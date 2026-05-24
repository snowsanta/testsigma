#!/usr/bin/env python3
"""
Interactive Manual Testing Utility for Testsigma Pipeline
--------------------------------------------------------
This script enables full manual testing of the Ingestion, Crawler, Graph,
and Reasoning engine layers of the Testsigma Autonomous Agent pipeline locally.

It implements an in-memory Graph Database simulator and a smart local text
parser/reporter, requiring zero external dependencies (no Neo4j container,
no OpenAI/Anthropic API keys required).
"""

import sys
import os
import re
import json
from typing import List, Dict, Any

# Insert root path so we can import src modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Smart Mock LLM Complete function
def smart_llm_complete(system: str, user: str, model: str = "gpt-4o") -> str:
    """
    Local smart mock to mimic an LLM responder for specs parsing and narrative report generation.
    """
    # 1. Ingestion Spec Parser Mock
    if "spec parser" in system.lower() or "extract all requirements" in user.lower():
        # Extract specs dynamically from input text using simple regex
        requirements = []
        lines = user.split("\n")
        for line in lines:
            # Match standard list pattern e.g., "* R1: User can create a repo"
            match = re.search(r"[\*\-]\s*(R\d+)\s*:\s*(.*)", line)
            if match:
                req_id = match.group(1)
                title = match.group(2).strip()
                # Determine a realistic section context
                section = "Features"
                if "security" in user.lower() and "r3" in req_id.lower():
                    section = "Security"
                elif "visualization" in title.lower():
                    section = "Graph Visualization"
                elif "blast radius" in title.lower() or "report" in title.lower():
                    section = "Reasoning Engine"
                
                requirements.append({
                    "id": req_id,
                    "title": title,
                    "source_section": section,
                    "raw_text": f"Specification line: {title}"
                })
        
        if not requirements:
            # Fallback defaults if parsing input failed
            requirements = [
                {"id": "R1", "title": "Parse markdown specs", "source_section": "Ingestion Features", "raw_text": "Upload Markdown file"},
                {"id": "R2", "title": "Scan repository signatures", "source_section": "Ingestion Features", "raw_text": "AST recursive repository scans"},
                {"id": "R3", "title": "Compute blast radius", "source_section": "Blast Radius Engine", "raw_text": "Trace modified PR changes"}
            ]
        return json.dumps(requirements, indent=2)

    # 2. Report Generator Specialist Mock
    if "quality assurance" in system.lower() or "blast radius" in user.lower():
        # Parse direct and downstream impacts from user prompt
        direct_ui = re.findall(r"'label': '([^']+)'", user) or ["Simulated UI Element"]
        direct_req = re.findall(r"'title': '([^']+)'", user) or ["Simulated Requirement"]
        downstream_ui = re.findall(r"Downstream Impacts:.*?ui_elements\":\s*\[([^\]]+)\]", user, re.DOTALL)
        downstream_req = re.findall(r"Downstream Specs:.*?requirements\":\s*\[([^\]]+)\]", user, re.DOTALL)
        
        prose = []
        prose.append("### [!!!] Quality Assurance Risk Assessment Report")
        prose.append("A pull request modification was analyzed for code-change risk and blast radius.")
        prose.append("\n#### 1. Directly Impacted Customer Features:")
        for r in set(direct_req):
            prose.append(f"- **{r}**: User interactions tied to this requirement are directly modified by these code adjustments.")
        
        prose.append("\n#### 2. User-Facing UI Elements Modified:")
        for ui in set(direct_ui):
            prose.append(f"- `{ui}` component has direct code alterations.")
            
        if downstream_ui or downstream_req:
            prose.append("\n#### 3. Downstream/Indirect Regressions Risk:")
            prose.append("The modified code paths trigger secondary components downstream that lack coverage:")
            for r in set(downstream_req):
                prose.append(f"- Potential impact to **{r}** user flow.")
        else:
            prose.append("\n#### 3. Downstream Regression Risk:")
            prose.append("- Risk is fully localized. No downstream navigation paths or secondary requirements are impacted.")
            
        prose.append("\n#### 4. QA Action Recommendations:")
        prose.append("- Run regression checks on directly modified elements.")
        prose.append("- Validate page state transitions between these interactive UI components.")
        return "\n".join(prose)
        
    return "Simulated Response"

# Monkeypatch LLM client interface before importing modules
import src.llm.client
src.llm.client.complete = smart_llm_complete

# Import actual pipeline modules
from src.ingest.parser import parse_prd
from src.ingest.code_parser import scan_repository
from src.ingest.models import Requirement, CodeFile
from src.graph.writer import write_requirement, write_code_file, write_covers_edge, write_implements_edge, write_transition_edge
from src.reason.pr_fetcher import PR
from src.reason.blast_radius import BlastRadiusEngine
from src.reason.reporter import generate_report

# In-Memory Graph Database Session Simulation
class MockRecord:
    def __init__(self, data_dict):
        self._data = data_dict
    def data(self):
        return self._data

class MockResult:
    def __init__(self, records):
        self.records = records
    def __iter__(self):
        return iter(self.records)
    def single(self):
        return self.records[0] if self.records else None

class InMemoryGraphSession:
    """Simulates a Neo4j bolt session, storing and matching nodes/edges in memory."""
    def __init__(self):
        self.nodes = {
            "Requirement": {},
            "UIElement": {},
            "CodeFile": {},
            "Absence": {}
        }
        self.edges = []  # List of dicts: {"from_label": x, "from_id": y, "to_label": z, "to_id": w, "type": t, "properties": {}}

    def _extract_prop(self, query_clean: str, prop: str) -> str:
        """Extract a property value from an inline Cypher SET/MERGE string: `{prop}: 'value'` or `u.{prop}='value'`."""
        for sep in (prop + ": '", prop + ":'", prop + "='", prop + "= '"):
            if sep in query_clean:
                start = query_clean.find(sep) + len(sep)
                end = query_clean.find("'", start)
                if start > len(sep) and end > start:
                    return query_clean[start:end]
        return ""

    def run(self, query: str, **kwargs) -> MockResult:
        query_clean = " ".join(query.split())
        
        # 1. Write Requirement
        if "MERGE (r:Requirement" in query_clean:
            req_id = kwargs.get("id") or self._extract_prop(query_clean, "id")
            self.nodes["Requirement"][req_id] = {
                "id": req_id,
                "title": kwargs.get("title", ""),
                "source_section": kwargs.get("source_section", ""),
                "raw_text": kwargs.get("raw_text", "")
            }
            return MockResult([MockRecord({"r": self.nodes["Requirement"][req_id]})])

        # 2. Write UIElement
        if "MERGE (u:UIElement" in query_clean:
            ui_id = kwargs.get("id") or self._extract_prop(query_clean, "id")
            self.nodes["UIElement"][ui_id] = {
                "id": ui_id,
                "selector": kwargs.get("selector") or self._extract_prop(query_clean, "selector"),
                "label": kwargs.get("label") or self._extract_prop(query_clean, "label"),
                "url": kwargs.get("url") or self._extract_prop(query_clean, "url")
            }
            return MockResult([MockRecord({"u": self.nodes["UIElement"][ui_id]})])

        # 3. Write COVERS relationship
        if "MERGE (r)-[c:COVERS]->(u)" in query_clean:
            req_id = kwargs["req_id"]
            ui_id = kwargs["ui_id"]
            edge = {
                "from_label": "Requirement", "from_id": req_id,
                "to_label": "UIElement", "to_id": ui_id,
                "type": "COVERS",
                "properties": {"confidence": kwargs.get("confidence", 1.0)}
            }
            self.edges.append(edge)
            return MockResult([MockRecord({"c": edge})])

        # 4. Write CodeFile
        if "MERGE (c:CodeFile" in query_clean:
            path = kwargs["path"]
            self.nodes["CodeFile"][path] = {
                "path": path,
                "language": kwargs.get("language", ""),
                "last_modified": kwargs.get("last_modified", "")
            }
            return MockResult([MockRecord({"c": self.nodes["CodeFile"][path]})])

        # 5. Write IMPLEMENTS relationship
        if "MERGE (c)-[i:IMPLEMENTS]->(u)" in query_clean:
            file_path = kwargs["file_path"]
            ui_id = kwargs["ui_id"]
            edge = {
                "from_label": "CodeFile", "from_id": file_path,
                "to_label": "UIElement", "to_id": ui_id,
                "type": "IMPLEMENTS",
                "properties": {"confidence": kwargs.get("confidence", 1.0)}
            }
            self.edges.append(edge)
            return MockResult([MockRecord({"i": edge})])

        # 6. Write TRANSITION relationship
        if "MERGE (u1)-[t:TRANSITION]->(u2)" in query_clean:
            from_id = kwargs["from_id"]
            to_id = kwargs["to_id"]
            edge = {
                "from_label": "UIElement", "from_id": from_id,
                "to_label": "UIElement", "to_id": to_id,
                "type": "TRANSITION",
                "properties": {
                    "action": kwargs.get("action", "click"),
                    "selector": kwargs.get("selector", "")
                }
            }
            self.edges.append(edge)
            return MockResult([MockRecord({"t": edge})])

        # 7. Get Blast Radius Query simulation (Traverse nodes in-memory)
        if "collect(DISTINCT ui) AS ui_elements" in query_clean:
            changed_files = kwargs.get("changed_files", [])
            # Normalize path separators for matching
            changed_files = [fp.replace("\\", "/") for fp in changed_files]
            min_conf = kwargs.get("min_confidence", 0.6)
            
            ui_elements = []
            requirements = []
            downstream_ui_elements = []
            downstream_requirements = []
            
            # Trace CodeFiles → UI via IMPLEMENTS edges (direct CodeFile → UIElement)
            for file_path in changed_files:
                for edge in self.edges:
                    if (edge["from_label"] == "CodeFile" and edge["from_id"] == file_path and 
                        edge["type"] == "IMPLEMENTS" and edge["properties"].get("confidence", 1.0) >= min_conf):
                        
                        ui_id = edge["to_id"]
                        if ui_id in self.nodes["UIElement"]:
                            ui_elements.append(self.nodes["UIElement"][ui_id])
            
            # Trace directly affected UI to covered requirements
            for ui in ui_elements:
                ui_id = ui["id"]
                for edge in self.edges:
                    if (edge["from_label"] == "Requirement" and edge["to_id"] == ui_id and 
                        edge["type"] == "COVERS" and edge["properties"].get("confidence", 1.0) >= min_conf):
                        
                        req_id = edge["from_id"]
                        if req_id in self.nodes["Requirement"]:
                            requirements.append(self.nodes["Requirement"][req_id])
            
            # Trace downstream UI elements (one transition hop for simulator)
            for ui in ui_elements:
                ui_id = ui["id"]
                for edge in self.edges:
                    if edge["from_label"] == "UIElement" and edge["from_id"] == ui_id and edge["type"] == "TRANSITION":
                        down_ui_id = edge["to_id"]
                        if down_ui_id in self.nodes["UIElement"] and down_ui_id not in [u["id"] for u in ui_elements]:
                            downstream_ui_elements.append(self.nodes["UIElement"][down_ui_id])
            
            # Trace downstream UI elements to covered downstream requirements
            for down_ui in downstream_ui_elements:
                down_ui_id = down_ui["id"]
                for edge in self.edges:
                    if (edge["from_label"] == "Requirement" and edge["to_id"] == down_ui_id and 
                        edge["type"] == "COVERS" and edge["properties"].get("confidence", 1.0) >= min_conf):
                        
                        req_id = edge["from_id"]
                        if req_id in self.nodes["Requirement"] and req_id not in [r["id"] for r in requirements]:
                            downstream_requirements.append(self.nodes["Requirement"][req_id])
                            
            return MockResult([MockRecord({
                "ui_elements": ui_elements,
                "requirements": requirements,
                "downstream_ui_elements": downstream_ui_elements,
                "downstream_requirements": downstream_requirements,
                "affected_flows": [],
                "absence_nodes": []
            })])

        return MockResult([])


# Main pipeline manual execution flow
def main():
    print("==========================================================")
    print("   [*] TESTSIGMA PIPELINE - LOCAL MANUAL TESTING UTILITY   ")
    print("==========================================================")
    
    # Step 1: Setup Simulated Graph Database Session
    session = InMemoryGraphSession()
    print("\n[System] Initialized In-Memory Graph Simulation Database Session.")
    
    # Step 2: Select and parse the PRD specification
    print("\n--- [Stage 1: Specs Ingestion] ---")
    default_prd_path = os.path.join(os.path.dirname(__file__), "tests/fixtures/sample_prd.md")
    
    if os.path.exists(default_prd_path):
        print(f"Found sample spec file at: {default_prd_path}")
        with open(default_prd_path, "r", encoding="utf-8") as f:
            prd_content = f.read()
    else:
        print("No specs file found under tests/fixtures/sample_prd.md. Using default built-in requirements specs.")
        prd_content = """
        # Default Specs
        * R1: User can upload a Markdown file as a PRD spec.
        * R2: User can scan a code repository.
        * R3: User can compute a blast-radius.
        """
        
    print("\nParsing Markdown Specification using `parse_prd`...")
    parsed_requirements = parse_prd(prd_content)
    print(f"Ingested {len(parsed_requirements)} structured specifications:")
    for req in parsed_requirements:
        print(f"  - [{req.id}] {req.title} ({req.source_section})")
        # Write requirement to simulated database
        write_requirement(session, req)
        
    # Step 3: Scan Codebase
    print("\n--- [Stage 2: Code Scanning & AST Parsing] ---")
    project_root = os.path.dirname(__file__)
    print(f"Scanning repository code files under root: {project_root} ...")
    scanned_files, scanned_functions = scan_repository(project_root)
    print(f"Scanned {len(scanned_files)} code modules and found {len(scanned_functions)} AST function definitions.")
    
    # Write code files to simulated database
    for cf in scanned_files:
        write_code_file(session, cf)

    # Filter project-specific python modules (excluding testsigma/venv files)
    target_files = [f.path for f in scanned_files if not f.path.startswith("testsigma") and f.path.startswith("src")]
    print("\nRegistered project source modules available for manual modification test:")
    for idx, f in enumerate(target_files):
        print(f"  [{idx + 1}] {f}")
        
    # Step 4: Create Simulated Semantic Graph Relationships (The UI Coverage Mappings)
    # To mimic what the BrowserAgent crawler and LLM mapping produces:
    print("\n--- [Stage 3: Seeding Semantic UI-Code-Spec Graph Links] ---")
    
    # Write mock UIElements to Graph
    session.run("MERGE (u:UIElement {id: 'U_spec_form'}) SET u.selector='#import-prd', u.label='Upload Spec Form', u.url='http://localhost/import'")
    session.run("MERGE (u:UIElement {id: 'U_scan_btn'}) SET u.selector='#scan-repo', u.label='Scan Code Button', u.url='http://localhost/scan'")
    session.run("MERGE (u:UIElement {id: 'U_blast_panel'}) SET u.selector='#blast-run', u.label='Blast Radius Engine Control Panel', u.url='http://localhost/blast'")
    session.run("MERGE (u:UIElement {id: 'U_report_view'}) SET u.selector='#narrative-report', u.label='QA Prose Report Panel', u.url='http://localhost/blast'")

    # Link Requirements to UI Elements (COVERS relationship)
    write_covers_edge(session, "R1", "U_spec_form", confidence=0.95)
    write_covers_edge(session, "R2", "U_scan_btn", confidence=0.90)
    write_covers_edge(session, "R3", "U_blast_panel", confidence=0.85)
    write_covers_edge(session, "R4", "U_blast_panel", confidence=0.75)
    write_covers_edge(session, "R5", "U_blast_panel", confidence=0.90)
    write_covers_edge(session, "R6", "U_report_view", confidence=0.95)
    
    # Link Code Files to UI Elements (IMPLEMENTS relationship)
    write_implements_edge(session, "src/ingest/parser.py", "U_spec_form", confidence=0.95)
    write_implements_edge(session, "src/ingest/code_parser.py", "U_scan_btn", confidence=0.90)
    write_implements_edge(session, "src/reason/blast_radius.py", "U_blast_panel", confidence=0.95)
    write_implements_edge(session, "src/reason/reporter.py", "U_report_view", confidence=0.95)
    
    # Map transitions between screens
    write_transition_edge(session, "U_spec_form", "U_blast_panel", action="click", selector="#next-btn")
    write_transition_edge(session, "U_blast_panel", "U_report_view", action="click", selector="#generate-report-btn")
    print("Successfully mapped 4 UIElements, 6 COVERS edges, 4 IMPLEMENTS edges, and 2 screen TRANSITIONS.")

    # Step 5: Prompt User to select modified files for Pull Request Simulation
    print("\n--- [Stage 4: Pull Request Simulation] ---")
    user_choice = input(f"\nEnter the number (1-{len(target_files)}) of the file you want to modify in your simulated PR: ")
    try:
        choice_idx = int(user_choice) - 1
        if choice_idx < 0 or choice_idx >= len(target_files):
            print("Invalid choice! Defaulting to src/reason/blast_radius.py")
            selected_file = "src/reason/blast_radius.py"
        else:
            selected_file = target_files[choice_idx]
    except ValueError:
        print("Invalid input! Defaulting to src/reason/blast_radius.py")
        selected_file = "src/reason/blast_radius.py"
        
    print(f"\nSimulating Pull Request modifying: `{selected_file}`")
    pr = PR(pr_number=101, changed_files=[selected_file])
    
    # Step 6: Run Blast Radius Engine calculation
    print("\n--- [Stage 5: Reasoning & Blast Radius Calculation] ---")
    engine = BlastRadiusEngine(session=session)
    calc_result = engine.compute(pr, min_confidence=0.6)
    
    print("\nStructured Blast Radius Calculation Output (JSON):")
    print(json.dumps(calc_result.to_dict(), indent=2))
    
    # Step 7: Run Quality Assurance Reporter to generate plain-English narrative report
    print("\n--- [Stage 6: Narrative Risk Reporting] ---")
    report_text, _ = generate_report(calc_result)
    print("\n" + report_text)
    print("\n==========================================================")
    print("                 MANUAL TESTING COMPLETED                 ")
    print("==========================================================")

if __name__ == "__main__":
    main()

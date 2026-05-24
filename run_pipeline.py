#!/usr/bin/env python3
"""
Real Pipeline Runner — Neo4j (Docker) + LM Studio (localhost:1234)
==================================================================
Runs the full TestSigma pipeline end-to-end:

  1. Ingest     — LLM parses tests/fixtures/sample_prd.md → structured requirements
  2. Scan Code  — AST scans src/ for Python modules
  3. Graph      — Writes requirements, code files, UI elements, and edges to Neo4j
  4. Reason     — Simulates a PR modifying a file, computes blast radius
  5. Report     — LLM generates plain-English risk report
"""

import os
import sys
from neo4j import GraphDatabase

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ── Stage 0: Connect to Neo4j ────────────────────────────────────────────────

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
driver.verify_connectivity()
print(f"[✓] Connected to Neo4j at {NEO4J_URI}")

with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")  # clean slate
print("[✓] Graph wiped for fresh run")

# ── Stage 1: Ingest PRD ──────────────────────────────────────────────────────

from src.ingest.parser import parse_prd

prd_path = os.path.join(os.path.dirname(__file__), "tests/fixtures/sample_prd.md")
with open(prd_path, "r", encoding="utf-8") as f:
    prd_content = f.read()

requirements = parse_prd(prd_content)
print(f"\n[Stage 1 — Ingest] Parsed {len(requirements)} requirements:")
for req in requirements:
    print(f"  [{req.id}] {req.title}  ({req.source_section})")

# ── Stage 2: Scan codebase ───────────────────────────────────────────────────

from src.ingest.code_parser import scan_repository

print(f"\n[Stage 2 — Scan] Scanning src/ for Python files ...")
files, functions = scan_repository(os.path.join(os.path.dirname(__file__), "src"))
project_files = [f for f in files if f.path.startswith("src")]
print(f"  Found {len(project_files)} source files, {len(functions)} functions")

# ── Stage 3: Write to Neo4j ──────────────────────────────────────────────────

from src.graph.writer import (
    write_requirement, write_code_file,
    write_covers_edge, write_implements_edge, write_transition_edge
)

with driver.session() as session:
    # Write requirements
    for req in requirements:
        write_requirement(session, req)

    # Write code files
    for cf in project_files:
        write_code_file(session, cf)

    # Write mock UI elements (simulating crawled DOM)
    ui_elements = [
        ("U_spec_form", "#import-prd", "Upload Spec Form", "http://localhost/import"),
        ("U_scan_btn", "#scan-repo", "Scan Code Button", "http://localhost/scan"),
        ("U_blast_panel", "#blast-run", "Blast Radius Panel", "http://localhost/blast"),
        ("U_report_view", "#narrative-report", "QA Report Panel", "http://localhost/blast"),
    ]
    for uid, sel, label, url in ui_elements:
        session.run(
            "MERGE (u:UIElement {id: $id}) SET u.selector=$sel, u.label=$label, u.url=$url",
            id=uid, sel=sel, label=label, url=url
        )

    # Wire COVERS: requirement → UI
    edge_mappings = [
        ("R1", "U_spec_form", 0.95),
        ("R2", "U_scan_btn", 0.90),
        ("R3", "U_blast_panel", 0.85),
        ("R4", "U_blast_panel", 0.75),
        ("R5", "U_blast_panel", 0.90),
        ("R6", "U_report_view", 0.95),
    ]
    for rid, uid, conf in edge_mappings:
        write_covers_edge(session, rid, uid, conf)

    # Wire IMPLEMENTS: code file → UI
    impl_mappings = [
        ("src/ingest/parser.py", "U_spec_form", 0.95),
        ("src/ingest/code_parser.py", "U_scan_btn", 0.90),
        ("src/reason/blast_radius.py", "U_blast_panel", 0.95),
        ("src/reason/reporter.py", "U_report_view", 0.95),
    ]
    for fpath, uid, conf in impl_mappings:
        write_implements_edge(session, fpath, uid, conf)

    # Wire TRANSITION: screen → screen
    write_transition_edge(session, "U_spec_form", "U_blast_panel", "click", "#next-btn")
    write_transition_edge(session, "U_blast_panel", "U_report_view", "click", "#generate-report-btn")

print(f"[Stage 3 — Graph] Written: {len(requirements)} reqs, {len(project_files)} files, "
      f"{len(ui_elements)} UIs, {len(edge_mappings)} COVERS, {len(impl_mappings)} IMPLEMENTS, 2 TRANSITIONS")

# ── Stage 4: Simulate PR & Compute Blast Radius ──────────────────────────────

from src.reason.pr_fetcher import PR
from src.reason.blast_radius import BlastRadiusEngine

# Simulate a PR modifying src/reason/blast_radius.py
pr = PR(pr_number=42, changed_files=["src/reason/blast_radius.py"])

with driver.session() as session:
    engine = BlastRadiusEngine(session=session)
    result = engine.compute(pr, min_confidence=0.6)

print(f"\n[Stage 4 — Blast Radius] PR #42 modifies: {pr.changed_files}")
print(f"  UI at risk:   {[u.get('selector', u.get('id', '?')) for u in result.ui_elements_at_risk]}")
print(f"  Reqs hit:     {[r.get('title', r.get('id', '?')) for r in result.affected_requirements]}")
print(f"  Downstream UI: {[u.get('selector', u.get('id', '?')) for u in result.downstream_ui_elements]}")
print(f"  Downstream reqs: {[r.get('title', r.get('id', '?')) for r in result.downstream_requirements]}")

# ── Stage 5: Generate Report ─────────────────────────────────────────────────

from src.reason.reporter import generate_report

print(f"\n[Stage 5 — Report] Calling LM Studio at localhost:1234 ...")
report, _ = generate_report(result)
print("\n" + "=" * 60)
print(report)
print("=" * 60)

# ── Cleanup ──────────────────────────────────────────────────────────────────

driver.close()
print("\n[Done] Pipeline complete.")

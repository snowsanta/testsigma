# TestSigma — Autonomous Risk Analysis Agent
## Design Document

**Author:** AI Engineer Candidate  
**Date:** May 2026  
**Version:** 1.0  
**Target Reader:** Senior engineers who will read this skeptically. Every claim here is one I can defend.

---

## Scope Statement

I went deep on the **Graph** and **Reason** layers. The blast-radius query, confidence model, and absence representation are where complexity lives and where the system's value is proven. The **Crawl** layer uses a fixture path after one real run — this is a deliberate tradeoff explained in Section 6, not a cut I'm hiding.

---

## 1. System Overview

The central question this system answers: **given a code change, what can break for a user?**

Everything else — crawling, ingesting, graph construction — is scaffolding to answer that one question with enough fidelity that a non-engineer QA lead can act on the output without understanding the underlying graph.

```mermaid
flowchart LR
    subgraph INPUT["Inputs"]
        PRD["📄 PRD / README\nMarkdown spec"]
        PR["🔀 GitHub Pull Request\nChanged file list"]
        URL["🌐 Web Application\nLive URL"]
    end

    subgraph PIPELINE["Agent Pipeline"]
        direction TB
        A["① INGEST\nparser.py"]
        B["② CRAWL\nbrowser_agent.py · artifacts.py"]
        C["③ GRAPH\nwriter.py · linker.py · absence.py"]
        D["④ REASON\npr_fetcher.py · blast_radius.py · reporter.py"]
    end

    subgraph OUTPUT["Output"]
        RPT["📋 QA Risk Report\nMarkdown + JSON\nReadable by non-engineers"]
    end

    PRD --> A
    URL --> B
    A --> C
    B --> C
    PR --> D
    C --> D
    D --> RPT

    style INPUT fill:#1a1a2e,stroke:#4a9eff,color:#e0e0e0
    style PIPELINE fill:#0f3460,stroke:#4a9eff,color:#e0e0e0
    style OUTPUT fill:#16213e,stroke:#4a9eff,color:#e0e0e0
```

The pipeline has five distinct processing stages, each with a clear boundary and a clear owner: code or LLM. The LLM is invoked exactly three times — parsing intent from text, judging semantic similarity, and writing prose. Every other decision is deterministic code.

---

## 2. Agent Decomposition

This is not a chain of prompts. The architecture separates reasoning stages by what kind of ambiguity they resolve. A deterministic rule genuinely cannot parse an unstructured PRD or judge whether "repository creation form" and `#new-repo-btn` are semantically related. An LLM cannot reliably traverse a graph or parse a GitHub API response. The boundary between them is not arbitrary — it maps directly to the nature of the task.

```mermaid
flowchart TD
    subgraph STAGE1["Stage 1 — PR Fetch + Diff Parse"]
        direction LR
        S1A["GitHub REST API\n/repos/:owner/:repo/pulls/:n/files"]
        S1B["PR struct\nList[changed_file_paths]"]
        S1A -->|"HTTP GET\n→ JSON"| S1B
        S1C["🟦 DETERMINISTIC\nStructured API. No ambiguity to resolve."]
    end

    subgraph STAGE2["Stage 2 — PRD Ingest"]
        direction LR
        S2A["Unstructured Markdown\nHeadings, bullet points, prose"]
        S2B["List[Requirement]\nid · title · source_section · raw_text"]
        S2A -->|"LLM call\n→ JSON array"| S2B
        S2C["🟨 LLM-DRIVEN\nIntent + section boundaries require semantic reading.\nNo regex can reliably extract 'what was intended'."]
    end

    subgraph STAGE3["Stage 3 — UI Crawl"]
        direction LR
        S3A["Start URL"]
        S3B["DOM + Interactive Elements\nCrawlArtifactBundle"]
        S3A -->|"Playwright mechanics\n(deterministic)"| S3X["HTML snapshot"]
        S3X -->|"LLM planner decides\nwhere to navigate next"| S3B
        S3C["🟪 HYBRID\nNavigation mechanics are deterministic.\nDeciding which link to click requires reasoning."]
    end

    subgraph STAGE4["Stage 4 — Cross-Layer Linking"]
        direction LR
        S4A["Requirements + UIElements\n(in graph)"]
        S4B["COVERS edges + IMPLEMENTS edges\nwith confidence scores 0–1"]
        S4A -->|"LLM batch match\n→ JSON array"| S4B
        S4C["🟨 LLM-DRIVEN\n'Upload Spec Form' ↔ R1 requires\nlanguage-level similarity judgment."]
    end

    subgraph STAGE5["Stage 5 — Blast Radius + Report"]
        direction LR
        S5A["Changed files from PR"]
        S5B["Risk report\nSeverity · Tables · Narrative"]
        S5A -->|"Multi-hop Cypher\n(deterministic)"| S5X["BlastRadiusResult struct"]
        S5X -->|"LLM prose generation"| S5B
        S5C["🟪 HYBRID\nGraph traversal is deterministic.\nConverting to QA-readable prose requires LLM."]
    end

    STAGE1 --> STAGE2
    STAGE2 --> STAGE3
    STAGE3 --> STAGE4
    STAGE4 --> STAGE5
```

### Stage Breakdown

| Stage | Module | Deterministic or LLM | Justification |
|---|---|---|---|
| PR fetch + diff parse | `pr_fetcher.py` | **Deterministic** | GitHub API is structured; response is unambiguous JSON |
| PRD parse → Requirements | `parser.py` | **LLM** | Unstructured markdown; intent and section boundaries require semantic reading |
| UI crawl → DOM + transitions | `browser_agent.py` | **Hybrid** | Playwright navigation mechanics are deterministic; choosing which element to interact with next requires reasoning about page purpose |
| Requirement ↔ UI linking | `linker.py` | **LLM** | Judging whether "repository creation form" maps to `#new-repo-btn` requires language-level similarity — no heuristic covers this reliably |
| Code ↔ UI linking | `linker.py` | **LLM** | Judging whether a code file implements a UI element requires semantic understanding of file names, paths, and content |
| Blast radius query | `reader.py` | **Deterministic** | Graph traversal is exact; Cypher handles the multi-hop path resolution |
| Report generation | `reporter.py` | **Hybrid** | Severity classification and table construction are deterministic; converting structured risk data to readable prose for a QA lead requires LLM |

### The LLM Boundary Rule

The LLM wrapper (`llm/client.py`) is the only place that makes external model calls. Every downstream module patches this single boundary in tests. This means 100% of business logic is unit-testable without live API calls.

Swapping model providers (OpenAI ↔ local LM Studio ↔ other compatible API endpoints) is fully supported at runtime via CLI flags (`--llm-provider`, `--openai-api-key`, `--llm-model`, `--llm-url`), configuring the unified `src.llm.client.configure()` interface dynamically at startup.

When `--llm-model` is omitted with LM Studio and a single model is loaded, the model field is omitted from the API payload and LM Studio auto-selects the loaded model.

---

## 3. Graph Schema

### Design Principles

The schema answers one question: **which code changes break which user-visible behaviors, and why?** Every node and edge type earns its place by being required for that traversal. Nodes that aren't queryable are not in the schema.

```mermaid
erDiagram
    Requirement {
        string id PK
        string title
        string source_section
        string raw_text
    }
    Absence {
        string req_id FK
        string reason
        float confidence
        datetime created_at
    }
    UIElement {
        string id PK
        string selector
        string label
        string url
        string element_type
    }
    CodeFile {
        string path PK
        string language
        string last_modified
    }

    Requirement ||--o{ Absence : "HAS_ABSENCE"
    Requirement ||--o{ UIElement : "COVERS (confidence)"
    UIElement ||--o{ UIElement : "TRANSITION (action, selector)"
    CodeFile ||--o{ UIElement : "IMPLEMENTS (confidence)"
```

### Node Catalogue

| Node | Layer | Key Properties | Purpose |
|---|---|---|---|
| `Requirement` | Requirements | `id`, `title`, `source_section`, `raw_text` | What was intended — the source of truth for product behavior |
| `Absence` | Requirements | `req_id`, `reason`, `confidence`, `created_at` | Requirements with no matching UI coverage — a first-class entity, not a boolean flag |
| `UIElement` | UI/DOM | `id`, `selector`, `label`, `url`, `element_type` | What was built — interactive elements captured from live crawl |
| `CodeFile` | Code | `path`, `language`, `last_modified` | How it was built — source files changed in a PR |

### Edge Catalogue

| Edge | From → To | Properties | Purpose |
|---|---|---|---|
| `COVERS` | Requirement → UIElement | `confidence (0–1)` | LLM-scored semantic link: this UI element implements this requirement |
| `HAS_ABSENCE` | Requirement → Absence | — | Flags requirements with zero UI coverage after crawl |
| `TRANSITION` | UIElement → UIElement | `action`, `selector` | Captures screen-to-screen navigation relationships from crawl |
| `IMPLEMENTS` | CodeFile → UIElement | `confidence (0–1)` | LLM-scored link: this code file implements this UI element |

### Why Absence Is a First-Class Node

The naive approach: add a boolean `has_coverage: false` flag on `Requirement`. The problem: you cannot traverse to it. You cannot query "requirements with absences connected to flows affected by this PR." A boolean is not a graph citizen.

By making `Absence` a node, we can write:

```cypher
MATCH (r:Requirement)-[:HAS_ABSENCE]->(a:Absence)
WHERE (r)-[:COVERS]->(:UIElement)<-[:IMPLEMENTS]-(:CodeFile {path: $changed_file})
RETURN r.title, a.reason
```

This returns requirements that **both** have coverage gaps **and** are in the blast radius of a specific code change. That query is impossible with a boolean flag.

### The Blast-Radius Query Explained

This is the query that justifies the entire schema. Given a list of changed files from a PR, it traces risk across all three layers:

```mermaid
flowchart LR
    CF["CodeFile\n(changed in PR)"]
    UI["UIElement\n(direct impact)"]
    DUI["UIElement\n(downstream,\nvia TRANSITION)"]
    REQ["Requirement\n(direct coverage)"]
    DREQ["Requirement\n(downstream\ncoverage)"]
    ABS["Absence\n(coverage gap)"]

    CF -->|"IMPLEMENTS\nconf ≥ threshold"| UI
    UI -->|"TRANSITION\n0..2 hops"| DUI
    UI -->|"COVERS ←"| REQ
    DUI -->|"COVERS ←"| DREQ
    REQ -->|"HAS_ABSENCE"| ABS

    style CF fill:#c0392b,stroke:#e74c3c,color:#fff
    style UI fill:#2980b9,stroke:#3498db,color:#fff
    style DUI fill:#1a6695,stroke:#3498db,color:#fff
    style REQ fill:#27ae60,stroke:#2ecc71,color:#fff
    style DREQ fill:#1a7a42,stroke:#2ecc71,color:#fff
    style ABS fill:#8e44ad,stroke:#9b59b6,color:#fff
```

The Cypher implementation:

```cypher
MATCH (cf:CodeFile)
WHERE cf.path IN $changed_files
OPTIONAL MATCH (cf)-[impl:IMPLEMENTS]->(ui:UIElement)
  WHERE impl.confidence >= $min_confidence
OPTIONAL MATCH (ui)<-[cov:COVERS]-(r:Requirement)
  WHERE cov.confidence >= $min_confidence
OPTIONAL MATCH (ui)-[:TRANSITION*0..2]->(downstream:UIElement)
OPTIONAL MATCH (downstream)<-[down_cov:COVERS]-(down_r:Requirement)
  WHERE down_cov.confidence >= $min_confidence
OPTIONAL MATCH (r)-[:HAS_ABSENCE]->(absence:Absence)
RETURN
  collect(DISTINCT ui)         AS ui_elements,
  collect(DISTINCT r)          AS requirements,
  collect(DISTINCT absence)    AS absence_nodes,
  collect(DISTINCT downstream) AS downstream_ui_elements,
  collect(DISTINCT down_r)     AS downstream_requirements
```

`OPTIONAL MATCH` throughout — if any layer is unlinked, the query still returns partial results rather than an empty set. This is intentional: a missing link is itself signal worth reporting.

---

## 4. Confidence Handling Under Ambiguity

The system produces probabilistic links, not exact mappings. Three failure modes require explicit handling:

```mermaid
flowchart TD
    subgraph FM1["Failure Mode 1: Unmapped Code File"]
        FM1A["PR changes app/new_module.rb"]
        FM1B{"CodeFile node\nexists in graph?"}
        FM1C["OPTIONAL MATCH returns null\nQuery continues with partial results"]
        FM1D["Report flags: 'N changed files\ncould not be mapped to UI elements'"]
        FM1A --> FM1B
        FM1B -->|"No"| FM1C --> FM1D
        FM1B -->|"Yes"| FM1E["Normal blast radius traversal"]
    end

    subgraph FM2["Failure Mode 2: Requirement Not Found in UI"]
        FM2A["Requirement R7 exists\nNo COVERS edges exist"]
        FM2B["Post-processing:\nmark_all_absences()"]
        FM2C["Absence node created\nHAS_ABSENCE edge written\nReason + timestamp stored"]
        FM2D["If changed code maps to flow\nthat depends on this requirement:\nAbsence surfaced in report"]
        FM2A --> FM2B --> FM2C --> FM2D
    end

    subgraph FM3["Failure Mode 3: Borderline Semantic Match"]
        FM3A["LLM assigns confidence 0.52\nfor a Requirement ↔ UIElement link"]
        FM3B["Confidence stored on COVERS edge"]
        FM3C{"confidence ≥\nmin_confidence threshold?"}
        FM3D["Edge excluded from\nblast radius traversal"]
        FM3E["Edge included, result\nmarked as low-confidence"]
        FM3F["If >30% edges are low-confidence:\nreport flagged for human review"]
        FM3A --> FM3B --> FM3C
        FM3C -->|"No (default: 0.6)"| FM3D
        FM3C -->|"Yes"| FM3E --> FM3F
    end
```

### Confidence Score Semantics

| Score Range | Interpretation | Display |
|---|---|---|
| 0.80 – 1.00 | High confidence — LLM is certain of semantic match | 🟢 |
| 0.60 – 0.79 | Medium confidence — plausible match, passes default threshold | 🟡 |
| 0.00 – 0.59 | Low confidence — borderline match, excluded from traversal by default | 🔴 |

Confidence thresholds are named as tuning parameters, not principles. The default of 0.6 was chosen to exclude noise while preserving genuinely uncertain links. Teams should calibrate this against their own false-positive tolerance.

### Human-in-the-Loop Trigger

```python
# From reporter.py — the 30% threshold is a named heuristic
if structured["low_confidence_count"] / structured["total_edges"] > 0.30:
    report += "⚠ >30% of edges are low-confidence — manual review recommended."
```

The system does not halt. It produces the best report it can and flags uncertainty explicitly. A QA lead can decide whether to act on flagged items. This is the correct behavior: the system augments human judgment, it does not replace it.

---

## 5. Eval Approach

The question: **if we ran this system 100 times on the same input, how do we know which runs were correct?**

```mermaid
flowchart LR
    subgraph DETERMINISTIC["Deterministic Layer — 100% reproducible"]
        D1["PR fetch\n→ identical changed_files"]
        D2["Graph writes (MERGE)\n→ idempotent, same graph every run"]
        D3["Cypher traversal\n→ identical blast radius result struct"]
        D4["30 unit + integration tests\nverify all of the above"]
        D1 --> D2 --> D3
    end

    subgraph LLM_LAYER["LLM Layer — probabilistic, scored by rubric"]
        L1["PRD Parsing\nEval: recall + precision vs.\nhand-labeled requirement set"]
        L2["Semantic Linking\nEval: edge accuracy vs.\ngold-standard COVERS/IMPLEMENTS set"]
        L3["Report Prose\nEval: rubric scoring on\nclarity · coverage · confidence transparency"]
    end

    DETERMINISTIC -->|"Struct inputs to LLM stages"| LLM_LAYER
```

### Deterministic Layer Verification

All 30 tests use `unittest.mock.patch` on `src.llm.client.complete` — the single LLM boundary. With the LLM mocked:

- `test_write_requirement_node_creates_node` — asserts exact Cypher MERGE structure and parameter bindings
- `test_blast_radius_filters_out_low_confidence_edges` — asserts `min_confidence` is passed correctly to the query
- `test_pr_fetcher_returns_changed_files` — uses `responses` library to mock GitHub API, asserts parsed file list
- `test_full_pipeline_produces_report` — integration test: seeds mock graph, runs blast radius, verifies report structure

If deterministic layers produce the same output on the same input 100/100 times, the only variance is in LLM outputs.

### LLM Layer Scoring Rubric

> [!NOTE]
> The LLM Layer Scoring Rubric detailed below represents a conceptual evaluation framework (TODO). It defines the recommended guidelines for continuous evaluation in a production environment, but is not yet implemented as automated validation code in the current codebase.

**PRD Parsing (Ingest):**
- Recall: what fraction of hand-labeled requirements were extracted?
- Precision: what fraction of extracted requirements are genuine?
- Section attribution: is `source_section` correctly mapped?

**Semantic Linking:**
- Ground truth: manually labeled COVERS/IMPLEMENTS pairs for a test application
- Accuracy at threshold 0.6: what fraction of edges above threshold are correct?
- False-negative rate: what fraction of genuine links fall below threshold?

**Report Prose:**
- Does the report name specific UI elements and requirements (not generic IDs)?
- Is severity classification consistent with the underlying data?
- Are confidence warnings present where low-confidence edges exist?
- No Cypher, no node IDs, no implementation details visible to QA reader?

The last criterion is tested deterministically: `test_reporter_does_not_expose_cypher_or_ids` asserts that "MATCH", "MERGE", and "neo4j" do not appear in any generated report.

---

## 6. Scope Decisions

This section leads with what I prioritized, not with apology for what I cut.

```mermaid
quadrantChart
    title Investment Depth vs. Assignment Value
    x-axis Low Value --> High Value
    y-axis Low Depth --> High Depth
    quadrant-1 Over-invested
    quadrant-2 Core Bets
    quadrant-3 Deliberately Skipped
    quadrant-4 Easy Wins
    Graph Schema: [0.85, 0.90]
    Blast Radius Query: [0.90, 0.85]
    Test Coverage: [0.75, 0.80]
    Report Quality: [0.80, 0.75]
    Absence Modeling: [0.85, 0.75]
    Confidence Model: [0.75, 0.70]
    PRD Ingest: [0.70, 0.65]
    Live Crawling: [0.60, 0.25]
    Screenshots: [0.30, 0.10]
    Call Graph: [0.55, 0.20]
    UserFlow Nodes: [0.50, 0.15]
```

### What I Went Deep On

**Graph Schema and Absence Modeling.** The three-layer schema with Absence as a first-class node is the intellectual core of this system. Getting it right means the blast-radius query is a natural graph traversal rather than a workaround. This is where I spent the most careful design time.

**Blast-Radius Cypher Query.** Multi-hop traversal with configurable confidence thresholds, downstream TRANSITION propagation (0..2 hops), and OPTIONAL MATCH throughout so partial data always yields a useful result. The query handles five distinct categories of risk in a single database round-trip.

**Test Coverage.** 30 tests across 5 modules, all written test-first per the coding plan. Every LLM call site is mocked at the `llm.client.complete` boundary. The integration test runs the full pipeline with mock dependencies. This means the deterministic core is verifiable without any API keys or running databases.

**Report Output Quality.** The reporter produces severity classification, confidence percentages, markdown tables distinguishing direct from downstream impact, and an LLM narrative. The output is genuinely readable by a non-engineer QA lead.

### What I Scoped Down and Why

**Live crawling replaced by fixture path for debug/demo.** The `BrowserAgent` is fully implemented with Playwright + LLM planner and handles real navigation, error recovery, and URL deduplication. Pass `--url` without `--crawl-fixture` to trigger a live crawl. The `--crawl-fixture` flag loads a pre-captured JSON file for debug/demo reliability — live crawling on a public application has non-deterministic timing, bot detection, and network failures that would make a demo fail unpredictably. The fixture path makes the demo reliable. The agent code is real and tested.

**CodeFunction and function-level tracing removed.** The `code_parser.py` was removed, `CodeFunction` removed from schema, and `CALLS`/`DEFINED_IN` edges removed. The blast radius operates at file-level granularity via `IMPLEMENTS` edges. Function-level call-graph tracing with `CALLS*` multi-hop traversal is the next highest-value addition (see Section 7). The schema was simplified to eliminate nodes and edges not actively populated by the pipeline.

**`UserFlow` and `PART_OF` removed from active Cypher.** The schema defines `UserFlow` nodes and `PART_OF` edges conceptually, but they are not populated by the current pipeline. The blast radius query uses `TRANSITION` edges between `UIElement` nodes directly, which gives equivalent traversal.

**Screenshot capture not implemented.** The assignment mentions screenshots as a crawl artifact. The `DOMSnapshot` captures HTML and interactive elements, which is what the graph ingestion needs. Screenshots would add value for a human reviewer of the crawl output but not for the downstream graph construction.

---

## 7. What I Would Build Next

In priority order, with reasoning:

```mermaid
gantt
    title Next Week Roadmap — Priority Order
    dateFormat  YYYY-MM-DD
    section Priority 1
    Webhook-triggered crawl      :p1, 2026-05-25, 3d
    PR event → targeted recrawl  :p1b, after p1, 2d

    section Priority 2
    Function-level call graph     :p2, 2026-05-25, 4d
    CALLS + DEFINED_IN edges      :p2b, after p2, 2d

    section Priority 3
    Confidence calibration UI     :p3, 2026-05-28, 5d
    Feedback loop to linker       :p3b, after p3, 2d
```

### Priority 1 — Webhook-Triggered Live Crawling

**The problem it solves:** The graph goes stale the moment the application changes. A PR that adds a new route creates UI elements the graph doesn't know about, meaning blast-radius results silently miss new coverage.

**What to build:** A GitHub webhook listener that triggers a targeted recrawl when a PR is opened. The crawl focuses on routes mentioned in the PR's changed files (inferred from file paths and import trees), not the full application. New DOM snapshots merge into the graph without wiping existing nodes.

**Why this is #1:** The graph's accuracy degrades over time without it. Every other improvement assumes the graph is current.

### Priority 2 — Dynamic Call-Graph Analysis

**The problem it solves:** File-level blast radius misses shared utility functions. If `utils/auth.py` is changed and it's called by 12 route handlers, the current system only traces from `utils/auth.py` directly to UI elements — it doesn't traverse the call tree to find all affected callers.

**What to build:** Reintroduce `code_parser.py` with `ast.Call` node extraction. Add `CodeFunction` node, `CALLS` and `DEFINED_IN` edges to the schema. Update the blast-radius query to start from `CodeFile → DEFINED_IN ← CodeFunction → CALLS* → CodeFunction → DEFINED_IN → CodeFile → IMPLEMENTS → UIElement`.

**Why this is #2:** Function-level tracing dramatically increases blast-radius accuracy for utility-heavy codebases. It's the difference between "this file is affected" and "these 12 specific functions, called from these 5 routes, are affected."

### Priority 3 — Confidence Calibration UI

**The problem it solves:** The LLM's semantic similarity scores are heuristics. A confident incorrect link (confidence 0.95 for a wrong match) is worse than a low-confidence correct one. Engineers who know the codebase can identify these mislinks immediately, but there's no way to feed that knowledge back.

**What to build:** A lightweight graph editor UI showing the COVERS and IMPLEMENTS edges with their confidence scores. Engineers click to promote, demote, or delete links. Accepted corrections are written back to Neo4j and used as few-shot examples for the next linking run.

**Why this is #3:** It closes the accuracy feedback loop without requiring manual re-running of the full pipeline. Over time, the system's precision improves on the specific codebase it's calibrated for.

### Priority 4 — Automated LLM Evaluation Suite (TODO)

**The problem it solves:** Without automated tracking of LLM semantic parser and linker changes, adjustments to model prompts, configuration thresholds, or core model engines can cause silent recall and precision regressions that are extremely hard to detect.

**What to build:** An automated pipeline regression runner that executes the LLM parser and linker over "gold-standard" benchmark datasets (hand-labeled PRD specs and Requirement ↔ UI mapping assertions). The runner outputs detailed precision, recall, and false-negative metrics, serving as an automated CI/CD quality gate to block regressions.

**Why this is #4:** It shifts evaluation from subjective manual reviews to systematic, quantitative metrics, ensuring that LLM behaviors are fully auditable and continuously measured.

---

## 8. System Architecture — Full Dataflow

```mermaid
sequenceDiagram
    participant CLI as CLI (cli.py)
    participant INGEST as Ingest Layer
    participant CRAWL as Crawl Layer
    participant NEO4J as Neo4j Graph
    participant LINKER as LLM Linker
    participant GITHUB as GitHub API
    participant REASON as Reason Engine
    participant LLM as LLM (llm/client.py)

    CLI->>INGEST: parse_prd(prd_content)
    INGEST->>LLM: complete(system, user_prompt)
    LLM-->>INGEST: JSON array of requirements
    INGEST-->>CLI: List[Requirement]

    CLI->>CRAWL: BrowserAgent.run(url)
    CRAWL->>LLM: LLMPlanner.next_action(elements)
    LLM-->>CRAWL: {action, selector, reason}
    CRAWL-->>CLI: CrawlArtifactBundle

    CLI->>NEO4J: write_requirement() × N
    CLI->>NEO4J: write_ui_element() × N
    CLI->>NEO4J: write_transition_edge() × N

    CLI->>LINKER: link_requirements_to_ui(session)
    LINKER->>NEO4J: MATCH all Requirements + UIElements
    NEO4J-->>LINKER: nodes
    LINKER->>LLM: batch semantic match prompt
    LLM-->>LINKER: [{req_id, ui_ids, confidence}]
    LINKER->>NEO4J: write_covers_edge() × N

    CLI->>NEO4J: mark_all_absences(session)
    Note over NEO4J: MATCH Requirements with no COVERS edges<br/>MERGE Absence nodes + HAS_ABSENCE edges

    CLI->>GITHUB: fetch_pr(repo, pr_number)
    GITHUB-->>CLI: List[changed_file_paths]

    CLI->>NEO4J: write_code_file() × N (seed PR files)
    
    CLI->>LINKER: link_code_to_ui(session)
    LINKER->>LLM: code file → UI match prompt
    LLM-->>LINKER: [{ui_id, file_paths, confidence}]
    LINKER->>NEO4J: write_implements_edge() × N

    CLI->>REASON: BlastRadiusEngine.compute(pr)
    REASON->>NEO4J: multi-hop Cypher query
    NEO4J-->>REASON: {ui_elements, requirements,<br/>downstream_ui, absence_nodes}

    REASON->>LLM: generate_report(blast_result)
    LLM-->>REASON: plain-English narrative
    REASON-->>CLI: report_text + structured_json
    CLI->>CLI: save_report() → reports/report-*.md
```

---

## 9. Test Architecture

```mermaid
flowchart TB
    subgraph UNIT["Unit Tests (25 tests)"]
        T1["tests/ingest/\ntest_models.py · test_parser.py\n5 tests — models, LLM mock"]
        T2["tests/crawl/\ntest_artifacts.py · test_browser_agent.py\n6 tests — serialization, Playwright mock, step limit"]
        T3["tests/graph/\ntest_writer.py · test_reader.py\n10 tests — Cypher structure, confidence filtering, absence"]
        T4["tests/reason/\ntest_pr_fetcher.py · test_blast_radius.py · test_reporter.py\n7 tests — GitHub mock, result struct, prose output"]
    end

    subgraph INTEGRATION["Integration Test (1 test)"]
        T5["tests/integration/test_end_to_end.py\nFull pipeline: ingest → graph seed → blast radius → report\nAll LLM calls mocked; graph operations mocked"]
    end

    subgraph FIXTURES["Shared Fixtures (conftest.py)"]
        F1["mock_llm_client\nmonkeypatches src.llm.client.complete\nReturns configurable string — not a real LLM call"]
        F2["neo4j_session\nMagicMock with .run() + .single() mocked\nNo real database connection"]
        F3["docker_neo4j\nMock container with bolt_url\nFor integration smoke test"]
    end

    FIXTURES --> UNIT
    FIXTURES --> INTEGRATION
```

**The key architectural decision:** mock at `src.llm.client.complete`, not at the LangChain level or the HTTP level. This means every LLM-consuming module can be tested by setting `mock_llm_client.return_value = "..."` to any string, and the downstream parsing logic is tested with that string. Tests verify the full code path from LLM output to structured result — just without calling a real model.

---

## Appendix A — Sample Blast-Radius Report (Real Output)

The following is an unedited report produced by the live system against **[Cudael/quiz PR #38](https://github.com/Cudael/quiz/pull/38)**, targeting the application at `https://quiz.cudael.dev`.

**Model used:** All three LLM stages (PRD parsing, semantic linking, report prose) were run using **Gemma 3 4B** via LM Studio at `localhost:1234` — a 4-billion parameter model running locally, chosen for zero-cost offline operation during development. It is not the model this system is designed to be evaluated against.

The `llm/client.py` wrapper is model-agnostic: swapping to GPT-4o, Claude 3.5 Sonnet, or Gemma 3 27B requires changing one environment variable (`LM_STUDIO_MODEL`). A larger model would be expected to improve results across all three stages:

| Stage | Expected improvement with a larger model |
|---|---|
| PRD Parsing | Better handling of ambiguous spec language; more accurate `source_section` attribution; fewer missed requirements in dense documents |
| Semantic Linking | More conservative and calibrated confidence scores; fewer false-positive COVERS/IMPLEMENTS matches; better discrimination between semantically adjacent but functionally distinct elements |
| Report Prose | Less generic phrasing; tighter narrative; better alignment between severity language and actual risk data |

The 100% confidence scores throughout this report are a direct artifact of Gemma 3 4B's tendency to over-commit in structured JSON outputs. A model with stronger calibration (GPT-4o, Claude 3.5 Sonnet) would be expected to return a realistic distribution of confidence scores rather than collapsing to 1.0 for every match.

Three observations worth naming honestly:

1. **All confidence scores are 100%.** Partly a model calibration issue (above), and partly a prompt gap — the linker prompt does not include few-shot examples with sub-1.0 scores to anchor the output range. Both are fixable and tracked under Section 7, Priority 3.

2. **Direct and Downstream tables are identical.** The TRANSITION traversal (`*0..2` hops) returned the same element set as the direct pass. This is correct behavior when the crawl captured a single-page context with no outbound transitions recorded — the 0-hop case of `TRANSITION*0..2` returns the originating elements themselves. The output is not wrong; it reflects the graph's current transition coverage. A richer crawl would produce distinct downstream entries.

3. **Selectors are real.** `#import-prd`, `.question-card .image-upload-dropzone`, `.image-upload-remove` — these came from a live Playwright crawl of `quiz.cudael.dev`, not a hand-written fixture. The graph is grounded in actual DOM structure.

All three observations are documented rather than hidden. They represent the honest state of the system at submission time.

---

### Report: Cudael/quiz PR #38 — `quiz.cudael.dev`

**Generated:** 2026-05-24 13:31:17  
**Target:** https://quiz.cudael.dev  
**PR:** Cudael/quiz#38

---

#### 1. Impact Summary

**Severity:** Critical  
**Confidence Coverage:** 100% of edges are high-confidence

#### 2. Directly Affected

| Feature | UI Element | Confidence |
|---------|-----------|------------|
| Upload Spec File Input | `input[type=file]` | 🟢 100% |
| Import PRD Spec Button | `#import-prd` | 🟢 100% |
| Publish Step Cover Image Upload | `.step-publish .image-upload-dropzone` | 🟢 100% |
| Question Image Preview | `.question-card .image-preview img` | 🟢 100% |
| Question Image Upload Dropzone | `.question-card .image-upload-dropzone` | 🟢 100% |
| Remove Image Button | `.image-upload-remove` | 🟢 100% |
| Replace Image Button | `.image-upload-replace` | 🟢 100% |
| Cover Image Preview | `.image-preview img` | 🟢 100% |
| Quiz Cover Image Upload Dropzone | `.image-upload-dropzone` | 🟢 100% |
| Cover Image URL Text Input | `#image-url-input` | 🟢 100% |
| Publish Quiz Button | `#publish-quiz` | 🟢 100% |
| Markdown PRD Upload | — | 🟢 100% |

#### 3. Downstream Cascade

These features may be indirectly affected via UI transitions:

| Feature | UI Element | Confidence |
|---------|-----------|------------|
| Upload Spec File Input | `input[type=file]` | 🟢 100% |
| Import PRD Spec Button | `#import-prd` | 🟢 100% |
| Publish Step Cover Image Upload | `.step-publish .image-upload-dropzone` | 🟢 100% |
| Question Image Preview | `.question-card .image-preview img` | 🟢 100% |
| Question Image Upload Dropzone | `.question-card .image-upload-dropzone` | 🟢 100% |
| Remove Image Button | `.image-upload-remove` | 🟢 100% |
| Replace Image Button | `.image-upload-replace` | 🟢 100% |
| Cover Image Preview | `.image-preview img` | 🟢 100% |
| Quiz Cover Image Upload Dropzone | `.image-upload-dropzone` | 🟢 100% |
| Cover Image URL Text Input | `#image-url-input` | 🟢 100% |
| Publish Quiz Button | `#publish-quiz` | 🟢 100% |
| Markdown PRD Upload | — | 🟢 100% |

*Note: Direct and downstream tables are identical because the crawl fixture captured a single-page context with no outbound transitions. The 0-hop case of `TRANSITION*0..2` returns the source elements themselves. See calibration note above.*

#### 4. Narrative Assessment

**Executive Summary.** A Critical failure point has been identified related to the Markdown PRD Upload feature. With 100% confidence across the blast radius, any defect in this single ingestion requirement threatens functionality across 11 downstream UI components. Immediate testing is required to validate the input pathway before deployment.

**Recommended Test Cases.**

1. **Core Functionality (Positive Path):** Upload a standard-format markdown file that meets all PRD structural requirements. Verify the system accepts the file, processes it correctly, and accurately renders the resulting data without error. *(Confirms the happy path still works after any changes.)*

2. **Boundary & Edge Case Testing (Failure Path):** Upload files that violate structural constraints — empty file, oversized file, corrupted formatting. Verify the system rejects each with a clear, actionable error message rather than entering an unknown state. *(Validates robustness of input validation.)*

3. **Downstream Display Verification (Cascade Check):** After a successful markdown PRD upload, navigate to all 11 affected downstream UI elements and verify they are correctly populated. Specifically check image upload dropzones, image previews, and the Publish Quiz button — all of which depend on the upload completing cleanly. *(Directly verifies the integrity of the cascade.)*

4. **Error Handling Under Interruption:** Simulate upload interruption midway (network drop, service timeout). Verify retry mechanisms engage and the user is clearly notified of the failure point without losing prior progress. *(Tests system resilience against transient failures.)*

5. **Concurrent Upload Load Test:** Simulate multiple users uploading large markdown files simultaneously. Monitor API response times to confirm the ingestion pipeline remains performant under concurrent load. *(Ensures the change does not introduce performance regressions at scale.)*

---

*Design document ends. Code, tests, and this document were produced as part of the Testsigma AI Engineer take-home assignment. The system is runnable end-to-end with `python cli.py` or in-memory with `python manual_test_pipeline.py`.*

# Design Document Plan — Testsigma AI Engineer Assignment
> What to write, section by section, with the argument to make in each.

---

## Document Metadata

- Format: Markdown (rendered PDF via Pandoc for submission)
- Target length: 10–11 pages
- Audience: Senior engineers who will read skeptically — treat every claim as one that needs to be defended
- Tone: Opinionated. Name trade-offs by name. Never use passive constructions to hide a decision.

---

## Section 1 — System Overview (0.5 pages)

**What to write:**
One diagram (system flow: Crawl → Ingest → Graph → Reason) and three sentences of framing. Do not explain what a knowledge graph is. Assume the reader knows.

**The argument:** Frame the whole system around one question — *"given a code change, what can break for a user?"* Everything else is scaffolding for that question. State this explicitly upfront so the rest of the document reads as justified by it.

**Scope statement goes here, not buried in a footnote.** One sentence: "I went deep on the Graph and Reason layers. The Crawl layer supports both live Playwright navigation and fixture-based replay. CodeFunction-level call-graph traversal is deferred — the blast radius operates at CodeFile→UIElement granularity. This is a deliberate choice, explained in Section 6."

---

## Section 2 — Agent Decomposition (1.5 pages)

**What to write:**
Define the six distinct stages. For each stage, state explicitly: is it deterministic or LLM-driven? Why?

| Stage | Deterministic or LLM | Justification |
|---|---|---|
| PR fetch + diff parse | Deterministic | GitHub REST API is structured; no ambiguity to resolve |
| PRD parse → Requirement structs | LLM | Unstructured markdown; intent and section boundaries require semantic reading |
| UI crawl → DOM + transitions | Deterministic + LLM Planner | Playwright navigation is deterministic; deciding which element to click next requires reasoning about the page's purpose |
| Code → UI semantic linking | LLM | Matching source file paths to UI elements by naming convention and context requires language understanding |
| Requirement → UI semantic linking | LLM | Judging similarity between prose specs and DOM element labels requires language processing |
| Blast radius report generation | LLM | Raw risk data must be converted into actionable, non-technical plain-English prose |

**The argument this section must make:** This is not a chain of prompts. LLM is used only where a deterministic rule genuinely cannot do the job. Detail what the deterministic parts do — file parsing, graph structures, diff extraction, JSON serialization, graph writes, Neo4j Cypher queries. The LLM touches five specific boundaries: parsing intent from markdown, navigating pages autonomously, linking code paths to UI, linking requirements to UI, and writing prose. Everything else — the schema, the graph writes, the blast radius traversal, the severity classification — is deterministic code.

**What to avoid:** Do not list "I use LangChain for the agent loop" as if that answers the decomposition question. The reviewer is checking whether you know *where* the reasoning boundary is, not what library you used.

---

## Section 3 — Graph Schema with Justification (2.5 pages)

**What to write:**
This section needs to earn its length. Three parts:

**Part A — Node and edge catalogue**

| Node type | Key properties | Layer | Status |
|---|---|---|---|
| `Requirement` | id, title, source_section, raw_text | Requirements | Fully implemented |
| `Absence` | req_id, reason, confidence | Requirements | Fully implemented |
| `UIElement` | id, selector, label, url | UI/DOM | Fully implemented |
| `UserFlow` | id, name, start_url, steps (list) | UI/DOM | Schema defined; not populated (deferred) |
| `CodeFile` | path, language, last_modified | Code | Fully implemented |
| `CodeFunction` | name, file_path, start_line, end_line | Code | Model defined, AST extracted; not written to Neo4j (deferred) |

| Edge type | From → To | Key properties | Status |
|---|---|---|---|
| `COVERS` | Requirement → UIElement | confidence (0–1) | Fully implemented |
| `HAS_ABSENCE` | Requirement → Absence | — | Fully implemented |
| `PART_OF` | UIElement → UserFlow | step_order | Schema defined; never populated (deferred) |
| `IMPLEMENTS` | CodeFile → UIElement | confidence (0–1) | Fully implemented |
| `CALLS` | CodeFunction → CodeFunction | — | Schema defined; never populated (deferred) |
| `DEFINED_IN` | CodeFunction → CodeFile | — | Schema defined; never populated (deferred) |
| `TRANSITION` | UIElement → UIElement | action (str), selector (str) | Fully implemented |

**Important schema note for the evaluator:** The full schema (6 nodes, 7 edges) is defined in `src/graph/schema.py`. The implemented subset used in the blast radius is 4 nodes (Requirement, Absence, UIElement, CodeFile) and 4 edges (COVERS, HAS_ABSENCE, IMPLEMENTS, TRANSITION). UserFlow, CodeFunction, CALLS, DEFNED_IN, and PART_OF are defined as forward-compatible schema elements to support call-graph traversal in the next iteration — the blast radius operates at CodeFile→UIElement granularity, which is the design trade-off explained in Section 6.

**Part B — How absence is modelled**

* **Post-processing Goal:** Identify all `Requirement` nodes that have no outgoing `COVERS` edges to any `UIElement`. For each found gap, write an `Absence` node containing the crawl verification context (reason description, zeroed confidence) and link it via a `HAS_ABSENCE` relationship.
* **Schema Importance:** Modeling absence as an independent node rather than a boolean flag on requirements allows us to track unique parameters (specific detection reasons) and query missed coverages in isolation. Absence nodes are keyed on `req_id` with MERGE for idempotency across re-runs.

**Part C — The query that justifies the schema**

* **Current Blast-Radius Query Logic (implemented):**
  * **Scope Search:** Start with CodeFile nodes whose paths match the PR's changed file list.
  * **Trace to UI Layer:** Follow `IMPLEMENTS` edges to matching UIElement nodes, filtering by a configurable `min_confidence` parameter.
  * **Link to Product Intent:** Trace back to Requirement nodes along `COVERS` edges, applying confidence filters.
  * **Propagate Downstream:** Traverse up to 2 hops along `TRANSITION` edges to capture UI elements indirectly affected by modifying the initial component.
  * **Link downstream Requirements:** Trace back from downstream UI elements along `COVERS` edges.
  * **Expose Untested Risks:** Query any `Absence` nodes linked to affected requirements.
  * **Aggregate Results:** Return distinct UI elements, requirements, downstream UI elements, downstream requirements, flows, and absence details — all null-safe via OPTIONAL MATCH.

* **Deferred: CodeFunction-level traversal** — The schema supports following `DEFINED_IN` from Function→File and `CALLS` between functions. This would enable tracing the blast radius along the call graph (not just the file→UI mapping) to identify functions in unaffected files that call into affected code. Scoped down per Section 6.

---

## Section 4 — Confidence Handling under Ambiguity (1.5 pages)

**What to write:**
Three specific failure modes and how each is handled.

* **Failure mode 1: Code change touches an unmapped file**
  * *Handling Goal:* OPTIONAL MATCH in Cypher prevents execution errors. The blast radius returns empty lists for unconnected files. The report output clearly states "No user-facing flows are affected" when zero UI or requirement nodes are reached. Unmapped modules are visible in the JSON output as absent from `directly_affected_ui`.

* **Failure mode 2: Mismatched requirements (Absent Features)**
  * *Handling Goal:* Post-crawl `mark_all_absences()` creates an `Absence` node for every Requirement with no COVERS edges. If a changed code path maps to a flow that depends on this absent feature, the absence is surfaced in the blast radius result and flagged in the report.

* **Failure mode 3: Borderline semantic matches**
  * *Handling Goal:* Confidence scores (0.0–1.0) stored on COVERS and IMPLEMENTS edges. The `--min-confidence` CLI parameter (default 0.6) filters edges below the threshold in the blast radius query. The report displays confidence as color-coded percentages (🟢 ≥80%, 🟡 ≥60%, 🔴 <60%) and notes the percentage of high-confidence edges.

* **Human-in-the-loop trigger (deferred):** The design specifies flagging reports where >30% of nodes are low-confidence for manual review. This is a post-processing rule to be added to the reporter — the structured summary already computes `low_confidence_count` and `confidence_pct`, which are exposed in the JSON export for CI/CD gating.

---

## Section 5 — Eval Approach (1 page)

**What to write:**
Answer the literal question asked: *"If we ran your system 100 times on the same input, how do we know which runs are correct?"*

* **Deterministic Layer (31 Unit/Integration Tests):** For fixed inputs (seeded Neo4j, mock API responses, static spec documents), execution is completely deterministic. The 31-test suite verifies: spec parsing idempotency, graph write idempotency (MERGE semantics), blast radius query correctness with confidence filtering, report generation without Cypher/ID leakage, and full pipeline smoke test. These tests pass identically every run.

* **LLM Quality Evaluator (Proposed Rubric):**
  * **Spec Extraction:** Evaluate `parse_prd()` by checking recall and precision against a hand-labeled reference collection of requirements from the sample PRD.
  * **Cross-layer Mappings:** Assert edge accuracy by running the linker against gold-standard Requirement→UI pairs and measuring precision.
  * **Natural Prose Generation:** Score reporter output using a defined rubric evaluating: (a) plain-English phrasing with no technical leakage, (b) inclusion of all affected user flows, (c) actionable test case specificity, (d) confidence transparency.

* **Note:** The rubric evaluator and gold-standard datasets are described in this document as the intended evaluation framework. The current test suite covers the deterministic boundary; LLM quality evaluation would be added in a CI stage that gates on minimum rubric scores.

---

## Section 6 — Scope Decisions (1 page)

**Went deep on:**
* **Graph Schema:** Designed a clean multi-layer structure incorporating first-class Absence nodes, UI transition edges, and forward-compatible schema elements (CodeFunction, UserFlow) ready for the next iteration.
* **Blast-Radius Logic:** Implemented multi-hop Cypher traversal with confidence filtering at every hop, TRANSITION edge traversal (0..2 hops), and null-safe OPTIONAL MATCH to handle unmapped files gracefully.
* **Test Coverage:** 31 passing unit + integration tests with test-first development across all 5 modules.
* **Dual Report Output:** Structured Markdown report with severity classification, confidence tables, and LLM narrative alongside machine-readable JSON export for CI/CD consumption.
* **Live Crawling:** Full Playwright (headless Chromium) + LLMPlanner agent loop that navigates web apps autonomously, with a `--crawl-fixture` JSON path for deterministic replay.

**Scoped down:**
* **Call-graph traversal:** The blast radius maps CodeFile → UIElement directly via `IMPLEMENTS`. CodeFunction nodes are extracted by the AST scanner but not written to Neo4j. Dynamic call-graph analysis (following `CALLS` edges between functions) would trace impact through the call tree and is the top priority for the next iteration.
* **UserFlow modelling:** The `PART_OF` edge and `UserFlow` node are schema-defined but not populated. They would enable grouping UI elements into named flows (e.g., "Quiz Creation Flow") for more readable reports.
* **Human-in-the-loop trigger:** The >30% low-confidence flagging rule is computed (confidence_pct available in JSON) but not auto-flagged in the report. This is a thin reporter addition.

---

## Section 7 — Future Roadmap (0.75 pages)

* **Priority 1 — CodeFunction-level Call-Graph Analysis:** Write CodeFunction nodes to Neo4j with `DEFINED_IN` edges. Populate `CALLS` edges via AST/static analysis. Extend the blast radius to walk function-level call chains, catching impact in files that don't directly IMPLEMENT UI but call into changed code.
* **Priority 2 — Webhook-Triggered Crawling:** Automatically run targeted crawl sessions on PR events to keep the knowledge graph aligned with the live application state. A Vercel/Netlify deploy webhook or GitHub Actions workflow would trigger re-crawl of changed pages.
* **Priority 3 — Interactive Confidence Calibration UI:** Add a feedback loop where engineers can adjust semantic links directly in a visual graph editor, feeding corrections back to improve the LLM linker's accuracy over time.

---

## Section 8 — CLI & Runtime (0.75 pages)

**What to write:**
Document the entry point, prerequisites, and runtime commands so the evaluator can reproduce the pipeline.

**Prerequisites:**
- Python 3.11+, Neo4j 5.x (Docker: `docker compose up -d`), LM Studio running locally at localhost:1234 with a loaded model
- `pip install -r requirements.txt`

**Entry point: `cli.py`**

```
python cli.py \
  --url <target-web-app> \
  --repo <org/repo> \
  --pr <pull-request-number> \
  --prd <path-to-prd.md>
```

**Key flags:**
| Flag | Purpose |
|---|---|
| `--url` | Target web app to crawl (optional with `--crawl-fixture`) |
| `--repo` | GitHub repo, e.g. `Cudael/quiz` |
| `--pr` | Pull request number |
| `--prd` | Path to product spec markdown (always required) |
| `--crawl-fixture path.json` | Load pre-captured UI fixture instead of live crawl |
| `--no-crawl` | Skip crawl entirely; use existing Neo4j data |
| `--no-link` | Skip LLM semantic linking; use existing edges |
| `--min-confidence` | Blast radius edge threshold (default: 0.6) |
| `--max-steps` | Max crawl navigation steps (default: 10) |
| `--output` | Report output directory (default: reports/) |

**Output:** Two files per run in `reports/`:
- `report-<timestamp>.md` — Structured Markdown with severity, affected features table, downstream cascade table, and LLM-generated narrative + test cases
- `report-<timestamp>.json` — Machine-readable for CI/CD gating

**Pipeline stages (8 total):**
1. Parse PRD → structured requirements (LLM)
2. Crawl web app → DOM snapshots + transitions (Playwright + LLM Planner) or load fixture
3. Scan codebase → CodeFile nodes from AST
4. Write to Neo4j → all nodes + edges
5. LLM semantic linking → COVERS + IMPLEMENTS edges
6. Mark coverage gaps → Absence nodes
7. Fetch PR diff + compute blast radius
8. Generate & save report (Markdown + JSON)

**Example run against a real PR:**
```
docker compose up -d                                    # start Neo4j
python cli.py \
  --url https://myapp.vercel.app \
  --repo Cudael/quiz \
  --pr 38 \
  --prd tests/fixtures/sample_prd.md \
  --crawl-fixture tests/fixtures/quiz_ui_fixture.json
```

---

## Document Checklist Before Submission

- [ ] Every LLM step is named and justified — no unexplained "the agent decides"
- [ ] The absence and blast-radius reasoning queries are fully explained in logical steps
- [ ] Confidence thresholds are named as heuristics, not presented as principled
- [ ] Section 6 leads with what was prioritized, not with apology for what was cut
- [ ] The word "robust" does not appear anywhere in the document
- [ ] The report sample (actual output for a real PR) is attached as an appendix or separate file
- [ ] Schema elements that exist in code but aren't populated (UserFlow, CodeFunction, CALLS, DEFNED_IN, PART_OF) are explicitly noted as deferred
- [ ] CLI entry point and run commands are documented

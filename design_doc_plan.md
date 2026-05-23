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

**Scope statement goes here, not buried in a footnote.** One sentence: "I went deep on the Graph and Reason layers. The Crawl layer uses a fixture after one real run. This is a deliberate choice, explained in Section 6."

---

## Section 2 — Agent Decomposition (1.5 pages)

**What to write:**
Define the five distinct stages. For each stage, state explicitly: is it deterministic or LLM-driven? Why?

| Stage | Deterministic or LLM | Justification |
|---|---|---|
| PR fetch + diff parse | Deterministic | GitHub API is structured; no ambiguity to resolve |
| PRD parse → Requirement structs | LLM | Unstructured markdown; intent and section boundaries require semantic reading |
| UI crawl → DOM + transitions | Deterministic + LLM Planner | Mechanics are deterministic; deciding navigation steps requires reasoning |
| Requirement ↔ UI linking | LLM | Judging similarity between prose specs and DOM elements requires language processing |
| Blast radius report generation | LLM | The output must be converted into non-technical plain-English text |

**The argument this section must make:** This is not a chain of prompts. LLM is used only where a deterministic rule genuinely cannot do the job. Detail what the deterministic parts do — file parsing, graph structures, diff extraction, JSON serialization, graph writes. The LLM touches exactly three things: parsing intent from text, judging semantic similarity, and writing prose. Everything else is code.

**What to avoid:** Do not list "I use LangChain for the agent loop" as if that answers the decomposition question. The reviewer is checking whether you know *where* the reasoning boundary is, not what library you used.

---

## Section 3 — Graph Schema with Justification (2.5 pages)

**What to write:**
This section needs to earn its length. Three parts:

**Part A — Node and edge catalogue**

| Node type | Key properties | Layer |
|---|---|---|
| `Requirement` | id, title, source_section, raw_text | Requirements |
| `Absence` | reason, confidence, created_at | Requirements |
| `UIElement` | id, selector, label, url, element_type | UI/DOM |
| `UserFlow` | id, name, start_url, steps (list) | UI/DOM |
| `CodeFile` | path, language, last_modified | Code |
| `CodeFunction` | name, file_path, start_line, end_line | Code |

| Edge type | From → To | Key properties |
|---|---|---|
| `COVERS` | Requirement → UIElement | confidence (0–1) |
| `HAS_ABSENCE` | Requirement → Absence | — |
| `PART_OF` | UIElement → UserFlow | step_order |
| `IMPLEMENTS` | CodeFile → UIElement | confidence (0–1) |
| `CALLS` | CodeFunction → CodeFunction | — |
| `DEFINED_IN` | CodeFunction → CodeFile | — |
| `TRANSITION` | UIElement → UIElement | action (str), selector (str) |

**Part B — How absence is modelled**

* **Post-processing Goal:** Identify all `Requirement` nodes that have no outgoing `COVERS` edges to any `UIElement`. For each found gap, write an `Absence` node containing the crawl verification context (reason description, zeroed confidence, timestamp) and link it via a `HAS_ABSENCE` relationship.
* **Schema Importance:** Modeling absence as an independent node rather than a boolean flag on requirements allows us to track unique parameters (e.g., crawl execution timestamps, specific detection reasons) and query missed coverages in isolation.

**Part C — The query that justifies the schema**

* **Blast-Radius Query Logic:**
  * **Scope Search:** Start with CodeFile nodes affected by changed files from a Pull Request.
  * **Traverse Code Structure:** Locate functions defined within the affected files.
  * **Trace to UI Layer:** Follow the `IMPLEMENTS` edge to matching UIElements, filtering by a configurable confidence parameter.
  * **Propagate Downstream Impacts:** Traverse up to two hops along screen `TRANSITION` edges to capture subsequent UI nodes affected by modifying the initial component.
  * **Link to Product Intent:** Trace back to Requirements (both directly affected and downstream) along `COVERS` edges, applying confidence filters.
  * **Expose Untested Risks:** Query any `Absence` nodes linked to these requirements.
  * **Aggregate Results:** Return distinct UI elements, direct user flows, requirements, and absence details.

---

## Section 4 — Confidence Handling under Ambiguity (1.5 pages)

**What to write:**
Three specific failure modes and how each is handled.

* **Failure mode 1: Code change touches an unmapped file**
  * *Handling Goal:* Utilize optional matches in queries to prevent execution errors on missing links. Flag the unmapped modules in the report for manual structural analysis.
* **Failure mode 2: Mismatched requirements (Absent Features)**
  * *Handling Goal:* Generate an `Absence` node. If a changed code path maps to a flow that depends on this absent feature, surface the untested coverage risk in the non-technical report.
* **Failure mode 3: Borderline semantic matches**
  * *Handling Goal:* Store confidence scores on edges. Apply configurable thresholds in the calculation engine to treat low-confidence elements as possible (but unconfirmed) risks.
* **Human-in-the-loop trigger:** Flag any reports where the ratio of unconfirmed or low-confidence nodes exceeds 30% as needing structural review.

---

## Section 5 — Eval Approach (1 page)

**What to write:**
Answer the literal question asked: *"If we ran your system 100 times on the same input, how do we know which runs are correct?"*

* **Deterministic Layer (Unit/Integration Checks):** For inputs where mock variables are static (e.g., seeded databases, mock API responses, test spec documents), execution must be completely deterministic, achieving identical output patterns in every run.
* **LLM Quality Evaluator (Rubric Scoring):**
  * **Spec Extraction:** Evaluate parsing by checking recall and precision metrics against a hand-labeled reference collection of requirements.
  * **Cross-layer Mappings:** Assert edge accuracy against static gold-standard links.
  * **Natural Prose Generation:** Score reports using a defined rubric evaluating plain-English phrasing, inclusion of user flows, and coverage of confidence warnings.

---

## Section 6 — Scope Decisions (1 page)

**Went deep on:**
* **Graph Schema:** Designing a clean multi-layer structure incorporating first-class Absence nodes and UI transition states.
* **Blast-Radius Logic:** Crafting advanced Cypher traversals incorporating threshold filtering and screen navigations.
* **Test Coverage:** Adhering to a strict test-first plan for reliable execution.

**Scoped down:**
* **Live crawling:** Mocked dynamic navigation runs in favor of structured JSON fixtures to prevent execution volatility.
* **Call-graph extraction:** Utilized static code-to-feature indexes rather than dynamic call traces.

---

## Section 7 — Future Roadmap (0.75 pages)

* **Priority 1 — Webhook Crawling:** Automatically trigger targeted crawl runs on PR notifications to keep graph components aligned.
* **Priority 2 — Call-Graph Analysis:** Parse code definitions to build function call hierarchies dynamically.
* **Priority 3 — Accuracy Calibration:** Add a feedback loop allowing engineers to adjust semantic links directly in a UI.

---

## Document Checklist Before Submission

- [ ] Every LLM step is named and justified — no unexplained "the agent decides"
- [ ] The absence and blast-radius reasoning queries are fully explained in logical steps
- [ ] Confidence thresholds are named as heuristics, not presented as principled
- [ ] Section 6 leads with what was prioritized, not with apology for what was cut
- [ ] The word "robust" does not appear anywhere in the document
- [ ] The report sample (actual output for a real PR) is attached as an appendix or separate file
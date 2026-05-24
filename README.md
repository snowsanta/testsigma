# TestSigma — Autonomous Risk Analysis Agent

> **Given a code change (PR), what user-facing features can break?**

An agent that crawls a web application, ingests a product spec, builds a Neo4j knowledge graph across three layers (Requirements → UI → Code), and uses that graph to produce a plain-English QA risk report when code changes.

---

## Architecture

```
[PRD Markdown]                              [GitHub PR]
      │                                          │
      ▼                                          │
┌──────────┐                                     │
│  INGEST  │                                     │
│  parser  │                                     │
└────┬─────┘                                     │
     │                                            │
     ▼                                            ▼
┌──────────────────────────────────────────┐  ┌──────────────────┐
│            GRAPH LAYER (Neo4j)           │  │   PR FETCHER     │
│  Requirement ─COVERS──► UIElement        │  │  (GitHub API)    │
│  CodeFile ─IMPLEMENTS─► UIElement        │  └────────┬─────────┘
│  UIElement ─TRANSITION─► UIElement       │           │
│  Requirement ─HAS_ABSENCE─► Absence      │           │
└──────────────┬───────────────────────────┘           │
               │                                       │
               ▼                                       ▼
┌──────────────────────────────────────────────────────┐
│                  REASON ENGINE                       │
│               Blast radius query                     │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌──────────────────────┐
│   REPORTER (LLM)     │
│  English risk report │
└──────────────────────┘
```

Five stages, clearly bounded by what's deterministic and what's LLM-driven:

| Stage | Type | What It Does |
|---|---|---|
| PR fetch + diff parse | Deterministic | GitHub REST API → list of changed file paths |
| PRD parse → Requirements | LLM | Unstructured markdown → structured requirement objects |
| UI crawl → DOM elements | Deterministic + LLM Planner | Playwright navigation, HTML parsing |
| Requirement ↔ UI linking | LLM | Semantic similarity scoring → COVERS edges |
| Blast radius report | LLM | Structured risk data → plain-English prose |

The LLM touches exactly three things: parsing intent, judging semantic similarity, and writing prose. Everything else is pure code.

---

## Project Structure

```
├── src/
│   ├── ingest/               # Parse PRDs into structured requirement models
│   │   ├── models.py             # Requirement, CodeFile dataclasses
│   │   └── parser.py             # Markdown PRD → List[Requirement] via LLM
│   │
│   ├── crawl/                # Browser automation to capture UI/DOM
│   │   ├── artifacts.py          # DOMSnapshot, Transition, CrawlArtifactBundle
│   │   └── browser_agent.py      # Playwright + LLMPlanner agent loop
│   │
│   ├── graph/                # Neo4j knowledge graph read/write
│   │   ├── schema.py             # Node/edge type constants (5 nodes, 5 edges)
│   │   ├── writer.py             # MERGE-based idempotent writes
│   │   ├── reader.py             # Multi-hop blast-radius Cypher queries
│   │   ├── linker.py             # LLM semantic matching → COVERS + IMPLEMENTS edges
│   │   └── absence.py            # Post-processing: detect uncovered requirements
│   │
│   ├── reason/               # Risk reasoning engine
│   │   ├── pr_fetcher.py         # GitHub REST API → PR with changed files
│   │   ├── blast_radius.py       # Coordinates graph queries → BlastRadiusResult
│   │   └── reporter.py           # BlastRadiusResult → plain-English narrative
│   │
│   └── llm/                  # Single LLM boundary point
│       └── client.py             # Thin complete() wrapper (the only LLM call site)
│
├── tests/
│   ├── conftest.py               # Shared fixtures (mock LLM, mock Neo4j)
│   ├── fixtures/
│   │   └── sample_prd.md         # 6-requirement sample PRD
│   ├── ingest/                   # 5 tests for models, parser
│   ├── crawl/                    # 6 tests for artifacts, browser agent
│   ├── graph/                    # 10 tests for writer, reader
│   ├── reason/                   # 7 tests for PR fetcher, blast radius, reporter
│   └── integration/
│       └── test_end_to_end.py    # Full pipeline smoke test
│
├── manual_test_pipeline.py       # Zero-dependency interactive test harness
├── requirements.txt
└── coding_plan.md
```

---

## Graph Schema

### Node Types

| Node | Key Properties | Layer |
|---|---|---|
| `Requirement` | id, title, source_section, raw_text | Requirements |
| `Absence` | reason, confidence, created_at | Requirements |
| `UIElement` | id, selector, label, url, element_type | UI/DOM |
| `UserFlow` | id, name, start_url, steps | UI/DOM |
| `CodeFile` | path, language, last_modified | Code |

### Edge Types

| Edge | From → To | Properties |
|---|---|---|
| `COVERS` | Requirement → UIElement | confidence (0–1) |
| `HAS_ABSENCE` | Requirement → Absence | — |
| `PART_OF` | UIElement → UserFlow | step_order |
| `IMPLEMENTS` | CodeFile → UIElement | confidence (0–1) |
| `TRANSITION` | UIElement → UIElement | action, selector |

### Absence Modeling

Requirements with no matching UI coverage get an `Absence` node linked via `HAS_ABSENCE`. This makes them queryable as first-class entities rather than buried as boolean flags, enabling reports like "3 requirements have no testable UI — here's what they are."

### Blast Radius Query (Multi-Hop)

1. Start from `CodeFile` nodes in the PR's changed file list
2. Follow `IMPLEMENTS` → to linked `UIElement` nodes (confidence ≥ threshold)
3. Follow `COVERS` ← to affected `Requirement` nodes
4. Traverse `TRANSITION*0..2` → downstream `UIElement` nodes
5. Follow `COVERS` ← to downstream `Requirement` nodes
6. Check `HAS_ABSENCE` for coverage gaps
7. Aggregate distinct results

---

## Quick Start

### Prerequisites

- Python 3.11+
- Neo4j 5.x (via Docker or local install)
- OpenAI API key / LM studio setup (for LLM calls)

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd testsigma-assignment

# Create and activate virtual environment
python -m venv testsigma
source testsigma/bin/activate   # Linux/macOS
testsigma\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# Install Neo4j driver
pip install neo4j

# Start Neo4j (Docker)
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."
```

### Zero-Dependency Quick Test

Run the in-memory test harness — no Neo4j, no API keys, no Docker required:

```bash
python manual_test_pipeline.py
```

This walks you through the full pipeline interactively:
1. Parses `tests/fixtures/sample_prd.md` into structured requirements
2. Lists available source files in `src/` for PR simulation selection
3. Seeds a simulated graph with Requirements, UIElements, COVERS edges, IMPLEMENTS edges, and TRANSITION edges
4. Lets you pick which file to simulate as changed in a PR
5. Computes the blast radius
6. Generates a plain-English QA risk report

### Running the CLI

You can execute the complete automated risk assessment pipeline via the command-line utility `cli.py`:

```bash
python cli.py \
  --url <target-web-app-url> \
  --repo <org/repo> \
  --pr <pull-request-number> \
  --prd <path-to-prd.md> \
  --crawl-fixture <path-to-fixture.json>
```

#### LLM Provider Configuration (LM Studio vs OpenAI)

By default, the pipeline connects to a local **LM Studio** instance at `http://localhost:1234`. You can seamlessly redirect completions to **OpenAI (ChatGPT)** or specify customized model engines and URLs using the following command-line arguments:

* `--llm-provider`: LLM backend to utilize: `lm-studio` (default) or `openai`.
* `--openai-api-key`: Specifies your OpenAI API key (falls back to the `OPENAI_API_KEY` environment variable if omitted).
* `--llm-model`: Optional. Specifies a model name. When omitted with LM Studio and a single model loaded, the loaded model is auto-selected. For OpenAI, defaults to `gpt-4o`.
* `--llm-url`: Overrides the target completions URL (useful for local gateways, custom hosting, or OpenAI proxies).

**Example using local LM Studio with live crawl:**
```bash
python cli.py \
  --url https://quiz.cudael.dev \
  --repo Cudael/quiz \
  --pr 38 \
  --prd tests/fixtures/sample_prd.md \
  --llm-provider lm-studio
```

**Example using a pre-captured crawl fixture (debug/demo):**
```bash
python cli.py \
  --repo Cudael/quiz \
  --pr 38 \
  --prd tests/fixtures/sample_prd.md \
  --crawl-fixture tests/fixtures/quiz_ui_fixture.json \
  --llm-provider lm-studio
```

**Example using ChatGPT (OpenAI):**
```bash
python cli.py \
  --repo Cudael/quiz \
  --pr 38 \
  --prd tests/fixtures/sample_prd.md \
  --crawl-fixture tests/fixtures/quiz_ui_fixture.json \
  --llm-provider openai \
  --openai-api-key "sk-proj-..." \
  --llm-model "gpt-4o"
```

### Running Tests

```bash
# All tests (30 tests)
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/ -v -m "not integration"

# Specific module
python -m pytest tests/graph/ -v
```

---

## Confidence Handling

The system handles three failure modes:

| Failure Mode | Handling |
|---|---|
| **Unmapped file changed** | OPTIONAL MATCH in Cypher prevents errors; unmapped modules flagged in report |
| **Requirement not found in UI** | `Absence` node created; surfaced in report as uncovered risk |
| **Borderline semantic match** | Confidence stored on edges; filtered by configurable `min_confidence` threshold |

**Human-in-the-loop trigger:** Reports where >30% of nodes are low-confidence are flagged for manual review.

---

## Scope Decisions

**Went deep on:**
- Graph schema (5 node types, 5 edge types, absence as first-class node)
- Blast-radius logic (multi-hop Cypher with confidence filtering, transition traversal)
- Test coverage (30 tests across 5 modules, test-first development)

**Scoped down:**
- Live crawling — the browser agent uses a `--crawl-fixture` flag for debug/demo reliability; pass `--url` without `--crawl-fixture` for a live Playwright crawl
- Function-level call-graph tracing — uses file-level IMPLEMENTS edges rather than function-level CALLS/DEFINED_IN traversal

This is deliberate. The assignment explicitly states: *"A submission that goes deep on two layers and explicitly scopes the third beats a submission that does all three shallowly."*

---

## Eval Approach

If the system is run 100 times on the same input:

- **Deterministic layers** (PR fetch, graph writes, Cypher queries): produce identical output every run — verified by 30 unit/integration tests
- **LLM layers** (PRD parsing, semantic linking, report prose): scored via rubric evaluating recall/precision against gold-standard references, plain-English quality, and confidence transparency **(TODO: Currently conceptual framework; see Future Roadmap)**

---

## What I'd Build Next (With Another Week)

1. **Webhook-triggered live crawling** — automatically re-crawl on PR events to keep the graph aligned with the live application state
2. **Dynamic call-graph analysis** — parse function call trees to trace code impact beyond file-level mapping
3. **Interactive confidence calibration UI** — let engineers adjust semantic links directly in a visual graph editor, feeding back into the model's accuracy
4. **Automated LLM Evaluation Suite (TODO)** — implement the conceptual precision/recall rubric scoring and gold-standard dataset comparisons as an automated CI/CD gate to systematically measure parsing and linking performance.

---

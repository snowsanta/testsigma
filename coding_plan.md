# Coding Plan — Testsigma AI Engineer Assignment
> UT-first: every module gets its test objectives defined before its implementation. Tests define the contract; implementation satisfies it.

---

## Stack & Tooling

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11 | LangChain, Neo4j driver, Playwright all first-class |
| Test runner | `pytest` + `pytest-asyncio` | async-native, fixture system handles Neo4j lifecycle |
| LLM boundary | `unittest.mock.patch` on the LLM wrapper | keeps 100% of business logic testable without API calls |
| Graph DB | Neo4j 5 via Docker | zero signup, `docker-compose up` is the full setup |
| Browser agent | Playwright + GPT-4o via LangChain tool | explicit over magic; easier to stub in tests |
| HTTP mocking | `respx` or `responses` | mock GitHub API and PRD fetch calls |

---

## Repository Layout

```
testsigma-assignment/
├── docker-compose.yml          # Neo4j + app
├── .env.example
├── README.md
│
├── src/
│   ├── crawl/
│   │   ├── __init__.py
│   │   ├── browser_agent.py    # Playwright + LLM tool loop
│   │   └── artifacts.py        # DOM snapshot, screenshot, transition structs
│   │
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── parser.py           # README/PRD → structured requirements
│   │   ├── code_parser.py      # Repository scanner (extract file paths, function signatures)
│   │   └── models.py           # Requirement, CodeFile, and CodeFunction dataclasses
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── schema.py           # Node/edge type constants
│   │   ├── writer.py           # Write nodes + edges to Neo4j
│   │   ├── reader.py           # Query helpers (blast radius, coverage)
│   │   └── absence.py          # Absence node creation logic
│   │
│   ├── reason/
│   │   ├── __init__.py
│   │   ├── pr_fetcher.py       # GitHub API → PR diff struct
│   │   ├── blast_radius.py     # Graph queries → risk structs
│   │   └── reporter.py         # Risk structs → plain-English report (LLM)
│   │
│   └── llm/
│       ├── __init__.py
│       └── client.py           # Thin wrapper — THE ONLY place that calls Anthropic/OpenAI
│
└── tests/
    ├── conftest.py             # Neo4j test fixtures, shared mocks
    ├── crawl/
    │   ├── test_artifacts.py
    │   └── test_browser_agent.py
    ├── ingest/
    │   ├── test_parser.py
    │   ├── test_code_parser.py
    │   └── test_models.py
    ├── graph/
    │   ├── test_writer.py
    │   └── test_reader.py
    ├── reason/
    │   ├── test_pr_fetcher.py
    │   ├── test_blast_radius.py
    │   └── test_reporter.py
    └── integration/
        └── test_end_to_end.py
```

---

## Module 1 — `ingest`

### Test Objectives

* **`tests/ingest/test_models.py`**
  * **Fields Validation:** Assert that a `Requirement` node possesses essential properties (ID, title, source documentation section, raw text).
  * **Idempotent Deduplication Support:** Verify that `Requirement` nodes are hashable to enable duplicate filtering.
  * **Code Layer Models:** Verify that `CodeFile` and `CodeFunction` schemas support paths, function names, lines, and file-level metrics.

* **`tests/ingest/test_parser.py`**
  * **Markdown Requirement Extraction:** Verify that the spec parser successfully extracts requirements from Markdown text, converting them into structured models.
  * **Deduplication Logic:** Assert that duplicate feature lines or definitions are filtered during the parsing run.
  * **Null Inputs:** Assert that empty spec files return a safe, empty array without exceptions.
  * **Metadata Tracking:** Verify that section headers (e.g., "Security", "User Operations") are correctly mapped onto each requirement.

* **`tests/ingest/test_code_parser.py`**
  * **Repository Scanning:** Assert that directory traversals identify and filter target source code files.
  * **Signature Extraction:** Verify that AST visitors identify function definitions and map them correctly back to their containing modules.

### Implementation Details
* `parser.py` parses unstructured requirements utilizing a structured LLM call (mocked in tests via unit patching).
* `code_parser.py` walks code trees and builds abstract syntax trees using the `ast` library to inventory files and functions.

---

## Module 2 — `crawl`

### Test Objectives

* **`tests/crawl/test_artifacts.py`**
  * **DOM Serialization:** Verify that DOM snapshots serialize and deserialize cleanly to dictionaries.
  * **Interactive Element Detection:** Assert that parser filters successfully isolate elements (buttons, anchors, inputs).
  * **Transition Linking:** Verify that a transition records details of moving from one DOM snapshot URL to a target URL.
  * **Bundle Export:** Assert that entire crawler artifact bundles are fully JSON-serializable for system exports.

* **`tests/crawl/test_browser_agent.py`**
  * **Execution Thresholds:** Assert that the crawl loop terminates upon hitting specified step counts.
  * **Bundle Generation:** Verify that execution returns structured snapshots and transitions.

### Implementation Details
* `BrowserAgent` manages dynamic Playwright navigations guided by LLM choices, outputting transition objects.
* Scoped down for the initial submission run to read from a pre-captured JSON crawl fixture.

---

## Module 3 — `graph`

### Test Objectives

* **`tests/graph/test_writer.py`**
  * **Requirement Storage:** Verify that writing a requirement creates a node in Neo4j with properties.
  * **Idempotent Graph Writes:** Assert that writing the same requirement twice does not duplicate nodes.
  * **UI Node Writes:** Verify that browser DOM snapshots successfully compile into database `UIElement` nodes.
  * **Requirements to UI Links:** Verify that the `COVERS` edge is written between requirements and elements, correctly storing semantic confidence scores.
  * **Absence Node Generation:** Assert that requirements unmatched by any UI elements trigger the creation of `Absence` nodes linked via `HAS_ABSENCE` edges.
  * **Code Layer Writing:** Verify that `CodeFile` and `CodeFunction` nodes are safely registered.
  * **Code to UI Linking:** Assert that `IMPLEMENTS` edges link files to matching interface elements with confidence properties.
  * **Page Transitions:** Assert that `TRANSITION` edges are written between consecutive screen UI components to represent user paths.

* **`tests/graph/test_reader.py`**
  * **Code to UI Fetching:** Assert that queries return all UI element nodes connected to a given file.
  * **Impacted Requirements Listing:** Verify that the reader calculates requirements that lose UI coverage for a list of UI elements.
  * **Unlinked File Blast Radius:** Assert that file paths with no database links return empty lists safely.
  * **Absence Detection in Impacts:** Verify that blast-radius calculations successfully report associated `Absence` states.
  * **Confidence Filtering:** Assert that reasoning queries exclude edges whose scores fall below a parameter threshold.

### Implementation Details
* `writer.py` relies on Neo4j Cypher queries using `MERGE` actions to ensure database write idempotency.
* `reader.py` exposes optimized queries for blast-radius calculations.
* `absence.py` triggers post-processing traversals to map gaps.

---

## Module 4 — `reason`

### Test Objectives

* **`tests/reason/test_pr_fetcher.py`**
  * **Diff Extraction:** Assert that parsing PR targets produces accurate lists of changed file paths.
  * **Error Resilience:** Verify that API failures or missing repositories raise dedicated error exceptions.

* **`tests/reason/test_blast_radius.py`**
  * **Calculation Coordination:** Assert that the engine queries the graph session using parameters for changed files.
  * **Output Struct Serialization:** Assert that calculated raw blast-radius result structures serialize to dictionaries.

* **`tests/reason/test_reporter.py`**
  * **Narrative Generation:** Verify that reports generate readable, human-friendly prose.
  * **Technical Abstraction:** Assert that plain-English output does not leak Cypher queries or node IDs.
  * **Null Changes Handle:** Verify that zero-change inputs yield clear, safe reports.

### Implementation Details
* `pr_fetcher.py` extracts metadata using target repository HTTP queries.
* `blast_radius.py` coordinates database reads and builds intermediate analysis structures.
* `reporter.py` utilizes prompts to convert tabular query output into clean prose.

---

## Module 5 — `llm/client.py`

### Implementation Details
* Provides a thin wrapper exposing the LLM invocation interface. All downstream packages patch calls at this wrapper boundary.

---

## Integration Test

* **`tests/integration/test_end_to_end.py`**
  * **Full Pipeline Test:**
    * Run parsing logic on spec Markdown fixtures.
    * Seed the Neo4j database with parsed requirements and pre-captured crawl snapshots.
    * Execute code mappings and absence analysis steps.
    * Execute a blast-radius query based on a mock Pull Request structure.
    * Verify that the system generates a structured report containing plaintext descriptions of affected flows and requirements.
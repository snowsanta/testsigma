#!/usr/bin/env python3
"""TestSigma Autonomous Risk Analysis Agent — CLI Entry Point"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests
from neo4j import GraphDatabase

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.ingest.parser import parse_prd
from src.ingest.code_parser import scan_repository
from src.crawl.browser_agent import BrowserAgent
from src.crawl.artifacts import CrawlArtifactBundle, DOMSnapshot
from src.graph.writer import (
    write_requirement,
    write_ui_element,
    write_code_file,
    write_transition_edge,
)
from src.graph.linker import link_requirements_to_ui, link_code_to_ui
from src.graph.absence import mark_all_absences
from src.reason.pr_fetcher import fetch_pr, PRNotFoundError
from src.reason.blast_radius import BlastRadiusEngine
from src.reason.reporter import generate_report, save_report, save_report_json


import src.llm.client

def parse_args():
    p = argparse.ArgumentParser(description="TestSigma Risk Analysis Agent")
    p.add_argument("--url", help="Target web app URL to crawl (optional with --crawl-fixture)")
    p.add_argument("--repo", required=True, help="GitHub repo (e.g. org/repo)")
    p.add_argument("--pr", required=True, type=int, help="Pull request number")
    p.add_argument(
        "--prd",
        required=True,
        help="Path to PRD markdown file (e.g. tests/fixtures/sample_prd.md)",
    )
    p.add_argument("--max-steps", type=int, default=10, help="Max crawl steps (default: 10)")
    p.add_argument("--min-confidence", type=float, default=0.6, help="Blast radius confidence threshold (default: 0.6)")
    p.add_argument("--output", default="reports", help="Report output directory (default: reports/)")
    p.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    p.add_argument("--neo4j-user", default="neo4j")
    p.add_argument("--neo4j-password", default="password")
    p.add_argument("--no-crawl", action="store_true", help="Skip browser crawl (use existing graph data)")
    p.add_argument("--crawl-fixture", help="Path to JSON crawl fixture file (bypasses live crawl)")
    p.add_argument("--no-link", action="store_true", help="Skip LLM semantic linking (use existing edges)")
    
    # New LLM Provider configuration arguments
    p.add_argument("--llm-provider", choices=["lm-studio", "openai"], default="lm-studio", help="LLM backend provider (default: lm-studio)")
    p.add_argument("--openai-api-key", help="OpenAI API key (can also be set via OPENAI_API_KEY env variable)")
    p.add_argument("--llm-model", help="LLM model name (default: gpt-4o or LM Studio default model)")
    p.add_argument("--llm-url", help="Custom endpoint URL for LLM completions API")
    return p.parse_args()


def check_lm_studio(url):
    models_url = url.rsplit("/", 2)[0] + "/models"
    try:
        r = requests.get(models_url, timeout=5)
        if r.status_code == 200:
            models = r.json().get("data", [])
            if models:
                print(f"[OK] LM Studio running - {len(models)} model(s) loaded")
            else:
                print("[OK] LM Studio running - no models loaded yet")
            return
    except requests.RequestException:
        pass
    print(f"[ERROR] LM Studio not reachable at {models_url}")
    print("        Start LM Studio, load a model, and ensure the server is running.")
    sys.exit(1)


def connect_neo4j(uri, user, password):
    driver = GraphDatabase.driver(uri, auth=(user, password))
    for attempt in range(1, 4):
        try:
            driver.verify_connectivity()
            print(f"[OK] Connected to Neo4j at {uri}")
            return driver
        except Exception:
            if attempt < 3:
                print(f"  Retrying Neo4j connection ({attempt}/3)...")
                time.sleep(2)
            else:
                print(f"[ERROR] Failed to connect to Neo4j at {uri}")
                driver.close()
                sys.exit(1)
    return driver


def main():
    args = parse_args()
    started = datetime.now()

    print("=" * 60)
    print("  TestSigma Autonomous Risk Analysis Agent")
    print("=" * 60)
    print(f"  Target URL:  {args.url}")
    print(f"  Repository:  {args.repo}")
    print(f"  PR Number:   #{args.pr}")
    print(f"  PRD File:    {args.prd}")
    print(f"  Output Dir:  {args.output}")
    print("-" * 60)

    # ── Prerequisites ────────────────────────────────────────────────────
    if args.llm_provider == "openai":
        url = args.llm_url or "https://api.openai.com/v1/chat/completions"
        model = args.llm_model or "gpt-4o"
        api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            print("[ERROR] OpenAI API Key is required. Provide it via --openai-api-key or set the OPENAI_API_KEY environment variable.")
            sys.exit(1)
    else:  # lm-studio
        url = args.llm_url or "http://localhost:1234/v1/chat/completions"
        model = args.llm_model or "gpt-4o"
        api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        check_lm_studio(url)

    src.llm.client.configure(url=url, model=model, api_key=api_key)
    driver = connect_neo4j(args.neo4j_uri, args.neo4j_user, args.neo4j_password)

    try:
        # ── Stage 1: Ingest PRD ──────────────────────────────────────────
        print("\n[Stage 1/8] Parsing PRD ...")

        if not os.path.exists(args.prd):
            print(f"[ERROR] PRD file not found: {args.prd}")
            sys.exit(1)

        with open(args.prd, "r", encoding="utf-8") as f:
            prd_content = f.read()

        requirements = parse_prd(prd_content)
        if not requirements:
            print("[WARN] No requirements extracted from PRD. Check LM Studio output.")
        else:
            print(f"  Parsed {len(requirements)} requirements:")
            for r in requirements:
                print(f"    [{r.id}] {r.title}")

        # ── Stage 2: Crawl Web App ───────────────────────────────────────
        if args.crawl_fixture:
            print(f"\n[Stage 2/8] Loading crawl fixture: {args.crawl_fixture}")
            with open(args.crawl_fixture, "r", encoding="utf-8") as f:
                fixture_data = json.load(f)
            fixtures_by_url = {}
            for elem in fixture_data:
                url = elem.get("url", "https://fixture.local/")
                fixtures_by_url.setdefault(url, []).append(elem)
            crawl_bundle = CrawlArtifactBundle(
                snapshots=[DOMSnapshot(url=url, html="", elements=elems, timestamp=time.time()) for url, elems in fixtures_by_url.items()],
                transitions=[],
            )
            print(f"  Loaded {len(fixture_data)} UI elements across {len(fixtures_by_url)} pages")
        elif not args.no_crawl:
            print(f"\n[Stage 2/8] Crawling {args.url} ...")
            agent = BrowserAgent(max_steps=args.max_steps)
            crawl_bundle = agent.run(args.url)
            print(f"  Captured {len(crawl_bundle.snapshots)} DOM snapshots, "
                  f"{len(crawl_bundle.transitions)} transitions")
        else:
            crawl_bundle = None
            print(f"\n[Stage 2/8] Crawl skipped (--no-crawl)")

        # ── Stage 3: Scan Codebase ──────────────────────────────────────
        print("\n[Stage 3/8] Scanning codebase ...")
        project_root = os.path.abspath(os.path.dirname(__file__))
        files, functions = scan_repository(project_root)
        project_files = [f for f in files if f.path.startswith("src")]
        print(f"  Found {len(project_files)} source files, {len(functions)} functions")

        # ── Stage 4: Write to Neo4j ──────────────────────────────────────
        print("\n[Stage 4/8] Writing to Neo4j ...")
        with driver.session() as session:
            if args.no_crawl:
                session.run("MATCH (n) DETACH DELETE n")
                print("  Wiped existing graph for clean run with --no-crawl")

            for req in requirements:
                write_requirement(session, req)

            for cf in project_files:
                write_code_file(session, cf)

            if crawl_bundle:
                for snap in crawl_bundle.snapshots:
                    for elem in snap.elements:
                        elem_id = elem["id"] or elem["selector"]
                        ui_element = type("UIElement", (), {
                            "id": elem_id, "selector": elem["selector"],
                            "label": elem["label"], "url": snap.url
                        })()
                        write_ui_element(session, ui_element)

                for trans in crawl_bundle.transitions:
                    from_id = _url_to_ui_id(trans.from_url, crawl_bundle)
                    to_id = _url_to_ui_id(trans.to_url, crawl_bundle)
                    if from_id and to_id:
                        write_transition_edge(
                            session, from_id, to_id,
                            action=trans.action,
                            selector=trans.element_selector
                        )

            ui_count = session.run("MATCH (u:UIElement) RETURN count(u) AS n").single()["n"]
            req_count = session.run("MATCH (r:Requirement) RETURN count(r) AS n").single()["n"]
            file_count = session.run("MATCH (c:CodeFile) RETURN count(c) AS n").single()["n"]
            print(f"  Graph: {req_count} reqs, {ui_count} UIs, {file_count} code files")

        # ── Stage 5: Semantic Linking (LLM) ─────────────────────────────
        if not args.no_link:
            print("\n[Stage 5/8] LLM semantic linking ...")
            with driver.session() as session:
                link_requirements_to_ui(session)
                link_code_to_ui(session)
                covers_count = session.run(
                    "MATCH ()-[c:COVERS]->() RETURN count(c) AS n"
                ).single()["n"]
                impl_count = session.run(
                    "MATCH ()-[i:IMPLEMENTS]->() RETURN count(i) AS n"
                ).single()["n"]
                print(f"  Created {covers_count} COVERS edges, {impl_count} IMPLEMENTS edges")
        else:
            print("\n[Stage 5/8] Linking skipped (--no-link)")

        # ── Stage 6: Mark Absences ───────────────────────────────────────
        print("\n[Stage 6/8] Marking coverage gaps ...")
        with driver.session() as session:
            mark_all_absences(session)
            absence_count = session.run(
                "MATCH (a:Absence) RETURN count(a) AS n"
            ).single()["n"]
            print(f"  Found {absence_count} requirement gaps (Absence nodes)")

        # ── Stage 7: Fetch PR & Compute Blast Radius ────────────────────
        print(f"\n[Stage 7/8] Fetching PR {args.repo}#{args.pr} ...")
        try:
            pr = fetch_pr(args.repo, args.pr)
            print(f"  PR #{pr.pr_number} — {len(pr.changed_files)} changed files")
            for f in pr.changed_files[:5]:
                print(f"    {f}")
            if len(pr.changed_files) > 5:
                print(f"    ... and {len(pr.changed_files) - 5} more")
        except PRNotFoundError:
            print(f"[ERROR] PR #{args.pr} not found in {args.repo}")
            sys.exit(1)

        # Seed PR's changed files as CodeFile nodes so blast radius can match
        from src.ingest.models import CodeFile as CodeFileModel
        with driver.session() as session:
            for filepath in pr.changed_files:
                ext = os.path.splitext(filepath)[1]
                lang = {".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
                        ".json": "JSON", ".md": "Markdown", ".env": "Env"}.get(ext, "Unknown")
                cf = CodeFileModel(path=filepath, language=lang)
                write_code_file(session, cf)
            print(f"  Seeded {len(pr.changed_files)} PR files into graph")

            # Re-run linker to wire PR's files → UI elements
            if not args.no_link:
                link_code_to_ui(session)
                impl_count = session.run(
                    "MATCH ()-[i:IMPLEMENTS]->() RETURN count(i) AS n"
                ).single()["n"]
                print(f"  Re-linked: {impl_count} total IMPLEMENTS edges")

        print("\n  Computing blast radius ...")
        with driver.session() as session:
            engine = BlastRadiusEngine(session=session)
            blast_result = engine.compute(pr, min_confidence=args.min_confidence)

        n_ui = len(blast_result.ui_elements_at_risk)
        n_req = len(blast_result.affected_requirements)
        n_dn_ui = len(blast_result.downstream_ui_elements)
        n_dn_req = len(blast_result.downstream_requirements)
        print(f"  Direct: {n_ui} UIs, {n_req} requirements")
        print(f"  Downstream: {n_dn_ui} UIs, {n_dn_req} requirements")

        # ── Stage 8: Generate & Save Report ──────────────────────────────
        print("\n[Stage 8/8] Generating risk report ...")
        report_text, structured = generate_report(blast_result)
        md_path = save_report(
            report_text,
            output_dir=args.output,
            repo=args.repo,
            pr_number=args.pr,
            target_url=args.url,
        )
        json_path = save_report_json(
            structured,
            output_dir=args.output,
            repo=args.repo,
            pr_number=args.pr,
            target_url=args.url,
        )
        print(f"  Markdown: {os.path.abspath(md_path)}")
        print(f"  JSON:     {os.path.abspath(json_path)}")

        # ── Summary ──────────────────────────────────────────────────────
        elapsed = (datetime.now() - started).total_seconds()
        print("\n" + "=" * 60)
        print(f"  Pipeline complete in {elapsed:.1f}s")
        print(f"  Reports:  {os.path.abspath(args.output)}/")
        print("=" * 60)

    finally:
        driver.close()


def _url_to_ui_id(url: str, bundle: CrawlArtifactBundle) -> str:
    for snap in bundle.snapshots:
        if snap.url == url and snap.elements:
            elem = snap.elements[0]
            return elem.get("id", "") or elem.get("selector", "")
    if bundle.snapshots and bundle.snapshots[0].elements:
        elem = bundle.snapshots[0].elements[0]
        return elem.get("id", "") or elem.get("selector", "")
    return ""


if __name__ == "__main__":
    main()

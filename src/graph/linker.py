import json
from src.graph.writer import write_covers_edge, write_implements_edge
import src.llm.client


def link_requirements_to_ui(session):
    """LLM-driven semantic matching of requirements to UI elements with confidence scores."""
    reqs = _fetch_all_requirements(session)
    uis = _fetch_all_ui_elements(session)

    if not reqs or not uis:
        return

    system_prompt = (
        "You are a product requirements analyst. Given a list of software requirements "
        "and a list of UI elements found on a web application, determine which UI elements "
        "likely implement or relate to each requirement. Respond with valid JSON only."
    )

    reqs_json = json.dumps(reqs, indent=2)
    uis_json = json.dumps(uis, indent=2)
    user_prompt = (
        f"Requirements:\n{reqs_json}\n\n"
        f"UI Elements found during crawl:\n{uis_json}\n\n"
        "For each requirement, list the UI element IDs that most closely relate to it "
        "based on semantic similarity between the requirement text and the UI element labels/purposes. "
        "Assign a confidence score (0.0-1.0).\n\n"
        "Respond with a JSON array:\n"
        '[{"req_id": "R1", "ui_ids": ["U1"], "confidence": 0.9}, ...]'
    )
    matches = _call_llm_and_parse(system_prompt, user_prompt)
    if not matches:
        return

    for match in matches:
        req_id = match.get("req_id")
        ui_ids = match.get("ui_ids", [])
        confidence = float(match.get("confidence", 0.5))
        if req_id and ui_ids:
            for ui_id in ui_ids:
                write_covers_edge(session, req_id, ui_id, confidence=confidence)


def link_code_to_ui(session):
    """LLM-driven matching of code files to the UI elements they implement."""
    code_files = _fetch_all_code_files(session)
    uis = _fetch_all_ui_elements(session)

    if not code_files or not uis:
        return

    system_prompt = (
        "You are a full-stack engineer. Given a list of source code file paths and "
        "a list of UI elements on a web application, determine which code files are "
        "most likely responsible for implementing each UI element. Respond with JSON only."
    )

    files_json = json.dumps(code_files, indent=2)
    uis_json = json.dumps(uis, indent=2)
    user_prompt = (
        f"Source code files:\n{files_json}\n\n"
        f"UI Elements found during crawl:\n{uis_json}\n\n"
        "For each UI element, list the code file paths that likely implement it "
        "based on typical naming conventions (e.g., a file named 'parser.py' might "
        "relate to a 'file upload' or 'import' UI element). Assign a confidence (0.0-1.0).\n\n"
        "Respond with a JSON array:\n"
        '[{"ui_id": "U1", "file_paths": ["src/ingest/parser.py"], "confidence": 0.85}, ...]'
    )
    matches = _call_llm_and_parse(system_prompt, user_prompt)
    if not matches:
        return

    for match in matches:
        ui_id = match.get("ui_id")
        file_paths = match.get("file_paths", [])
        confidence = float(match.get("confidence", 0.5))
        if ui_id and file_paths:
            for fp in file_paths:
                write_implements_edge(session, fp, ui_id, confidence=confidence)


def _call_llm_and_parse(system_prompt: str, user_prompt: str) -> list:
    response_str = src.llm.client.complete(system=system_prompt, user=user_prompt)
    try:
        cleaned = response_str.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return []


def _fetch_all_requirements(session) -> list:
    result = session.run("MATCH (r:Requirement) RETURN r")
    reqs = []
    for record in result:
        data = record.data() if hasattr(record, "data") else record
        node = data.get("r", data)
        reqs.append({
            "id": node.get("id", ""),
            "title": node.get("title", ""),
            "source_section": node.get("source_section", ""),
            "raw_text": node.get("raw_text", ""),
        })
    return reqs


def _fetch_all_ui_elements(session) -> list:
    result = session.run("MATCH (u:UIElement) RETURN u")
    uis = []
    for record in result:
        data = record.data() if hasattr(record, "data") else record
        node = data.get("u", data)
        uis.append({
            "id": node.get("id", ""),
            "selector": node.get("selector", ""),
            "label": node.get("label", ""),
            "url": node.get("url", ""),
        })
    return uis


def _fetch_all_code_files(session) -> list:
    result = session.run("MATCH (c:CodeFile) RETURN c")
    files = []
    for record in result:
        data = record.data() if hasattr(record, "data") else record
        node = data.get("c", data)
        files.append({
            "path": node.get("path", ""),
            "language": node.get("language", ""),
        })
    return files

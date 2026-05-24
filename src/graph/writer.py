from src.ingest.models import Requirement, CodeFile, CodeFunction
from src.crawl.artifacts import DOMSnapshot, UIElement

def write_requirement(session, requirement: Requirement):
    query = """
    MERGE (r:Requirement {id: $id})
    SET r.title = $title,
        r.source_section = $source_section,
        r.raw_text = $raw_text
    RETURN r
    """
    session.run(
        query,
        id=requirement.id,
        title=requirement.title,
        source_section=requirement.source_section,
        raw_text=requirement.raw_text
    )

def write_ui_element(session, ui_element: UIElement):
    query = """
    MERGE (u:UIElement {id: $id})
    SET u.selector = $selector,
        u.label = $label,
        u.url = $url
    RETURN u
    """
    session.run(
        query,
        id=ui_element.id,
        selector=ui_element.selector,
        label=ui_element.label,
        url=ui_element.url
    )

def write_ui_elements(session, dom_snapshot: DOMSnapshot):
    """Iterates through all interactive elements in a snapshot and writes them."""
    # If it's a dictionary (for JSON mock loads) or a DOMSnapshot object
    elements = getattr(dom_snapshot, "elements", [])
    url = getattr(dom_snapshot, "url", "")
    
    if not elements and isinstance(dom_snapshot, dict):
        elements = dom_snapshot.get("elements", [])
        url = dom_snapshot.get("url", "")
        
    for index, elem in enumerate(elements):
        elem_id = elem.get("id", "") or f"UI-{index}"
        ui_element = UIElement(
            id=elem_id,
            selector=elem.get("selector", ""),
            label=elem.get("label", ""),
            url=url
        )
        write_ui_element(session, ui_element)

def write_covers_edge(session, req_id: str, ui_id: str, confidence: float):
    query = """
    MATCH (r:Requirement {id: $req_id})
    MATCH (u:UIElement {id: $ui_id})
    MERGE (r)-[c:COVERS]->(u)
    SET c.confidence = $confidence
    RETURN c
    """
    session.run(query, req_id=req_id, ui_id=ui_id, confidence=confidence)

def mark_absent(session, req_id: str, reason: str):
    query = """
    MATCH (r:Requirement {id: $req_id})
    MERGE (a:Absence {req_id: $req_id})
    SET a.reason = $reason,
        a.confidence = 0.0
    MERGE (r)-[:HAS_ABSENCE]->(a)
    RETURN a
    """
    session.run(query, req_id=req_id, reason=reason)

def write_code_file(session, code_file: CodeFile):
    query = """
    MERGE (c:CodeFile {path: $path})
    SET c.language = $language,
        c.last_modified = $last_modified
    RETURN c
    """
    session.run(
        query,
        path=code_file.path,
        language=code_file.language,
        last_modified=code_file.last_modified
    )

def write_implements_edge(session, file_path: str, ui_id: str, confidence: float):
    query = """
    MATCH (c:CodeFile {path: $file_path})
    MATCH (u:UIElement {id: $ui_id})
    MERGE (c)-[i:IMPLEMENTS]->(u)
    SET i.confidence = $confidence
    RETURN i
    """
    session.run(query, file_path=file_path, ui_id=ui_id, confidence=confidence)

def write_transition_edge(session, from_id: str, to_id: str, action: str, selector: str):
    query = """
    MATCH (u1:UIElement {id: $from_id})
    MATCH (u2:UIElement {id: $to_id})
    MERGE (u1)-[t:TRANSITION]->(u2)
    SET t.action = $action,
        t.selector = $selector
    RETURN t
    """
    session.run(
        query,
        from_id=from_id,
        to_id=to_id,
        action=action,
        selector=selector
    )

from typing import List, Dict, Any

def get_ui_elements_for_file(session, file_path: str) -> List[Dict[str, Any]]:
    query = """
    MATCH (c:CodeFile {path: $file_path})-[i:IMPLEMENTS]->(ui:UIElement)
    RETURN ui
    """
    records = session.run(query, file_path=file_path)
    elements = []
    
    # Check if records is a Mock or list
    for r in records:
        if hasattr(r, "data"):
            data = r.data()
            # Extract "ui" key from standard record dict
            ui = data.get("ui")
            if ui:
                elements.append(ui)
                
    return elements

def get_requirements_for_ui_elements(session, ui_ids: List[str]) -> List[Dict[str, Any]]:
    query = """
    MATCH (r:Requirement)-[cov:COVERS]->(ui:UIElement)
    WHERE ui.id IN $ui_ids
    RETURN r
    """
    records = session.run(query, ui_ids=ui_ids)
    requirements = []
    
    for r in records:
        if hasattr(r, "data"):
            data = r.data()
            req = data.get("r")
            if req:
                requirements.append(req)
                
    return requirements

def get_blast_radius(session, changed_files: List[str], min_confidence: float = 0.6) -> Dict[str, List[Dict[str, Any]]]:
    """
    Executes a multi-layered blast-radius calculation query.
    Traces from modified code -> functions -> UI elements -> downstream transitions -> requirements.
    """
    query = """
    MATCH (cf:CodeFile)
    WHERE cf.path IN $changed_files
    OPTIONAL MATCH (cf)-[impl:IMPLEMENTS]->(ui:UIElement)
      WHERE impl.confidence >= $min_confidence
    OPTIONAL MATCH (ui)<-[cov:COVERS]-(r:Requirement)
      WHERE cov.confidence >= $min_confidence
    OPTIONAL MATCH (ui)-[:PART_OF]->(flow:UserFlow)
    OPTIONAL MATCH (ui)-[:TRANSITION*0..2]->(downstream:UIElement)
    OPTIONAL MATCH (downstream)<-[down_cov:COVERS]-(down_r:Requirement)
      WHERE down_cov.confidence >= $min_confidence
    OPTIONAL MATCH (r)-[:HAS_ABSENCE]->(absence:Absence)
    RETURN
      collect(DISTINCT ui) AS ui_elements,
      collect(DISTINCT r)  AS requirements,
      collect(DISTINCT flow) AS affected_flows,
      collect(DISTINCT absence) AS absence_nodes,
      collect(DISTINCT downstream) AS downstream_ui_elements,
      collect(DISTINCT down_r) AS downstream_requirements
    """
    result = session.run(query, changed_files=changed_files, min_confidence=min_confidence)
    
    # Support list of records mock patterns in UT conftest setups
    record = None
    if hasattr(result, "single"):
        try:
            record = result.single()
        except Exception:
            pass
            
    if not record and isinstance(result, list) and len(result) > 0:
        record = result[0]
        
    if not record:
        return {
            "ui_elements": [],
            "requirements": [],
            "affected_flows": [],
            "absence_nodes": [],
            "downstream_ui_elements": [],
            "downstream_requirements": []
        }
        
    data = {}
    if hasattr(record, "data"):
        data = record.data()
    elif isinstance(record, dict):
        data = record
        
    return {
        "ui_elements": data.get("ui_elements", []),
        "requirements": data.get("requirements", []),
        "affected_flows": data.get("affected_flows", []),
        "absence_nodes": data.get("absence_nodes", []),
        "downstream_ui_elements": data.get("downstream_ui_elements", []),
        "downstream_requirements": data.get("downstream_requirements", [])
    }

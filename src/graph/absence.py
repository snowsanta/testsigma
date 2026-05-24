def mark_all_absences(session):
    """
    Post-processing step that finds all Requirements with no outgoing COVERS edges to UIElement,
    and attaches an Absence node linked via HAS_ABSENCE to represent coverage gaps.
    """
    query = """
    MATCH (r:Requirement)
    WHERE NOT (r)-[:COVERS]->(:UIElement)
    MERGE (a:Absence {req_id: r.id})
    SET a.reason = "No matching UI element found after crawl",
        a.confidence = 0.0
    MERGE (r)-[:HAS_ABSENCE]->(a)
    RETURN a
    """
    session.run(query)

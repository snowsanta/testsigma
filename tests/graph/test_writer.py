import pytest
from unittest.mock import MagicMock
from src.ingest.models import Requirement, CodeFile, CodeFunction
from src.crawl.artifacts import DOMSnapshot, UIElement
from src.graph.writer import (
    write_requirement,
    write_ui_elements,
    write_covers_edge,
    mark_absent,
    write_code_file,
    write_implements_edge,
    write_transition_edge
)

def test_write_requirement_node_creates_node(neo4j_session):
    req = Requirement(id="R1", title="Create repository", source_section="Features", raw_text="Allows creating repositories.")
    
    # Mock run return to yield a single node record mock
    mock_record = MagicMock()
    neo4j_session.run.return_value.single.return_value = mock_record
    
    write_requirement(neo4j_session, req)
    
    # Assert Cypher parameter binding structure is correct
    neo4j_session.run.assert_called_once()
    args, kwargs = neo4j_session.run.call_args
    assert "MERGE (r:Requirement" in args[0]
    assert kwargs["id"] == "R1"
    assert kwargs["title"] == "Create repository"

def test_write_covers_edge_links_requirement_to_ui(neo4j_session):
    # Mock writing of covers relationship
    write_covers_edge(neo4j_session, req_id="R1", ui_id="U1", confidence=0.85)
    
    args, kwargs = neo4j_session.run.call_args
    assert "MATCH (r:Requirement {id: $req_id})" in args[0]
    assert "MATCH (u:UIElement {id: $ui_id})" in args[0]
    assert "MERGE (r)-[c:COVERS]->(u)" in args[0]
    assert kwargs["req_id"] == "R1"
    assert kwargs["ui_id"] == "U1"
    assert kwargs["confidence"] == 0.85

def test_absence_node_is_created_for_uncovered_requirement(neo4j_session):
    mark_absent(neo4j_session, req_id="R2", reason="No UI elements found matching specification")
    
    args, kwargs = neo4j_session.run.call_args
    assert "MERGE (a:Absence {req_id: $req_id})" in args[0]
    assert "MERGE (r)-[:HAS_ABSENCE]->(a)" in args[0]
    assert kwargs["req_id"] == "R2"
    assert kwargs["reason"] == "No UI elements found matching specification"

def test_write_code_file_creates_node(neo4j_session):
    cf = CodeFile(path="app/repos/create.rb", language="Ruby")
    write_code_file(neo4j_session, cf)
    
    args, kwargs = neo4j_session.run.call_args
    assert "MERGE (c:CodeFile {path: $path})" in args[0]
    assert kwargs["path"] == "app/repos/create.rb"
    assert kwargs["language"] == "Ruby"

def test_write_implements_edge_links_code_to_ui(neo4j_session):
    write_implements_edge(neo4j_session, file_path="app/repos/create.rb", ui_id="U1", confidence=0.9)
    
    args, kwargs = neo4j_session.run.call_args
    assert "MATCH (c:CodeFile {path: $file_path})" in args[0]
    assert "MATCH (u:UIElement {id: $ui_id})" in args[0]
    assert "MERGE (c)-[i:IMPLEMENTS]->(u)" in args[0]
    assert kwargs["file_path"] == "app/repos/create.rb"
    assert kwargs["ui_id"] == "U1"
    assert kwargs["confidence"] == 0.9

def test_write_transition_edge_links_ui_elements(neo4j_session):
    write_transition_edge(neo4j_session, from_id="U1", to_id="U2", action="click", selector="#btn")
    
    args, kwargs = neo4j_session.run.call_args
    assert "MATCH (u1:UIElement {id: $from_id})" in args[0]
    assert "MATCH (u2:UIElement {id: $to_id})" in args[0]
    assert "MERGE (u1)-[t:TRANSITION]->(u2)" in args[0]
    assert kwargs["from_id"] == "U1"
    assert kwargs["to_id"] == "U2"
    assert kwargs["action"] == "click"
    assert kwargs["selector"] == "#btn"

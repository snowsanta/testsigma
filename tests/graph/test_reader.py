import pytest
from unittest.mock import MagicMock
from src.graph.reader import get_ui_elements_for_file, get_requirements_for_ui_elements, get_blast_radius

def test_get_ui_elements_for_file(neo4j_session):
    mock_record = MagicMock()
    mock_record.data.return_value = {
        "ui": {"id": "U1", "selector": "#btn", "label": "New repo", "url": "https://github.com"}
    }
    # Setup run result mocks
    neo4j_session.run.return_value = [mock_record]
    
    elements = get_ui_elements_for_file(neo4j_session, file_path="app/repos/create.rb")
    assert len(elements) == 1
    assert elements[0]["id"] == "U1"
    assert elements[0]["selector"] == "#btn"

def test_get_requirements_losing_coverage(neo4j_session):
    mock_record = MagicMock()
    mock_record.data.return_value = {
        "r": {"id": "R1", "title": "Create repository", "source_section": "Features"}
    }
    neo4j_session.run.return_value = [mock_record]
    
    reqs = get_requirements_for_ui_elements(neo4j_session, ui_ids=["U1"])
    assert len(reqs) == 1
    assert reqs[0]["id"] == "R1"

def test_blast_radius_returns_empty_for_unconnected_file(neo4j_session):
    mock_result = MagicMock()
    # Mocking single() to return None representing empty database matching records
    neo4j_session.run.return_value.single.return_value = None
    
    result = get_blast_radius(neo4j_session, changed_files=["app/unrelated.rb"])
    assert result["ui_elements"] == []
    assert result["requirements"] == []
    assert result["downstream_ui_elements"] == []

def test_blast_radius_filters_out_low_confidence_edges(neo4j_session):
    mock_result = MagicMock()
    # The query filters out elements below min_confidence. Setting mock parameter verification:
    get_blast_radius(neo4j_session, changed_files=["app/low_conf.rb"], min_confidence=0.6)
    
    args, kwargs = neo4j_session.run.call_args
    assert kwargs["min_confidence"] == 0.6
    assert "min_confidence" in args[0] or "$min_confidence" in args[0]

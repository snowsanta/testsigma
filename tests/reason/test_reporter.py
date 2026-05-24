import pytest
from unittest.mock import patch
from src.reason.blast_radius import BlastRadiusResult
from src.reason.reporter import generate_report

@pytest.fixture
def sample_blast_radius_result():
    return BlastRadiusResult(
        ui_elements_at_risk=[{"id": "U1", "label": "New repository button"}],
        affected_requirements=[{"id": "R1", "title": "Repository creation feature"}],
        downstream_ui_elements=[{"id": "U2", "label": "Repository name input"}],
        downstream_requirements=[{"id": "R2", "title": "Unique repository names check"}]
    )

def test_reporter_returns_non_empty_string(sample_blast_radius_result, mock_llm_client):
    mock_llm_client.return_value = "This change is localized to the Repository creation panel."
    
    report, structured = generate_report(sample_blast_radius_result)
    
    assert isinstance(report, str)
    assert len(report) > 0
    assert isinstance(structured, dict)

def test_reporter_does_not_expose_cypher_or_ids(sample_blast_radius_result, mock_llm_client):
    mock_llm_client.return_value = "Risk affects: Repository creation panel. Downstream: Repository name input."
    
    report, _ = generate_report(sample_blast_radius_result)
    
    assert "MATCH" not in report
    assert "MERGE" not in report
    assert "neo4j" not in report.lower()

def test_reporter_handles_empty_blast_radius(mock_llm_client):
    empty = BlastRadiusResult(
        ui_elements_at_risk=[],
        affected_requirements=[],
        downstream_ui_elements=[],
        downstream_requirements=[]
    )
    mock_llm_client.return_value = "No user-facing flows or specification requirements are affected by this change."
    
    report, _ = generate_report(empty)
    assert "no" in report.lower() or "not affect" in report.lower()

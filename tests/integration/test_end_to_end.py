import pytest
from unittest.mock import patch, MagicMock
from src.ingest.parser import parse_prd
from src.ingest.code_parser import scan_repository
from src.graph.writer import write_requirement, write_ui_elements, write_covers_edge, mark_absent
from src.reason.pr_fetcher import PR
from src.reason.blast_radius import BlastRadiusEngine
from src.reason.reporter import generate_report

@pytest.mark.integration
def test_full_pipeline_produces_report(mock_llm_client, docker_neo4j):
    # 1. Ingest specs
    mock_llm_client.return_value = """[
        {"id": "R1", "title": "Create repository", "source_section": "Features", "raw_text": "Allows creating repositories."}
    ]"""
    reqs = parse_prd("# Spec File")
    assert len(reqs) == 1
    
    # 2. Seed mock Neo4j session
    mock_session = MagicMock()
    mock_record = MagicMock()
    mock_record.data.return_value = {
        "ui_elements": [{"id": "U1", "label": "Create button"}],
        "requirements": [{"id": "R1", "title": "Create repository"}],
        "downstream_ui_elements": [],
        "downstream_requirements": []
    }
    mock_session.run.return_value = [mock_record]
    mock_session.run.return_value.single.return_value = mock_record
    
    for req in reqs:
        write_requirement(mock_session, req)
    
    # 3. Compute Blast Radius for Mock PR
    pr = PR(pr_number=123, changed_files=["app/repos/create.rb"])
    
    with patch("src.reason.blast_radius.get_blast_radius") as mock_query:
        mock_query.return_value = {
            "ui_elements": [{"id": "U1", "label": "Create button"}],
            "requirements": [{"id": "R1", "title": "Create repository"}],
            "downstream_ui_elements": [],
            "downstream_requirements": []
        }
        engine = BlastRadiusEngine(session=mock_session)
        result = engine.compute(pr)
        
        # 4. Generate plaintext narrative report
        mock_llm_client.return_value = "This change is localized to the repository creation button. No downstream flows are at risk."
        report = generate_report(result)
        
        assert isinstance(report, str)
        assert "repository creation button" in report

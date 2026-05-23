import pytest
from unittest.mock import patch
from src.ingest.parser import parse_prd
from src.ingest.models import Requirement

@pytest.fixture
def sample_readme():
    return """
    # Project Specs
    
    ## Features
    * R1: User can create a repository.
    * R2: User can delete a repository.
    
    ## Security
    * R3: Enable two-factor authentication.
    """

@pytest.fixture
def sample_readme_with_duplicates():
    return """
    # Project Specs
    ## Features
    * R1: User can create a repository.
    * R1: User can create a repository.
    """

def test_parser_extracts_requirements_from_markdown(sample_readme, mock_llm_client):
    # Mock the LLM completion parser response to return structured JSON representations
    mock_llm_client.return_value = """[
        {"id": "R1", "title": "User can create a repository", "source_section": "Features", "raw_text": "User can create a repository."},
        {"id": "R2", "title": "User can delete a repository", "source_section": "Features", "raw_text": "User can delete a repository."},
        {"id": "R3", "title": "Enable two-factor authentication", "source_section": "Security", "raw_text": "Enable two-factor authentication."}
    ]"""
    
    reqs = parse_prd(sample_readme)
    assert len(reqs) == 3
    assert all(isinstance(r, Requirement) for r in reqs)
    assert reqs[0].id == "R1"
    assert reqs[2].source_section == "Security"

def test_parser_deduplicates_identical_lines(sample_readme_with_duplicates, mock_llm_client):
    mock_llm_client.return_value = """[
        {"id": "R1", "title": "User can create a repository", "source_section": "Features", "raw_text": "User can create a repository."}
    ]"""
    reqs = parse_prd(sample_readme_with_duplicates)
    assert len(reqs) == 1

def test_parser_handles_empty_input():
    assert parse_prd("") == []

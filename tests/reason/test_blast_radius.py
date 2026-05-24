import pytest
import json
from unittest.mock import MagicMock, patch
from src.reason.pr_fetcher import PR
from src.reason.blast_radius import BlastRadiusEngine, BlastRadiusResult

@pytest.fixture
def mock_reader_returns():
    return {
        "ui_elements": [{"id": "U1", "selector": "#btn", "label": "New repo"}],
        "requirements": [{"id": "R1", "title": "Create repo"}],
        "downstream_ui_elements": [{"id": "U2", "selector": "#name"}],
        "downstream_requirements": [{"id": "R2", "title": "Set name"}]
    }

def test_blast_radius_engine_calls_graph_reader(mock_reader_returns):
    mock_session = MagicMock()
    
    # Patch graph query reader functions
    with patch("src.reason.blast_radius.get_blast_radius", return_value=mock_reader_returns) as mock_query:
        engine = BlastRadiusEngine(session=mock_session)
        pr = PR(pr_number=1, changed_files=["app/repos/create.rb"])
        
        result = engine.compute(pr, min_confidence=0.7)
        
        # Verify connection to reader query wrapper
        mock_query.assert_called_once_with(mock_session, changed_files=["app/repos/create.rb"], min_confidence=0.7)
        
        assert isinstance(result, BlastRadiusResult)
        assert len(result.ui_elements_at_risk) == 1
        assert result.ui_elements_at_risk[0]["id"] == "U1"
        assert len(result.downstream_requirements) == 1

def test_blast_radius_result_is_serialisable():
    result = BlastRadiusResult(
        ui_elements_at_risk=[{"id": "U1"}],
        affected_requirements=[{"id": "R1"}],
        downstream_ui_elements=[{"id": "U2"}],
        downstream_requirements=[{"id": "R2"}]
    )
    
    serialized = json.dumps(result.to_dict())
    deserialized = json.loads(serialized)
    assert deserialized["ui_elements_at_risk"] == [{"id": "U1"}]
    assert deserialized["downstream_requirements"] == [{"id": "R2"}]

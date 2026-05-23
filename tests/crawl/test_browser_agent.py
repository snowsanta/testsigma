import pytest
from unittest.mock import MagicMock, patch
from src.crawl.browser_agent import BrowserAgent, CrawlArtifactBundle

@pytest.fixture
def mock_playwright():
    with patch("src.crawl.browser_agent.PlaywrightExecutor") as mock:
        yield mock

@pytest.fixture
def mock_planner():
    with patch("src.crawl.browser_agent.LLMPlanner") as mock:
        yield mock

def test_agent_stops_after_max_steps(mock_playwright, mock_planner):
    # Setup planner to continuously request next click actions
    planner_instance = mock_planner.return_value
    planner_instance.next_action.return_value = {"action": "click", "selector": "#btn"}
    
    agent = BrowserAgent(max_steps=3)
    agent.run(start_url="https://github.com")
    
    # Verify loops hit constraint ceiling and exited safely
    assert planner_instance.next_action.call_count <= 3

def test_agent_returns_artifact_bundle(mock_playwright, mock_planner):
    planner_instance = mock_planner.return_value
    # First step navigates, second step stops crawl
    planner_instance.next_action.side_effect = [
        {"action": "click", "selector": "#btn"},
        {"action": "stop", "reason": "Target reached"}
    ]
    
    agent = BrowserAgent(max_steps=10)
    result = agent.run(start_url="https://github.com")
    
    assert isinstance(result, CrawlArtifactBundle)
    assert len(result.snapshots) >= 1

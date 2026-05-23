import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_llm_client(monkeypatch):
    """Fixture to mock the thin LLM wrapper boundary client.complete."""
    mock = MagicMock(return_value="mocked response")
    monkeypatch.setattr("src.llm.client.complete", mock)
    return mock

@pytest.fixture
def docker_neo4j():
    """Mock docker neo4j bolt URL fixture for unit testing."""
    class MockNeo4jContainer:
        bolt_url = "bolt://localhost:7687"
    return MockNeo4jContainer()

@pytest.fixture
def neo4j_session():
    """Mock Neo4j session fixture that avoids real database network calls in pure UTs."""
    session = MagicMock()
    # Mock run returns an object that has .single() and other expected Neo4j result accessors
    mock_result = MagicMock()
    session.run.return_value = mock_result
    return session

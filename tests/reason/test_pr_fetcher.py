import pytest
import responses
import re
from src.reason.pr_fetcher import fetch_pr, PR, PRNotFoundError

@pytest.fixture
def mock_github_pr_response():
    return [
        {"filename": "app/repos/create.rb", "status": "modified"},
        {"filename": "app/new_feature.py", "status": "added"}
    ]

@responses.activate
def test_pr_fetcher_returns_changed_files(mock_github_pr_response):
    # Mock the GitHub Pull Request Files REST API endpoint
    responses.add(
        responses.GET,
        "https://api.github.com/repos/test-owner/test-repo/pulls/123/files",
        json=mock_github_pr_response,
        status=200
    )
    
    pr = fetch_pr(repo="test-owner/test-repo", pr_number=123)
    
    assert isinstance(pr, PR)
    assert pr.pr_number == 123
    assert len(pr.changed_files) == 2
    assert "app/repos/create.rb" in pr.changed_files
    assert "app/new_feature.py" in pr.changed_files

@responses.activate
def test_pr_fetcher_handles_404():
    responses.add(
        responses.GET,
        re.compile(r"https://api.github.com/repos/.*"),
        status=404
    )
    
    with pytest.raises(PRNotFoundError):
        fetch_pr(repo="test-owner/test-repo", pr_number=99999)

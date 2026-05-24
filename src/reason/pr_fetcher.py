import requests
from typing import List

class PRNotFoundError(Exception):
    """Custom exception raised when a target repository or pull request is not found."""
    pass

class PR:
    """Data representation containing changed file list and identifier details of a PR."""
    def __init__(self, pr_number: int, changed_files: List[str]):
        self.pr_number = pr_number
        self.changed_files = changed_files

def fetch_pr(repo: str, pr_number: int) -> PR:
    """
    Fetches Pull Request file change lists using GitHub REST API via requests (for response mocking).
    Raises PRNotFoundError on 404 API errors.
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {"User-Agent": "Python-Requests"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 404:
        raise PRNotFoundError(f"Pull request not found: {repo} #{pr_number}")
        
    response.raise_for_status()
    data = response.json()
    
    # Extract all unique target modified/created/deleted file paths
    changed_files = [item.get("filename", "") for item in data if item.get("filename")]
    return PR(pr_number=pr_number, changed_files=changed_files)

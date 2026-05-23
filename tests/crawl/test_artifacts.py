import pytest
import json
from src.crawl.artifacts import DOMSnapshot, Transition, CrawlArtifactBundle

@pytest.fixture
def sample_dom_html():
    return """
    <html>
        <body>
            <h1>Welcome to GitHub</h1>
            <a id="new-repo" href="/new" class="btn">New repository</a>
            <input type="text" name="q" placeholder="Search..."/>
            <button type="submit">Go</button>
            <div>Static text context</div>
        </body>
    </html>
    """

def test_dom_snapshot_serialises_to_dict(sample_dom_html):
    snap = DOMSnapshot.from_html(sample_dom_html, url="https://github.com")
    d = snap.to_dict()
    assert d["url"] == "https://github.com"
    assert isinstance(d["elements"], list)
    assert "timestamp" in d

def test_dom_snapshot_extracts_interactive_elements(sample_dom_html):
    snap = DOMSnapshot.from_html(sample_dom_html, url="https://github.com")
    tags = [e["tag"] for e in snap.elements]
    assert "a" in tags
    assert "input" in tags
    assert "button" in tags
    assert "h1" not in tags  # non-interactive heading ignored

def test_transition_links_two_snapshots():
    t = Transition(
        from_url="https://github.com",
        to_url="https://github.com/new",
        action="click",
        element_selector="#new-repo"
    )
    assert t.from_url != t.to_url
    assert t.action == "click"
    assert t.element_selector == "#new-repo"

def test_crawl_artifact_export_is_json_serialisable():
    snap = DOMSnapshot.from_html("<html></html>", url="https://github.com")
    t = Transition("https://github.com", "https://github.com/new", "click", "#btn")
    bundle = CrawlArtifactBundle(snapshots=[snap], transitions=[t])
    
    serialized = json.dumps(bundle.to_dict())
    deserialized = json.loads(serialized)
    assert len(deserialized["snapshots"]) == 1
    assert len(deserialized["transitions"]) == 1

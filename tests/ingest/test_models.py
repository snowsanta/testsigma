from src.ingest.models import Requirement, CodeFile

def test_requirement_has_required_fields():
    r = Requirement(id="R1", title="User can create a repo", source_section="Features", raw_text="User opens page and submits repo creation form.")
    assert r.id == "R1"
    assert r.title == "User can create a repo"
    assert r.source_section == "Features"
    assert r.raw_text.startswith("User opens page")

def test_requirement_is_hashable():
    r = Requirement(id="R1", title="x", source_section="y", raw_text="z")
    # Hashability allows requirements to be held in sets for simple deduplication
    assert r in {r}

def test_code_file_has_required_fields():
    cf = CodeFile(path="app/main.py", language="Python", last_modified="2026-05-23")
    assert cf.path == "app/main.py"
    assert cf.language == "Python"

import pytest
from src.ingest.code_parser import scan_repository
from src.ingest.models import CodeFile, CodeFunction

def test_code_parser_scans_directory_for_python_files(tmp_path):
    # Seed dummy python files in standard nested paths
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text("""
def main_func():
    print("running main")
    
def secondary_func(x):
    return x * 2
""")
    (app_dir / "utils.py").write_text("""
class Helper:
    def help_me(self):
        pass
""")

    files, functions = scan_repository(tmp_path)
    
    # Assert correct CodeFile nodes were identified
    assert len(files) == 2
    paths = {f.path for f in files}
    assert any(p.endswith("main.py") for p in paths)
    assert any(p.endswith("utils.py") for p in paths)
    
    # Assert correct CodeFunction signatures were mapped using ast parsing
    assert len(functions) >= 3
    names = {fn.name for fn in functions}
    assert "main_func" in names
    assert "secondary_func" in names
    assert "help_me" in names
    
    # Assert function locations are mapped properly
    main_func = next(fn for fn in functions if fn.name == "main_func")
    assert main_func.file_path.endswith("main.py")

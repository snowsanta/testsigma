import os
import ast
from typing import List, Tuple
from src.ingest.models import CodeFile, CodeFunction

class PythonFunctionVisitor(ast.NodeVisitor):
    """AST Visitor to harvest function names from a Python source tree."""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.functions = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Extract module or class level function signature details
        self.functions.append(
            CodeFunction(
                name=node.name,
                file_path=self.file_path,
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno)
            )
        )
        self.generic_visit(node)

def scan_repository(root_dir: str) -> Tuple[List[CodeFile], List[CodeFunction]]:
    """
    Scans directory recursively, parsing ASTs of files to build Code node representations.
    """
    code_files = []
    code_functions = []
    
    root_path = str(root_dir)
    
    for root, dirs, files in os.walk(root_path):
        # Exclude dot directories, virtual environments, and caches
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in ("venv", "__pycache__", "testsigma", "reports", "node_modules")
        ]
        
        for file in files:
            if file.endswith((".py", ".rb")):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_path)
                
                language = "Python" if file.endswith(".py") else "Ruby"
                code_file = CodeFile(path=rel_path, language=language)
                code_files.append(code_file)
                
                # Parse AST for Python files
                if file.endswith(".py"):
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        tree = ast.parse(content, filename=full_path)
                        visitor = PythonFunctionVisitor(file_path=rel_path)
                        visitor.visit(tree)
                        code_functions.extend(visitor.functions)
                    except Exception:
                        # Ignore syntax or reading errors gracefully in scanning pass
                        pass
                        
    return code_files, code_functions

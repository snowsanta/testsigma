from dataclasses import dataclass

@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    source_section: str
    raw_text: str

@dataclass(frozen=True)
class CodeFile:
    path: str
    language: str
    last_modified: str = ""

@dataclass(frozen=True)
class CodeFunction:
    name: str
    file_path: str
    start_line: int = 0
    end_line: int = 0

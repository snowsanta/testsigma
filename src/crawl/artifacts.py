import time
from typing import List, Dict, Any
from html.parser import HTMLParser

class InteractiveElementParser(HTMLParser):
    """HTML parser to harvest interactive tags (a, button, input, select, textarea)."""
    def __init__(self):
        super().__init__()
        self.elements = []

    def _build_selector(self, tag: str, attrs_dict: dict) -> str:
        """Builds the most specific CSS selector possible for Playwright targeting."""
        elem_id = attrs_dict.get("id", "")
        if elem_id:
            return f"#{elem_id}"
        data_testid = attrs_dict.get("data-testid", "")
        if data_testid:
            return f'[data-testid="{data_testid}"]'
        aria_label = attrs_dict.get("aria-label", "")
        if aria_label:
            return f'[aria-label="{aria_label}"]'
        name = attrs_dict.get("name", "")
        if name:
            return f'[name="{name}"]'
        class_val = attrs_dict.get("class", "")
        if class_val:
            return f"{tag}.{class_val.replace(' ', '.')}"
        return tag

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        if tag in ("a", "button", "input", "select", "textarea"):
            attrs_dict = dict(attrs)
            elem_id = attrs_dict.get("id", "")
            label = attrs_dict.get("placeholder") or attrs_dict.get("value") or attrs_dict.get("aria-label") or attrs_dict.get("name") or attrs_dict.get("alt") or elem_id or tag
            self.elements.append({
                "tag": tag,
                "id": elem_id,
                "selector": self._build_selector(tag, attrs_dict),
                "label": label,
                "element_type": tag,
                "text_content": "",
            })

class DOMSnapshot:
    """DOM Snapshot representing parsed page structures."""
    def __init__(self, url: str, html: str, elements: List[Dict[str, Any]], timestamp: float):
        self.url = url
        self.html = html
        self.elements = elements
        self.timestamp = timestamp

    @classmethod
    def from_html(cls, html_content: str, url: str) -> "DOMSnapshot":
        parser = InteractiveElementParser()
        parser.feed(html_content)
        return cls(
            url=url,
            html=html_content,
            elements=parser.elements,
            timestamp=time.time()
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "elements": self.elements,
            "timestamp": self.timestamp
        }

class Transition:
    """Transition representing screen relationship navigation traversals."""
    def __init__(self, from_url: str, to_url: str, action: str, element_selector: str):
        self.from_url = from_url
        self.to_url = to_url
        self.action = action
        self.element_selector = element_selector

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_url": self.from_url,
            "to_url": self.to_url,
            "action": self.action,
            "element_selector": self.element_selector
        }

class CrawlArtifactBundle:
    """Bundle exporting a sequence of crawl snapshots and transitions."""
    def __init__(self, snapshots: List[DOMSnapshot], transitions: List[Transition]):
        self.snapshots = snapshots
        self.transitions = transitions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "transitions": [t.to_dict() for t in self.transitions]
        }

class UIElement:
    """Datalayer entity representation for UI/DOM elements."""
    def __init__(self, id: str, selector: str, label: str, url: str):
        self.id = id
        self.selector = selector
        self.label = label
        self.url = url

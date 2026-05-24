from typing import List, Dict, Any
from src.reason.pr_fetcher import PR
from src.graph.reader import get_blast_radius

class BlastRadiusResult:
    """Intermediate data representation containing categorized risk lists."""
    def __init__(
        self,
        ui_elements_at_risk: List[Dict[str, Any]],
        affected_requirements: List[Dict[str, Any]],
        downstream_ui_elements: List[Dict[str, Any]] = None,
        downstream_requirements: List[Dict[str, Any]] = None
    ):
        self.ui_elements_at_risk = ui_elements_at_risk
        self.affected_requirements = affected_requirements
        self.downstream_ui_elements = downstream_ui_elements if downstream_ui_elements is not None else []
        self.downstream_requirements = downstream_requirements if downstream_requirements is not None else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ui_elements_at_risk": self.ui_elements_at_risk,
            "affected_requirements": self.affected_requirements,
            "downstream_ui_elements": self.downstream_ui_elements,
            "downstream_requirements": self.downstream_requirements
        }

class BlastRadiusEngine:
    """Reasoning calculations orchestrator querying database paths."""
    def __init__(self, session):
        self.session = session

    def compute(self, pr: PR, min_confidence: float = 0.6) -> BlastRadiusResult:
        """Calculates the blast radius of changes in a given Pull Request."""
        # Query Neo4j multi-layered connections
        query_result = get_blast_radius(
            self.session,
            changed_files=pr.changed_files,
            min_confidence=min_confidence
        )
        
        return BlastRadiusResult(
            ui_elements_at_risk=query_result.get("ui_elements", []),
            affected_requirements=query_result.get("requirements", []),
            downstream_ui_elements=query_result.get("downstream_ui_elements", []),
            downstream_requirements=query_result.get("downstream_requirements", [])
        )

import json
from typing import List
import src.llm.client
from src.ingest.models import Requirement

def parse_prd(readme_content: str) -> List[Requirement]:
    """
    Parses unstructured spec documents into structured Requirement objects.
    Utilizes LLM to process section structure and semantic text values.
    """
    if not readme_content.strip():
        return []
        
    system_prompt = "You are a requirements spec parser. Parse the input document into a JSON list of requirements."
    user_prompt = f"Extract all requirements from the following markdown content. Format as a JSON array with fields: id, title, source_section, raw_text.\n\nContent:\n{readme_content}"
    
    # Call dynamically to respect monkeypatches during unit testing
    response_str = src.llm.client.complete(system=system_prompt, user=user_prompt)

    # Strip markdown code fences if present
    cleaned = response_str.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

    try:
        parsed_json = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed_json = []
        
    requirements = []
    seen_ids = set()
    
    for item in parsed_json:
        req_id = item.get("id", "")
        if req_id and req_id not in seen_ids:
            seen_ids.add(req_id)
            requirements.append(
                Requirement(
                    id=req_id,
                    title=item.get("title", ""),
                    source_section=item.get("source_section", ""),
                    raw_text=item.get("raw_text", "")
                )
            )
            
    return requirements

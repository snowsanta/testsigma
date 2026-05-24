import os
import requests

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
DEFAULT_MODEL = os.getenv("LM_STUDIO_MODEL", None)
API_KEY = os.getenv("OPENAI_API_KEY", "")


def configure(url: str = None, model: str = None, api_key: str = None):
    global LM_STUDIO_URL, DEFAULT_MODEL, API_KEY
    if url is not None:
        LM_STUDIO_URL = url
    if model is not None:
        DEFAULT_MODEL = model
    if api_key is not None:
        API_KEY = api_key


def complete(system: str, user: str, model: str = None) -> str:
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resolved = model or DEFAULT_MODEL
    if resolved:
        payload["model"] = resolved
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    response = requests.post(LM_STUDIO_URL, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

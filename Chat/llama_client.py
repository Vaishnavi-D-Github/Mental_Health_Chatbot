# llama_client.py
import requests

OLLAMA_HOST = "http://localhost:11434"

def call_ollama(prompt, model="llama3.2"):
    """
    Calls local Ollama server with given prompt.
    Make sure 'ollama run llama3.2' works first.
    """
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 80}
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()

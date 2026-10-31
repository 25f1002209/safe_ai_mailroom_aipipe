import os, json, requests

def chat_json(system_prompt, user_payload):
    api_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("AI_API_KEY is not configured")
    base = os.getenv("AI_BASE_URL", "https://aipipe.org/openai/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4.1-nano")
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
        ]
    }
    response = requests.post(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }, json=payload, timeout=int(os.getenv("AI_TIMEOUT", "35")))
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)

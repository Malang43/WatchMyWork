import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    raise RuntimeError("OPENROUTER_API_KEY was not found in .env")

url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

data = {
    "model": "nvidia/nemotron-3.5-lightning:free",
    "messages": [
        {
            "role": "user",
            "content": (
                "You are the reasoning engine for WatchMyWork. "
                "Reply with exactly: NEMOTRON CONNECTION WORKING"
            ),
        }
    ],
    "max_tokens": 50,
}

response = requests.post(
    url,
    headers=headers,
    json=data,
    timeout=60
)

print("HTTP status:", response.status_code)

if response.ok:
    result = response.json()
    print("Model:", result.get("model"))
    print("Response:")
    print(result["choices"][0]["message"]["content"])
else:
    print("Error:")
    print(response.text)
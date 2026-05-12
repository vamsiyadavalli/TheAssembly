import os
import requests
import json

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("GEMINI_API_KEY not set in environment.")

# Gemini API endpoint for listing models
url = "https://generativelanguage.googleapis.com/v1beta/models"
headers = {"Content-Type": "application/json"}
params = {"key": API_KEY}

print("[info] Querying Gemini API for available models...")
resp = requests.get(url, headers=headers, params=params)
if resp.status_code != 200:
    print(f"[error] Status: {resp.status_code}")
    print(resp.text)
    exit(1)

models = resp.json().get("models", [])
print(f"[info] Found {len(models)} models:")
for m in models:
    print(f"- {m['name']}")
    if 'supportedGenerationMethods' in m:
        print(f"    methods: {m['supportedGenerationMethods']}")
    else:
        print("    methods: (not listed)")

# Print full JSON for inspection
with open("gemini_models.json", "w") as f:
    json.dump(models, f, indent=2)
print("[info] Full model list written to gemini_models.json")

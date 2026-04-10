import requests, os
from dotenv import load_dotenv

load_dotenv()
r = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
)
models = [(m["id"], m.get("context_window", 0)) for m in r.json().get("data", [])]
for mid, ctx in sorted(models, key=lambda x: x[1], reverse=True):
    print(f"{ctx:>12}  {mid}")

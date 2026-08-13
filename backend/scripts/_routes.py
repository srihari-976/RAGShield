import os
os.environ["PYTHONPATH"] = "."
import httpx

spec = httpx.get("http://localhost:8000/openapi.json", timeout=30).json()
routes = set()
for path, ops in spec["paths"].items():
    for m in ops:
        if m in ("get", "post", "put", "patch", "delete"):
            routes.add((m.upper(), path))
for m, p in sorted(routes):
    print(f"{m:6s} {p}")
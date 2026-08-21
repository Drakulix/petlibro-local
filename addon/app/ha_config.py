import os

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API_URL = os.environ.get("HA_BASE_URL", "http://supervisor/core/api")

def _headers() -> dict:
    return {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}

def _token() -> str:
    return SUPERVISOR_TOKEN

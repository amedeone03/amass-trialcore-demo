import os

import requests
from dotenv import load_dotenv

load_dotenv()

TRIALCORE_URL = "https://api.amass.tech/api/v1/cores/trialcore/records"


def search_trials(query, limit=10):
    api_key = os.getenv("AMASS_API_KEY")
    if not api_key:
        raise RuntimeError("AMASS_API_KEY is missing. Add it to a .env file.")

    response = requests.get(
        TRIALCORE_URL,
        params={"query": query, "limit": limit},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", [])

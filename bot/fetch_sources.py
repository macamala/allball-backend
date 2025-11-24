import os
from typing import List, Dict, Any
import requests

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def fetch_football_headlines() -> List[Dict[str, Any]]:
    if not NEWS_API_KEY:
        raise ValueError("NEWS_API_KEY environment variable is not set")

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "football OR soccer OR premier league OR champions league",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": NEWS_API_KEY,
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data.get("articles", [])

import os
import requests

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def fetch_latest_news():
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "language": "en",
        "pageSize": 50,
        "apiKey": NEWS_API_KEY,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data.get("articles", [])

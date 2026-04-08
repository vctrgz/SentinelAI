import requests

def search_web(query: str):
    url = f"https://api.duckduckgo.com/?q={query}&format=json"
    res = requests.get(url).json()
    return res.get("AbstractText", "No results")
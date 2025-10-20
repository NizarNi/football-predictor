from __future__ import annotations
import os, sys, requests
from dotenv import load_dotenv, find_dotenv


def pages(base, key, path):
    page = 1
    while True:
        r = requests.get(f"{base}/{path}", params={"api_token": key, "page": page}, timeout=20)
        r.raise_for_status()
        j = r.json()
        for row in j.get("data", []):
            yield row
        meta = j.get("meta") or {}
        if not meta or not meta.get("next_page_url"):
            break
        page += 1


def main():
    load_dotenv(find_dotenv(usecwd=True))
    base = os.getenv("SPORTMONKS_BASE", "https://api.sportmonks.com/v3/football")
    key  = os.getenv("SPORTMONKS_KEY") or (open(os.getenv("SPORTMONKS_KEY_FILE")).read().strip() if os.getenv("SPORTMONKS_KEY_FILE") else None)
    if not key:
        print("No SPORTMONKS_KEY or SPORTMONKS_KEY_FILE set.", file=sys.stderr)
        sys.exit(1)

    needles = [s.lower() for s in sys.argv[1:]] or [
        "premier league","la liga","serie a","bundesliga","ligue 1",
        "uefa champions league","champions league",
        "uefa europa league","europa league",
    ]

    hits = []
    for L in pages(base, key, "leagues"):
        name = (L.get("name") or "").lower()
        if any(n in name for n in needles):
            hits.append((L.get("id"), L.get("name")))
    print("Matches:", hits or "none")


if __name__ == "__main__":
    main()

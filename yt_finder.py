import csv
import time
import urllib.request
import urllib.parse
import json

API_KEY = "AIzaSyDroUVO0OsAU3KSsql2EeCfz9akIV2lP5w"

QUERIES = [
    "investice nemovitosti česko",
    "realitní podcast česky",
    "hypotéka byt investice",
    "jak koupit byt investice",
    "nemovitosti výnos pronájem",
    "realitní investor česko",
    "investiční byt portfolio",
    "reality investice česky 2026",
]

MIN_SUBS = 500
MAX_SUBS = 500_000


def api_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def search_channels(query):
    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 15,
        "relevanceLanguage": "cs",
        "key": API_KEY,
    })
    url = f"https://www.googleapis.com/youtube/v3/search?{params}"
    data = api_get(url)
    return [item["snippet"]["channelId"] for item in data.get("items", [])]


def get_channel_details(channel_ids):
    ids = ",".join(channel_ids)
    params = urllib.parse.urlencode({
        "part": "snippet,statistics",
        "id": ids,
        "key": API_KEY,
    })
    url = f"https://www.googleapis.com/youtube/v3/channels?{params}"
    data = api_get(url)
    results = []
    for item in data.get("items", []):
        stats = item.get("statistics", {})
        subs = int(stats.get("subscriberCount", 0))
        videos = int(stats.get("videoCount", 0))
        snippet = item["snippet"]
        results.append({
            "channel_id": item["id"],
            "name": snippet["title"],
            "description": snippet.get("description", "")[:200].replace("\n", " "),
            "subscribers": subs,
            "videos": videos,
            "url": f"https://www.youtube.com/channel/{item['id']}",
        })
    return results


def main():
    seen = set()
    all_channels = []

    for query in QUERIES:
        print(f"Hľadám: '{query}'...")
        try:
            channel_ids = search_channels(query)
            new_ids = [cid for cid in channel_ids if cid not in seen]
            if not new_ids:
                continue
            seen.update(new_ids)

            details = get_channel_details(new_ids)
            for ch in details:
                if MIN_SUBS <= ch["subscribers"] <= MAX_SUBS and ch["videos"] >= 5:
                    all_channels.append(ch)
                    print(f"  ✅ {ch['name']} — {ch['subscribers']:,} subs")
                else:
                    print(f"  ⏭ {ch['name']} — {ch['subscribers']:,} subs (skip)")

            time.sleep(1)
        except Exception as e:
            print(f"  ❌ Chyba: {e}")

    all_channels.sort(key=lambda x: x["subscribers"], reverse=True)

    seen_ids = set()
    unique = []
    for ch in all_channels:
        if ch["channel_id"] not in seen_ids:
            seen_ids.add(ch["channel_id"])
            unique.append(ch)

    output = "yt_channels.csv"
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "subscribers", "videos", "url", "description", "channel_id"])
        writer.writeheader()
        writer.writerows(unique)

    print(f"\n✅ Hotovo — nájdených {len(unique)} kanálov → {output}")
    print("\nTop 20:")
    for ch in unique[:20]:
        print(f"  {ch['subscribers']:>7,} subs | {ch['name']} | {ch['url']}")


if __name__ == "__main__":
    main()
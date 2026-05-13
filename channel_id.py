import urllib.request
import urllib.parse
import json
import time

API_KEY = "AIzaSyDroUVO0OsAU3KSsql2EeCfz9akIV2lP5w"
CHANNEL_ID = "UCyZzHuwcUdS_uXWYF_qMLWw"

def api_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def get_videos_with_comments(channel_id, max_videos=100):
    # Získaj uploads playlist
    params = urllib.parse.urlencode({
        "part": "contentDetails",
        "id": channel_id,
        "key": API_KEY,
    })
    data = api_get(f"https://www.googleapis.com/youtube/v3/channels?{params}")
    playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Získaj videá
    videos = []
    next_page = None
    while len(videos) < max_videos:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": API_KEY,
        }
        if next_page:
            params["pageToken"] = next_page
        data = api_get(f"https://www.googleapis.com/youtube/v3/playlistItems?{urllib.parse.urlencode(params)}")
        for item in data.get("items", []):
            videos.append({
                "video_id": item["contentDetails"]["videoId"],
                "title": item["snippet"]["title"],
            })
        next_page = data.get("nextPageToken")
        if not next_page:
            break
        time.sleep(0.5)

    # Získaj stats
    results = []
    for i in range(0, len(videos), 50):
        batch = videos[i:i+50]
        ids = ",".join(v["video_id"] for v in batch)
        params = urllib.parse.urlencode({
            "part": "statistics",
            "id": ids,
            "key": API_KEY,
        })
        data = api_get(f"https://www.googleapis.com/youtube/v3/videos?{params}")
        for item in data.get("items", []):
            vid_id = item["id"]
            stats = item.get("statistics", {})
            comments = int(stats.get("commentCount", 0))
            views = int(stats.get("viewCount", 0))
            title = next((v["title"] for v in batch if v["video_id"] == vid_id), "")
            results.append({
                "title": title[:60],
                "comments": comments,
                "views": views,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
            })
        time.sleep(0.5)

    results.sort(key=lambda x: x["comments"], reverse=True)
    return results

results = get_videos_with_comments(CHANNEL_ID, max_videos=100)

print(f"\nTop 20 videí podľa komentárov (z posledných 100):\n")
print(f"{'Komentáre':>10} {'Views':>8}  Názov")
print("-" * 80)
for r in results[:20]:
    print(f"{r['comments']:>10} {r['views']:>8}  {r['title']}")
    print(f"           {r['url']}")
    print()
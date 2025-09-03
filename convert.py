import requests
import json
import re
from pathlib import Path

M3U_URL = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/CricHD.m3u"
OUTPUT_FILE = Path("tv1.json")


def fetch_m3u(url: str) -> str:
    r = requests.get(url)
    r.raise_for_status()
    return r.text


def parse_m3u(m3u_text: str):
    lines = m3u_text.strip().splitlines()
    channels = []
    current = {}

    for line in lines:
        if line.startswith("#EXTINF"):
            # title বের করা
            match = re.search(r',\s*(.*)', line)
            title = match.group(1).strip() if match else "Unknown"

            # id বানানো
            channel_id = re.sub(r'\W+', '_', title.lower())

            current = {
                "id": channel_id,
                "title": title,
                "category": "Sports"  # Default category
            }

        elif line.startswith("http"):
            current["m3u8"] = line.strip()
            channels.append(current)
            current = {}

    return channels


def save_json(channels, output_file: Path):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)


def main():
    print("Fetching M3U playlist...")
    m3u_text = fetch_m3u(M3U_URL)
    print("Parsing channels...")
    channels = parse_m3u(m3u_text)
    print(f"Found {len(channels)} channels")
    save_json(channels, OUTPUT_FILE)
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

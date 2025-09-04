import requests
import json
import re
from pathlib import Path
from typing import List, Dict, Optional

# Provide one or more M3U/M3U8 playlist URLs to merge
M3U_URLS: List[str] = [
    "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/CricHD.m3u",
    # TheTVApp consolidated list (example from the user)
    # Fancode live events (user provided)
    "https://raw.githubusercontent.com/abusaeeidx/Ayna-Playlists-free-Version/refs/heads/main/playlist.m3u",
]
OUTPUT_FILE = Path("merge.json")


def fetch_m3u(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; M3U-Merger/1.0)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def _parse_extinf_attributes(extinf_line: str) -> Dict[str, str]:
    """Extract attributes like tvg-name, group-title from an #EXTINF line."""
    attrs: Dict[str, str] = {}
    # Find all key="value" pairs
    for match in re.finditer(r'(\w[\w-]*)\s*=\s*"([^"]*)"', extinf_line):
        key = match.group(1)
        value = match.group(2)
        attrs[key] = value
    return attrs


def _normalize_category(raw_category: Optional[str], title: str) -> str:
    if raw_category and raw_category.strip():
        cat = raw_category.strip()
        # Normalize common vendor prefixes like Fancode-*
        if cat.lower().startswith("fancode-"):
            cat = cat.split("-", 1)[1]
        # Collapse things like "Sports; Cricket" to "Cricket"
        if ";" in cat:
            parts = [p.strip() for p in cat.split(";") if p.strip()]
            if parts:
                cat = parts[-1]
        # Title-case simple categories
        if cat.lower() in {"cricket", "football", "soccer", "basketball", "baseball", "hockey", "news", "movies", "kids", "music"}:
            return cat.capitalize()
        # If contains specific sports keyword, map to that sport
        lc = cat.lower()
        if "cricket" in lc:
            return "Cricket"
        if any(k in lc for k in ["football", "soccer"]):
            return "Football"
        if any(k in lc for k in ["basketball", "nba"]):
            return "Basketball"
        if any(k in lc for k in ["baseball", "mlb"]):
            return "Baseball"
        if any(k in lc for k in ["hockey", "nhl"]):
            return "Hockey"
        if any(k in lc for k in ["news", "cnn", "bbc", "fox news"]):
            return "News"
        if any(k in lc for k in ["movie", "cinema", "film", "hbo"]):
            return "Movies"
        # Fallback to vendor-provided value if not recognized
        return cat

    # No group-title provided; infer from title
    t = title.lower()
    if "cricket" in t:
        return "Cricket"
    if any(k in t for k in ["football", "soccer"]):
        return "Football"
    if any(k in t for k in ["nba", "basketball"]):
        return "Basketball"
    if any(k in t for k in ["mlb", "baseball"]):
        return "Baseball"
    if any(k in t for k in ["nhl", "hockey"]):
        return "Hockey"
    if any(k in t for k in ["news", "cnn", "fox news", "bbc"]):
        return "News"
    if any(k in t for k in ["movie", "cinema", "film", "hbo"]):
        return "Movies"
    return "General"


def parse_m3u(m3u_text: str):
    lines = m3u_text.strip().splitlines()
    channels = []
    current = {}

    for line in lines:
        if line.startswith("#EXTINF"):
            attrs = _parse_extinf_attributes(line)
            # Title is after the last comma on the line
            match = re.search(r',\s*(.*)', line)
            title_from_suffix = match.group(1).strip() if match else "Unknown"
            title = attrs.get("tvg-name") or title_from_suffix or "Unknown"

            category: Optional[str] = _normalize_category(attrs.get("group-title"), title)

            channel_id = re.sub(r'\W+', '_', title.lower())

            current = {
                "id": channel_id,
                "title": title,
                "category": category
            }

        elif line.startswith("http"):
            current["m3u8"] = line.strip()
            channels.append(current)
            current = {}

    return channels


def is_m3u8_working(url: str) -> bool:
    """Return True if the m3u8 URL responds successfully."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; M3U-Merger/1.0)"}
    try:
        # Some origins block HEAD; fall back to GET if needed
        head = requests.head(url, headers=headers, allow_redirects=True, timeout=8)
        if 200 <= head.status_code < 300:
            return True
        # Try a lightweight GET
        with requests.get(url, headers=headers, stream=True, timeout=12) as r:
            if not (200 <= r.status_code < 300):
                return False
            # Read a tiny chunk to ensure it's actually accessible
            next(r.iter_content(chunk_size=256), None)
            return True
    except Exception:
        return False


def save_json(channels, output_file: Path):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)


def load_existing_json(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            # Keep only expected fields if present
            normalized: List[Dict] = []
            for ch in data:
                if not isinstance(ch, dict):
                    continue
                m3u8 = ch.get("m3u8") or ch.get("url")
                if not m3u8:
                    continue
                normalized.append({
                    "id": ch.get("id") or re.sub(r'\W+', '_', str(ch.get("title", "unknown")).lower()),
                    "title": ch.get("title", "Unknown"),
                    "category": ch.get("category", "General"),
                    "m3u8": m3u8,
                })
            return normalized
    except Exception:
        return []
    return []


def main():
    print("Fetching M3U playlists...")
    all_channels: List[Dict] = []

    for url in M3U_URLS:
        try:
            print(f"- Downloading: {url}")
            m3u_text = fetch_m3u(url)
            parsed = parse_m3u(m3u_text)
            print(f"  Parsed {len(parsed)} entries")
            all_channels.extend(parsed)
        except Exception as e:
            print(f"  Skipped {url}: {e}")

    # Dedupe by m3u8 URL
    deduped: Dict[str, Dict] = {}
    for ch in all_channels:
        m3u8_url = ch.get("m3u8", "").strip()
        if not m3u8_url:
            continue
        # Keep first occurrence
        if m3u8_url not in deduped:
            deduped[m3u8_url] = ch

    print(f"Checking availability of {len(deduped)} .m3u8 URLs...")
    working_channels: List[Dict] = []
    checked = 0
    for m3u8_url, ch in deduped.items():
        checked += 1
        ok = is_m3u8_working(m3u8_url)
        status = "OK" if ok else "DOWN"
        print(f"[{checked}/{len(deduped)}] {status} - {ch.get('title', '')}")
        if ok:
            working_channels.append(ch)

    print(f"Found {len(working_channels)} working channels out of {len(deduped)} unique entries")
    save_json(working_channels, OUTPUT_FILE)
    print(f"Saved working channels to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

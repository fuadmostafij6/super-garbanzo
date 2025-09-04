import requests
import json
import re
from pathlib import Path
from typing import List, Dict, Optional

# Provide one or more M3U/M3U8 playlist URLs to merge
M3U_URLS: List[str] = [
    "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/CricHD.m3u",
    "https://raw.githubusercontent.com/abusaeeidx/Toffee-playlist/refs/heads/main/ott_navigator.m3u",
    "https://raw.githubusercontent.com/abusaeeidx/T-Sports-Playlist-Auto-Update/refs/heads/main/combine_playlist.m3u",
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
    """Extract attributes like tvg-name, group-title, tvg-logo from an #EXTINF line."""
    attrs: Dict[str, str] = {}
    # Find all key="value" pairs
    for match in re.finditer(r'(\w[\w-]*)\s*=\s*"([^"]*)"', extinf_line):
        key = match.group(1)
        value = match.group(2)
        attrs[key] = value
    return attrs


def _parse_extvlcopt(line: str) -> Dict[str, str]:
    """Parse #EXTVLCOPT line for user agent and other options."""
    opts: Dict[str, str] = {}
    # Extract http-user-agent
    user_agent_match = re.search(r'http-user-agent=([^\\s]+)', line)
    if user_agent_match:
        opts["user_agent"] = user_agent_match.group(1)
    return opts


def _parse_exthttp(line: str) -> Dict[str, str]:
    """Parse #EXTHTTP line for cookies and other HTTP headers."""
    http_opts: Dict[str, str] = {}
    try:
        # Extract JSON content from the line
        json_match = re.search(r'#EXTHTTP:(\{.*\})', line)
        if json_match:
            json_str = json_match.group(1)
            data = json.loads(json_str)
            if "cookie" in data:
                http_opts["cookies"] = data["cookie"]
            # Add other HTTP options if present
            for key, value in data.items():
                if key != "cookie":
                    http_opts[f"http_{key}"] = value
    except (json.JSONDecodeError, KeyError):
        pass
    return http_opts


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
    current_opts = {}

    for line in lines:
        if line.startswith("#EXTINF"):
            attrs = _parse_extinf_attributes(line)
            # Title is after the last comma on the line
            match = re.search(r',\s*(.*)', line)
            title_from_suffix = match.group(1).strip() if match else "Unknown"
            # Clean up the title - remove any URL-like parts that might be included
            if title_from_suffix and ("http" in title_from_suffix or "w_300" in title_from_suffix or "w_240" in title_from_suffix):
                # If title contains URL parts, try to extract just the channel name
                if '", ' in title_from_suffix:
                    parts = title_from_suffix.split('", ')
                    if len(parts) > 1:
                        title_from_suffix = parts[-1].strip()
                elif '",' in title_from_suffix:
                    parts = title_from_suffix.split('",')
                    if len(parts) > 1:
                        title_from_suffix = parts[-1].strip()
                elif '\\", ' in title_from_suffix:
                    parts = title_from_suffix.split('\\", ')
                    if len(parts) > 1:
                        title_from_suffix = parts[-1].strip()
                elif '\\",' in title_from_suffix:
                    parts = title_from_suffix.split('\\",')
                    if len(parts) > 1:
                        title_from_suffix = parts[-1].strip()
            
            # Clean up special characters and formatting
            if title_from_suffix:
                # Remove leading "& " if present
                if title_from_suffix.startswith("& "):
                    title_from_suffix = title_from_suffix[2:]
                # Remove any remaining quotes
                title_from_suffix = title_from_suffix.strip('"\'')
                # Clean up any remaining URL artifacts
                if "/" in title_from_suffix and ("w_300" in title_from_suffix or "w_240" in title_from_suffix):
                    # Try to extract just the channel name after the last comma
                    if "," in title_from_suffix:
                        parts = title_from_suffix.split(",")
                        if len(parts) > 1:
                            title_from_suffix = parts[-1].strip()
            title = attrs.get("tvg-name") or title_from_suffix or "Unknown"

            category: Optional[str] = _normalize_category(attrs.get("group-title"), title)

            channel_id = re.sub(r'\W+', '_', title.lower())

            current = {
                "id": channel_id,
                "title": title,
                "category": category,
                "logo": attrs.get("tvg-logo", ""),
                "tvg_id": attrs.get("tvg-id", ""),
                "tvg_chno": attrs.get("tvg-chno", "")
            }
            # Reset options for new channel
            current_opts = {}

        elif line.startswith("#EXTVLCOPT"):
            # Parse VLC options (user agent, etc.)
            vlc_opts = _parse_extvlcopt(line)
            current_opts.update(vlc_opts)

        elif line.startswith("#EXTHTTP"):
            # Parse HTTP options (cookies, etc.)
            http_opts = _parse_exthttp(line)
            current_opts.update(http_opts)

        elif line.startswith("http"):
            current["m3u8"] = line.strip()
            # Add all collected options to the channel
            if current_opts:
                current.update(current_opts)
            channels.append(current)
            current = {}

    return channels


def is_m3u8_working(url: str, cookies: str = "", user_agent: str = "") -> bool:
    """Return True if the m3u8 URL responds successfully with optional cookies and user agent."""
    headers = {"User-Agent": user_agent or "Mozilla/5.0 (compatible; M3U-Merger/1.0)"}
    
    # Parse cookies if provided
    cookie_dict = {}
    if cookies:
        try:
            # Handle Toffee-style cookies (Edge-Cache-Cookie format)
            if "Edge-Cache-Cookie=" in cookies:
                # Extract the Edge-Cache-Cookie value
                edge_cookie_match = re.search(r'Edge-Cache-Cookie=([^;]+)', cookies)
                if edge_cookie_match:
                    edge_cookie_value = edge_cookie_match.group(1)
                    cookie_dict["Edge-Cache-Cookie"] = edge_cookie_value
            else:
                # Standard cookie parsing - split by semicolon and equals
                for cookie in cookies.split(';'):
                    if '=' in cookie:
                        name, value = cookie.strip().split('=', 1)
                        cookie_dict[name.strip()] = value.strip()
        except Exception as e:
            print(f"Cookie parsing error: {e}")
            pass
    
    try:
        # Try HEAD request first (faster)
        try:
            head = requests.head(url, headers=headers, cookies=cookie_dict, allow_redirects=True, timeout=10)
            if 200 <= head.status_code < 300:
                return True
        except Exception as e:
            print(f"HEAD request failed for {url}: {e}")
        
        # Fall back to GET request
        try:
            with requests.get(url, headers=headers, cookies=cookie_dict, stream=True, timeout=15) as r:
                if not (200 <= r.status_code < 300):
                    print(f"GET request failed for {url}: status {r.status_code}")
                    return False
                # Read a tiny chunk to ensure it's actually accessible
                try:
                    next(r.iter_content(chunk_size=256), None)
                    return True
                except Exception as e:
                    print(f"Content reading failed for {url}: {e}")
                    # Even if we can't read content, if we got a 200 response, consider it working
                    return True
        except Exception as e:
            print(f"GET request exception for {url}: {e}")
            return False
            
    except Exception as e:
        print(f"General exception for {url}: {e}")
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
                    "logo": ch.get("logo", ""),
                    "tvg_id": ch.get("tvg_id", ""),
                    "tvg_chno": ch.get("tvg_chno", ""),
                    "cookies": ch.get("cookies", ""),
                    "user_agent": ch.get("user_agent", ""),
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

    # Save all parsed channels first (for debugging)
    all_parsed_file = Path("all_parsed.json")
    save_json(list(deduped.values()), all_parsed_file)
    print(f"Saved all parsed channels to {all_parsed_file}")

    print(f"Checking availability of {len(deduped)} .m3u8 URLs...")
    working_channels: List[Dict] = []
    checked = 0
    
    # Debug: Test first few channels to see what's happening
    test_count = min(5, len(deduped))
    print(f"Testing first {test_count} channels for debugging...")
    
    for m3u8_url, ch in list(deduped.items())[:test_count]:
        checked += 1
        cookies = ch.get("cookies", "")
        user_agent = ch.get("user_agent", "")
        print(f"\nTesting channel {checked}: {ch.get('title', '')}")
        print(f"URL: {m3u8_url}")
        print(f"Has cookies: {bool(cookies)}")
        print(f"Has user agent: {bool(user_agent)}")
        
        ok = is_m3u8_working(m3u8_url, cookies, user_agent)
        status = "OK" if ok else "DOWN"
        print(f"[{checked}/{test_count}] {status} - {ch.get('title', '')}")
        if ok:
            working_channels.append(ch)
    
    # Continue with remaining channels
    for m3u8_url, ch in list(deduped.items())[test_count:]:
        checked += 1
        cookies = ch.get("cookies", "")
        user_agent = ch.get("user_agent", "")
        ok = is_m3u8_working(m3u8_url, cookies, user_agent)
        status = "OK" if ok else "DOWN"
        print(f"[{checked}/{len(deduped)}] {status} - {ch.get('title', '')}")
        if ok:
            working_channels.append(ch)

    print(f"Found {len(working_channels)} working channels out of {len(deduped)} unique entries")
    save_json(working_channels, OUTPUT_FILE)
    print(f"Saved working channels to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

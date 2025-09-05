
import re
import requests


def is_m3u8_working(url: str, cookies: str = "", user_agent: str = "") -> bool:
    """Return True if the m3u8 URL responds successfully with optional cookies and user agent."""
    import os

    # Use GitHub Actions user agent if in CI environment
    if os.environ.get("GITHUB_ACTIONS") and not user_agent:
        user_agent = "GitHub-Actions/1.0"

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


print(is_m3u8_working(url="http://142.93.220.229:80/starmovieselect/tracks-v1a1/mono.m3u8", ))
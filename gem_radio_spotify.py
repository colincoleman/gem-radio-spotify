#!/usr/bin/env python3
"""
Gem Radio New Wave → Spotify Playlist

Scrapes 7 days of track history from OnlineRadioBox and creates
a dated Spotify playlist using PKCE OAuth (no client secret needed).
"""

import json
import os
import re
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
import base64
import hashlib
import secrets
import subprocess
import threading

import requests
from bs4 import BeautifulSoup

CONFIG_FILE = Path.home() / ".gem_radio_spotify.json"
CACHE_FILE = Path.home() / ".gem_radio_spotify_token.json"
SEARCH_CACHE_FILE = Path.home() / ".gem_radio_spotify_search_cache.json"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-modify-public playlist-modify-private"
ONLINERADIOBOX_BASE = "https://onlineradiobox.com/ie/gemnewwave/playlist"

# ── Config ──────────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def get_client_id():
    cfg = load_config()
    if "client_id" in cfg:
        return cfg["client_id"]

    print("\nFirst-time setup: you need a Spotify Client ID.")
    print("1. Go to https://developer.spotify.com/dashboard")
    print("2. Click 'Create app'")
    print("3. Name it anything (e.g. 'Gem Radio Sync')")
    print(f"4. Set Redirect URI to exactly: {REDIRECT_URI}")
    print("5. Check 'Web API' under APIs used")
    print("6. Copy the Client ID from the app dashboard\n")

    client_id = input("Paste your Client ID here: ").strip()
    cfg["client_id"] = client_id
    save_config(cfg)
    print(f"Saved to {CONFIG_FILE}\n")
    return client_id

# ── PKCE OAuth ───────────────────────────────────────────────────────────────

def _open_browser(url):
    """Try Chrome, then Firefox, then fall back to the system default."""
    browsers = ["Google Chrome", "Firefox", "Brave Browser"]
    for app in browsers:
        result = subprocess.run(["open", "-a", app, url], capture_output=True)
        if result.returncode == 0:
            return
    webbrowser.open(url)

def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge

REQUIRED_SCOPES = set(SCOPES.split())

def _load_cached_token():
    if not CACHE_FILE.exists():
        return None
    data = json.loads(CACHE_FILE.read_text())
    granted = set(data.get("scope", "").split())
    if not REQUIRED_SCOPES.issubset(granted):
        print("Cached token is missing required scopes — re-authenticating…")
        CACHE_FILE.unlink()
        return None
    if data.get("expires_at", 0) > time.time() + 60:
        return data["access_token"]
    if "refresh_token" in data:
        return _refresh_token(data["refresh_token"], data["client_id"])
    return None

def _save_token(token_data, client_id):
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
    token_data["client_id"] = client_id
    CACHE_FILE.write_text(json.dumps(token_data))

def _refresh_token(refresh_token, client_id):
    resp = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    })
    if resp.ok:
        data = resp.json()
        data.setdefault("refresh_token", refresh_token)
        _save_token(data, client_id)
        return data["access_token"]
    return None

def get_access_token(client_id):
    cached = _load_cached_token()
    if cached:
        return cached

    verifier, challenge = _pkce_pair()
    state = secrets.token_hex(8)

    auth_url = "https://accounts.spotify.com/authorize?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    })

    auth_code = []
    server_ready = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = parse_qs(urlparse(self.path).query)
            if params.get("state", [None])[0] == state and "code" in params:
                auth_code.append(params["code"][0])
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8888), Handler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    print(f"\nOpen this URL in your browser to log in to Spotify:\n\n  {auth_url}\n")
    _open_browser(auth_url)
    server_thread.join(timeout=120)

    if not auth_code:
        print("Error: did not receive authorization code. Did you complete the login?")
        sys.exit(1)

    resp = requests.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code",
        "code": auth_code[0],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    resp.raise_for_status()
    token_data = resp.json()
    _save_token(token_data, client_id)
    return token_data["access_token"]

# ── Scraping ─────────────────────────────────────────────────────────────────

JINGLE_PATTERN = re.compile(
    r"^(YOURELISTENING|SWEEP|STINGER|STING|JIN|JINGLE|ID\b)",
    re.IGNORECASE,
)
TRAILING_NUMBER = re.compile(r"\s+\d+(\.\d+)?$")

def _clean_title(raw):
    """Strip trailing version/rotation numbers like 'Steppin Out 15' → 'Steppin Out'."""
    return TRAILING_NUMBER.sub("", raw).strip()

def scrape_day(day_offset):
    """Fetch one day's worth of tracks. day_offset=0 is today, 1 is yesterday, etc."""
    url = f"{ONLINERADIOBOX_BASE}/" if day_offset == 0 else f"{ONLINERADIOBOX_BASE}/{day_offset}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tracks = []
    for td in soup.select("td.track_history_item"):
        a = td.find("a")
        if not a:
            continue  # jingle/station ID with no link
        text = a.get_text(strip=True)
        if JINGLE_PATTERN.match(text):
            continue
        if " - " not in text:
            continue
        artist, _, title = text.partition(" - ")
        tracks.append((artist.strip(), _clean_title(title)))
    return tracks

def scrape_all_days(num_days=7):
    all_tracks = []
    seen = set()
    print(f"Scraping {num_days} days of Gem Radio New Wave history…")
    for day in range(num_days):
        try:
            day_tracks = scrape_day(day)
            new = [(a, t) for a, t in day_tracks if (a.lower(), t.lower()) not in seen]
            seen.update((a.lower(), t.lower()) for a, t in new)
            all_tracks.extend(new)
            print(f"  Day -{day}: {len(day_tracks)} plays, {len(new)} new unique tracks")
            time.sleep(0.5)
        except Exception as e:
            print(f"  Day -{day}: failed ({e})")
    print(f"Total unique tracks: {len(all_tracks)}")
    return all_tracks

# ── Spotify API ───────────────────────────────────────────────────────────────

class SpotifyRateLimitError(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after

class Spotify:
    BASE = "https://api.spotify.com/v1"

    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path, **params):
        for attempt in range(5):
            r = self.session.get(f"{self.BASE}{path}", params=params)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5)) + 1
                if wait > 60:
                    raise SpotifyRateLimitError(wait)
                print(f"  Rate limited — waiting {wait}s…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise SpotifyRateLimitError(3600)

    def _post(self, path, **kwargs):
        r = self.session.post(f"{self.BASE}{path}", **kwargs)
        if r.status_code == 403 and "playlists" in path:
            print("\n403 Forbidden: Spotify refused to create the playlist.")
            try:
                print(f"Spotify says: {r.json()}")
            except Exception:
                print(f"Response body: {r.text}")
            sys.exit(1)
        r.raise_for_status()
        return r.json()

    def search_track(self, artist, title):
        query = f"artist:{artist} track:{title}"
        data = self._get("/search", q=query, type="track", limit=1, market="IE")
        items = data.get("tracks", {}).get("items", [])
        return items[0]["uri"] if items else None

    def create_playlist(self, name, description=""):
        return self._post(
            "/me/playlists",
            json={"name": name, "public": True, "description": description},
        )["id"]

    def add_tracks(self, playlist_id, uris):
        for i in range(0, len(uris), 100):
            self._post(f"/playlists/{playlist_id}/tracks", json={"uris": uris[i:i+100]})
            time.sleep(0.2)

# ── Main ─────────────────────────────────────────────────────────────────────

def default_playlist_name():
    now = datetime.now()
    return f"Gem Radio New Wave {now.strftime('%b %y')}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync Gem Radio New Wave → Spotify playlist")
    parser.add_argument("--name", help="Playlist name (default: 'Gem Radio New Wave Jun 26')")
    parser.add_argument("--days", type=int, default=7, help="Days of history to scrape (default: 7)")
    parser.add_argument("--limit", type=int, default=None, help="Max tracks to add to the playlist")
    args = parser.parse_args()

    playlist_name = args.name or default_playlist_name()
    print(f"Creating playlist: '{playlist_name}'")

    client_id = get_client_id()
    token = get_access_token(client_id)
    sp = Spotify(token)

    tracks = scrape_all_days(args.days)
    if not tracks:
        print("No tracks found — check your internet connection.")
        sys.exit(1)

    search_cache = json.loads(SEARCH_CACHE_FILE.read_text()) if SEARCH_CACHE_FILE.exists() else {}

    print("\nSearching Spotify for tracks…")
    uris = []
    not_found = []
    api_calls = 0
    for i, (artist, title) in enumerate(tracks, 1):
        if args.limit and len(uris) >= args.limit:
            break
        key = f"{artist.lower()} - {title.lower()}"
        if key in search_cache:
            uri = search_cache[key]
        else:
            try:
                uri = sp.search_track(artist, title)
            except SpotifyRateLimitError as e:
                hours = e.retry_after / 3600
                print(f"\nSpotify daily quota hit. Progress saved ({api_calls} tracks searched, {len(uris)} found).")
                print(f"Run the script again in {hours:.1f} hours to continue from where it left off.")
                sys.exit(0)
            search_cache[key] = uri
            api_calls += 1
            SEARCH_CACHE_FILE.write_text(json.dumps(search_cache))
            time.sleep(0.5)
        if uri:
            uris.append(uri)
        else:
            not_found.append(f"{artist} - {title}")
        if i % 10 == 0:
            cached = i - api_calls
            print(f"  {i}/{len(tracks)}: {len(uris)} found, {api_calls} API calls, {cached} from cache…")

    seen_uris = set()
    unique_uris = []
    for uri in uris:
        if uri not in seen_uris:
            seen_uris.add(uri)
            unique_uris.append(uri)
    duplicates_removed = len(uris) - len(unique_uris)
    uris = unique_uris

    print(f"\nMatched {len(uris)}/{len(tracks)} tracks on Spotify ({duplicates_removed} duplicate URIs removed).")
    if not_found:
        print(f"Not found ({len(not_found)}):")
        for t in not_found:
            print(f"  {t}")

    if not uris:
        print("No tracks to add — exiting.")
        sys.exit(1)

    description = f"Gem Radio New Wave — scraped {datetime.now().strftime('%Y-%m-%d')}"
    playlist_id = sp.create_playlist(playlist_name, description)
    sp.add_tracks(playlist_id, uris)

    print(f"\nDone! Playlist '{playlist_name}' created with {len(uris)} tracks.")
    print(f"https://open.spotify.com/playlist/{playlist_id}")

if __name__ == "__main__":
    main()

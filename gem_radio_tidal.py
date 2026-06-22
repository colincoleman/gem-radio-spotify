#!/usr/bin/env python3
"""
Gem Radio New Wave → Tidal Playlist

Scrapes 7 days of track history from OnlineRadioBox and creates
a dated Tidal playlist. Uses Tidal's device code login — no developer
account or credentials required.
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import tidalapi
from bs4 import BeautifulSoup

SEARCH_CACHE_FILE = Path.home() / ".gem_radio_tidal_search_cache.json"
TIDAL_SESSION_FILE = Path.home() / ".gem_radio_tidal_session.json"
ONLINERADIOBOX_BASE = "https://onlineradiobox.com/ie/gemnewwave/playlist"

# ── Auth ─────────────────────────────────────────────────────────────────────

def get_session():
    session = tidalapi.Session()

    if TIDAL_SESSION_FILE.exists():
        data = json.loads(TIDAL_SESSION_FILE.read_text())
        try:
            session.load_oauth_session(
                data["token_type"],
                data["access_token"],
                data["refresh_token"],
                datetime.fromisoformat(data["expiry_time"]),
            )
            if session.check_login():
                return session
        except Exception:
            pass

    print("Logging in to Tidal…")
    session.login_oauth_simple()

    _save_session(session)
    return session

def _save_session(session):
    TIDAL_SESSION_FILE.write_text(json.dumps({
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expiry_time": session.expiry_time.isoformat(),
    }))

# ── Scraping ─────────────────────────────────────────────────────────────────

JINGLE_PATTERN = re.compile(
    r"^(YOURELISTENING|SWEEP|STINGER|STING|JIN|JINGLE|ID\b)",
    re.IGNORECASE,
)
TRAILING_NUMBER = re.compile(r"\s+\d+(\.\d+)?$")

def _clean_title(raw):
    return TRAILING_NUMBER.sub("", raw).strip()

def scrape_day(day_offset):
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
            continue
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

# ── Tidal search ─────────────────────────────────────────────────────────────

def search_track(session, artist, title):
    query = f"{artist} {title}"
    results = session.search(query, models=[tidalapi.Track], limit=5)
    tracks = results.get("tracks", [])
    if not tracks:
        return None
    # Prefer a result where the artist name roughly matches
    artist_lower = artist.lower()
    for track in tracks:
        track_artists = [a.name.lower() for a in track.artists]
        if any(artist_lower in a or a in artist_lower for a in track_artists):
            return track.id
    # Fall back to the top result
    return tracks[0].id

# ── Main ─────────────────────────────────────────────────────────────────────

def default_playlist_name():
    return f"Gem Radio New Wave {datetime.now().strftime('%b %y')}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync Gem Radio New Wave → Tidal playlist")
    parser.add_argument("--name", help="Playlist name (default: 'Gem Radio New Wave Jun 26')")
    parser.add_argument("--days", type=int, default=7, help="Days of history to scrape (default: 7)")
    args = parser.parse_args()

    playlist_name = args.name or default_playlist_name()
    print(f"Creating playlist: '{playlist_name}'")

    session = get_session()
    print(f"Logged in as: {session.user.email}\n")

    tracks = scrape_all_days(args.days)
    if not tracks:
        print("No tracks found — check your internet connection.")
        sys.exit(1)

    search_cache = json.loads(SEARCH_CACHE_FILE.read_text()) if SEARCH_CACHE_FILE.exists() else {}

    print("\nSearching Tidal for tracks…")
    track_ids = []
    not_found = []
    api_calls = 0
    for i, (artist, title) in enumerate(tracks, 1):
        key = f"{artist.lower()} - {title.lower()}"
        if key in search_cache:
            tid = search_cache[key]
        else:
            tid = search_track(session, artist, title)
            search_cache[key] = tid
            api_calls += 1
            SEARCH_CACHE_FILE.write_text(json.dumps(search_cache))
            time.sleep(0.3)

        if tid:
            track_ids.append(tid)
        else:
            not_found.append(f"{artist} - {title}")

    # Deduplicate IDs (preserving order) — same song can appear under slightly
    # different artist/title strings and resolve to the same Tidal track ID.
    seen_ids = set()
    unique_ids = []
    for tid in track_ids:
        if tid not in seen_ids:
            seen_ids.add(tid)
            unique_ids.append(tid)
    duplicates_removed = len(track_ids) - len(unique_ids)
    track_ids = unique_ids

        if i % 10 == 0:
            cached = i - api_calls
            print(f"  {i}/{len(tracks)}: {len(track_ids)} found, {api_calls} API calls, {cached} from cache…")

    print(f"\nMatched {len(track_ids)}/{len(tracks)} tracks on Tidal ({duplicates_removed} duplicate IDs removed).")
    if not_found:
        print(f"Not found ({len(not_found)}):")
        for t in not_found:
            print(f"  {t}")

    if not track_ids:
        print("No tracks to add — exiting.")
        sys.exit(1)

    playlist = session.user.create_playlist(
        playlist_name,
        f"Gem Radio New Wave — scraped {datetime.now().strftime('%Y-%m-%d')}",
    )
    # Tidal add_tracks accepts a list of track IDs
    playlist.add(track_ids)

    print(f"\nDone! Playlist '{playlist_name}' created with {len(track_ids)} tracks.")
    print(f"https://tidal.com/browse/playlist/{playlist.id}")

if __name__ == "__main__":
    main()

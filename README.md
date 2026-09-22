# Gem Radio New Wave → Spotify / Tidal

Scrapes 7 days of [Gem Radio New Wave](https://tunein.com/radio/Gem-Radio-New-Wave-s183330/) track history from [OnlineRadioBox](https://onlineradiobox.com/ie/gemnewwave/playlist/) and creates a dated playlist in your Spotify or Tidal account.

Gem Radio New Wave has a great selection of 70s/80s New Wave and Alternative — but listening to it via TuneIn means putting up with heavily compressed 128kbps streaming audio that sounds terrible on anything decent. This script lifts the playlist out of TuneIn and recreates it in Spotify or Tidal where you can listen at a proper bitrate.

Because the station runs a rotating catalog, scraping 7 days captures most of the unique tracks they play. Everything goes into a single playlist called *Gem Radio New Wave*: the first run creates it, and every later run adds whatever new tracks the station has played since. Nothing is ever removed, so the playlist grows as the station's rotation changes.

## Requirements

- Python 3.9+
- A Spotify or Tidal account (free or paid)

## Installation

```bash
git clone https://github.com/colincoleman/gem-radio-spotify.git
cd gem-radio-spotify
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Tidal (easiest — no setup required)

```bash
python gem_radio_tidal.py
```

On first run, the script prints a short URL. Open it in any browser, log in to Tidal, and the script continues automatically. Your session is cached locally so you won't be prompted again.

```bash
# Custom playlist name
python gem_radio_tidal.py --name "New Wave Classics"

# Scrape fewer days (e.g. 3 instead of 7)
python gem_radio_tidal.py --days 3

# Add at most 250 new tracks this run
python gem_radio_tidal.py --limit 250
```

Re-running with the same playlist name adds only newly played tracks — see the Spotify section below for details, it works the same way.

### Spotify (requires a free Developer App)

Spotify requires a Client ID to use their API. **Each person who wants to use the script needs their own free Developer App** — Spotify apps in development mode only allow the app owner to create playlists (others get a 403 error). Setup takes about 2 minutes:

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create a free app (name it anything)
2. Under **Redirect URIs**, add exactly: `http://127.0.0.1:8888/callback`
3. Copy the **Client ID** from the app dashboard

Then run the script — it will prompt you for the Client ID on first run and save it locally:

```bash
python gem_radio_spotify.py
```

```bash
# Custom playlist name
python gem_radio_spotify.py --name "New Wave Classics"

# Scrape fewer days
python gem_radio_spotify.py --days 3

# Add at most 250 new tracks this run (keeps you under Spotify's daily search quota)
python gem_radio_spotify.py --limit 250
```

Re-running **adds** newly played tracks to the existing playlist. It never removes anything, and tracks already in the playlist are skipped. `--limit` counts only new tracks, so repeated `--limit 250` runs keep growing the playlist. Use `--name` if you want a separate playlist, e.g. a snapshot for a particular month.

## How it works

1. **Scrapes** up to 7 days of play history from OnlineRadioBox, one page per day
2. **Deduplicates** tracks by `artist + title` (strips trailing rotation numbers like *Steppin Out 15* → *Steppin Out*)
3. **Searches** the streaming service API for each unique track. On Spotify, a miss is retried with a tidied title (*Into the Gap2* → *Into the Gap*, *ViennaCalling* → *Vienna Calling*, *(Remix)* dropped), then with a looser search that only accepts a result whose artist and title closely match (so *Banarama* still finds Bananarama)
4. **Deduplicates by track ID** — the same song listed under slightly different names resolves to one entry
5. **Creates a dated playlist** in your account, or adds only new tracks if a playlist with that name already exists

### Caching

Search results are cached in your home directory (`~/.gem_radio_tidal_search_cache.json` / `~/.gem_radio_spotify_search_cache.json`), including "not found" results. Re-running the script only makes API calls for tracks not seen before, so subsequent runs are much faster.

Cache entries are never expired. An entry is removed only if the service rejects that specific track when adding it to a playlist, so it gets searched again next time. Auth or API outages never touch the cache.

### Auth files

Credentials and tokens are stored in your home directory and never in this repo:

| File | Contents |
|------|----------|
| `~/.gem_radio_tidal_session.json` | Tidal OAuth token (auto-refreshed) |
| `~/.gem_radio_spotify_token.json` | Spotify OAuth token (auto-refreshed) |
| `~/.gem_radio_spotify.json` | Spotify Client ID |

## License

MIT

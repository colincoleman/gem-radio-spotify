# Gem Radio New Wave → Spotify / Tidal

Scrapes 7 days of [Gem Radio New Wave](https://tunein.com/radio/Gem-Radio-New-Wave-s183330/) track history from [OnlineRadioBox](https://onlineradiobox.com/ie/gemnewwave/playlist/) and creates a dated playlist in your Spotify or Tidal account.

Gem Radio New Wave is a continuous-rotation internet radio station playing 70s/80s New Wave and Alternative. Because it runs a rotating catalog, scraping 7 days captures most of the unique tracks they play. Running the script monthly and keeping old playlists gives you a nice snapshot archive — *Gem Radio New Wave Jun 26*, *Gem Radio New Wave Jul 26*, and so on.

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
```

### Spotify (requires a free Developer App)

Spotify requires a Client ID to use their API. You only need to do this once:

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
```

## How it works

1. **Scrapes** up to 7 days of play history from OnlineRadioBox, one page per day
2. **Deduplicates** tracks by `artist + title` (strips trailing rotation numbers like *Steppin Out 15* → *Steppin Out*)
3. **Searches** the streaming service API for each unique track
4. **Deduplicates by track ID** — the same song listed under slightly different names resolves to one entry
5. **Creates a dated playlist** in your account and adds all matched tracks

### Caching

Search results are cached in your home directory (`~/.gem_radio_tidal_search_cache.json` / `~/.gem_radio_spotify_search_cache.json`). Re-running the script — or running it again the following month — only makes API calls for tracks not seen before, so subsequent runs are much faster.

### Auth files

Credentials and tokens are stored in your home directory and never in this repo:

| File | Contents |
|------|----------|
| `~/.gem_radio_tidal_session.json` | Tidal OAuth token (auto-refreshed) |
| `~/.gem_radio_spotify_token.json` | Spotify OAuth token (auto-refreshed) |
| `~/.gem_radio_spotify.json` | Spotify Client ID |

## License

MIT

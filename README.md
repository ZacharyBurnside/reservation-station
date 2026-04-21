# Reservation Station

A real-time Manhattan restaurant reservation finder built with Plotly Dash. Queries the Resy API across 15 cuisine types concurrently to surface available tables for any date, time, and party size — then displays them on an interactive map alongside filterable restaurant tiles.

---

## What It Does

1. **Searches** Resy's API across 15 cuisine types simultaneously using concurrent threads
2. **Displays** available reservations as cards showing restaurant name, rating, price range, cuisine, neighborhood, and a direct booking link
3. **Maps** every available restaurant on an interactive Leaflet map of Manhattan
4. **Filters** results dynamically by price range, cuisine type, and neighborhood without re-querying the API

---

## Features

- **Concurrent API queries** — fetches all 15 cuisines in parallel (ThreadPoolExecutor) for fast results
- **Interactive map** — Leaflet map with markers for every available restaurant, tooltips on hover
- **Smart caching** — stores results in memory so filters apply instantly without repeat API calls
- **Retry logic** — automatically retries failed requests (502s, network errors) up to 3 times
- **Direct booking links** — each card links directly to the Resy booking page for that restaurant and date
- **Live filters** — filter by price ($–$$$$), cuisine type, and Manhattan neighborhood

---

## Cuisine Types Covered

American, Chinese, Cocktail Bar, French, Indian, Italian, Japanese, Korean, Mediterranean, Mexican, New American, Seafood, Steakhouse, Sushi, Thai

---

## Tech Stack

- **Python** — core logic and API integration
- **Plotly Dash** — web UI framework
- **Dash Leaflet** — interactive map component
- **Pandas** — data processing and deduplication
- **Resy API** — reservation availability data
- **concurrent.futures** — parallel API requests

---

## Usage

```bash
pip install dash dash-leaflet pandas requests pytz

python main_file.py
```

Then open `http://localhost:8050` in your browser.

**Search inputs:**
- Date (date picker)
- Time (e.g. `06:00 PM`)
- Party size (1–10)

Click **Find Reservations** to fetch live availability, then use **Apply Filters** to narrow results by price, cuisine, or neighborhood.

---

## How It Works

```
User inputs date/time/party size
        ↓
ThreadPoolExecutor fires 15 concurrent Resy API requests (one per cuisine)
        ↓
Results merged, deduplicated by reservation link
        ↓
Dash renders restaurant cards + Leaflet map markers
        ↓
Filters apply to cached data (no re-fetch)
```

The Resy API is queried at `https://api.resy.com/3/venuesearch/search` with a bounding box covering all of Manhattan (radius ~35km from center).

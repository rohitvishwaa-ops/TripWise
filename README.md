# TripWise

A smart travel planner: find real places in any city, save the ones you like,
and turn a city (or a route of several cities) into an editable day-by-day
itinerary that is stored in a database.

> Built for the **AWS Student Builder Group, VIT Chennai — Web Development
> Recruitment Task (TripWise: Smart Travel Planner)**.

## Submission links

| Item | Link |
|------|------|
| GitHub repository | https://github.com/rohitvishwaa-ops/TripWise |
| Live website (frontend) | `TODO: add deployed frontend URL` |
| Live API (backend) | `TODO: add deployed backend URL` (interactive docs at `<backend URL>/docs`) |
| Screenshots PDF | `TODO: <register no>_<Track>.pdf` |

## Chosen track

**Track 3: Full-Stack Development.** A responsive React frontend, a FastAPI
backend, a Neon PostgreSQL database and real external APIs (Geoapify), all
connected end to end.

## Project overview

Planning a trip usually means juggling maps, lists and notes across several
sites. TripWise keeps it in one place:

1. **Explore** real places around any city or coordinates (from Geoapify /
   OpenStreetMap), narrow them down with categories, radius and result count,
   sort them, and open any place for details.
2. **Save** interesting places to **My Trip**, a list that is kept in the
   database and survives refreshes.
3. **Plan** a trip: pick one city or a route of several, the number of days,
   a pace and your interests. TripWise builds a day-by-day itinerary from real
   nearby places and saves it.
4. **Edit** the itinerary: reorder stops, move them between days, add notes,
   remove stops, add saved places, or regenerate a single day.

There are no user accounts. Each browser gets an anonymous ID (a random UUID
kept in `localStorage`) and all saved data is scoped to it.

## Features

**Explore (destination discovery, search, filters, sorting)**
- Search by **city or place name** (resolved with Geoapify geocoding; if a name
  matches several places, you choose — nothing is guessed), by **coordinates**,
  or with **Use my location**.
- Filters: search radius (0.5–50 km), categories (Sights, Attractions, Museums,
  Parks, Nature, Beaches, Restaurants, Cafés, Hotels) and result count
  (20 / 50 / 100).
- Sorting: relevance, name A to Z, name Z to A (ignores case and accents).
- Results as responsive cards with category tags and coordinates.

**Destination details**
- Dialog with categories, full address, coordinates and an OpenStreetMap link,
  plus **Add to My Trip** / **Remove**.

**My Trip (persistent itinerary)**
- Saved places in the order added, with Remove and a clear empty state.
- Stored in Neon PostgreSQL per browser ID; duplicates are prevented.

**Plan (automatic trip planning)**
- **Single-city or multi-city** trips (up to 10 cities in travel order,
  1–30 days in total; days set per city).
- Pace (Relaxed 2 / Balanced 3 / Packed up to 5 stops a day) and interests
  (Culture, History, Nature, Food, Shopping, Nightlife, Beaches,
  Entertainment).
- Real places only, grouped into days of nearby stops, ordered nearest-first
  and labelled Morning / Afternoon / Evening (an order, not a schedule).
  Multi-city trips get a "Travel to [next city]" step between cities.
- Saved trips list ("Your trips") and trip pages that reopen after refresh,
  with a destination photo (Wikipedia) when one is available.

**Itinerary editing**
- Move stops up/down, move a stop to another day, add a personal note, remove
  a stop (with confirmation), add a place from My Trip (to a chosen day or the
  closest one), and regenerate one day without touching the others.
- Every change is saved immediately; success and errors are announced.

**Reliability and UX**
- Loading skeletons, empty states, inline validation, and clear error messages
  with retry for network/API failures.
- Responsive layout (desktop and phone), keyboard accessible, visible focus,
  screen-reader announcements, light and dark themes.

## Technologies used

| Role | Technology (installed version) |
|------|--------------------------------|
| Frontend framework | React 19.3 (JavaScript, JSX) |
| Build tool / dev server | Vite 8.3 with `@vitejs/plugin-react` |
| Styling | Plain CSS with design tokens (no CSS framework) |
| Icons and font | `@phosphor-icons/react` 2.1, `@fontsource-variable/bricolage-grotesque` 5.3 (self-hosted) |
| Frontend linting | oxlint 1.88 |
| Backend framework | FastAPI 0.143 (Python 3.11) with Pydantic 2.14 for validation |
| ASGI server | Uvicorn 0.54 |
| HTTP client (external APIs) | httpx 0.28 |
| Database | Neon (serverless PostgreSQL) |
| ORM / driver | SQLAlchemy 2.1, psycopg 3.3 |
| Configuration | python-dotenv |
| Backend tests | pytest |
| Place data | Geoapify **Places API** and **Geocoding API** (data © OpenStreetMap contributors) |
| Destination photos | Wikipedia REST API (page summary lead image; no key) |
| Optional, off by default | Google Gemini API via REST (see [Optional AI selection](#optional-ai-selection-off-unless-configured)) |

```
TripWise/
├── frontend/   React + Vite app (dev server on http://localhost:5173)
└── backend/    FastAPI app (dev server on http://localhost:8000)
```

The browser only talks to the TripWise backend; the backend talks to Geoapify
and Neon. API keys and the database URL never reach the frontend.

## Setup

### Prerequisites

- Node.js 20+ and npm
- Python 3.10+
- A free [Geoapify](https://myprojects.geoapify.com) API key
- A free [Neon](https://console.neon.tech) PostgreSQL project

### Backend

```bash
cd backend
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# macOS/Linux:          source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in GEOAPIFY_API_KEY and DATABASE_URL
python init_db.py           # optional; tables are also created on startup
uvicorn main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/health` → `{"status": "ok"}`.
Interactive API documentation: http://localhost:8000/docs.

CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` by default
(override with `CORS_ORIGINS` in `backend/.env`, comma-separated).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (start the backend first).
The API base URL defaults to `http://localhost:8000` (override with
`VITE_API_URL` in `frontend/.env`; see `frontend/.env.example`). Vite reads
`.env` at startup, so restart `npm run dev` after changing it.

Production build: `npm run build` (output in `frontend/dist/`). Lint: `npm run lint`.

### Environment variables

Copy `backend/.env.example` to `backend/.env` and fill it in. Never commit
`.env` files (they are excluded by `.gitignore`).

| Variable | Where | Required | Purpose |
|----------|-------|----------|---------|
| `GEOAPIFY_API_KEY` | backend | yes | Geoapify Places + Geocoding (server-side only) |
| `DATABASE_URL` | backend | yes | Neon PostgreSQL connection string |
| `CORS_ORIGINS` | backend | for deployment | comma-separated frontend origins allowed to call the API |
| `GEMINI_API_KEY` | backend | no — leave unset | enables the optional AI layer; off when empty |
| `GEMINI_MODEL` | backend | no | AI model name (default `gemini-3.5-flash-lite`) |
| `VITE_API_URL` | frontend (build time) | for deployment | backend base URL (default `http://localhost:8000`) |

### Configuration

Set `GEOAPIFY_API_KEY` in `backend/.env` (get a key at
https://myprojects.geoapify.com). The key is only used server-side and is never
returned in responses. Without it, `/api/places` and `/api/geocode` respond
with `503`.

### Database (Neon PostgreSQL)

1. Create a project at https://console.neon.tech and copy its connection string
   (Connect → connection string).
2. Put it in `backend/.env` as `DATABASE_URL` (see `backend/.env.example`).
   - `postgres://` / `postgresql://` URLs are used with the `psycopg` (v3) driver.
   - `sslmode=require` is added automatically for non-local hosts if the URL
     doesn't set `sslmode`; explicit settings such as `channel_binding=require`
     are kept.
3. Create the tables: `python init_db.py` (from `backend/`). The app also runs
   this on startup.

Initialization only creates missing tables (`CREATE TABLE IF NOT EXISTS`
semantics). It never drops, truncates or migrates existing tables or data.
If the database is unreachable at startup, the error is logged, `/health` and
`/api/places` keep working, and itinerary requests return `503`.

Tables:

- `itinerary_items` (My Trip): `id`, `trip_id`, `place_id`, `name`, `address`,
  `latitude`, `longitude`, `categories` JSON, `created_at`; unique on
  `(trip_id, place_id)`.
- `trips`, `trip_cities`, `trip_days`, `trip_activities` (planned trips),
  linked by foreign keys with `ON DELETE CASCADE` and guarded by check/unique
  constraints.

## API documentation

Full interactive documentation (every endpoint, parameter, request body and
error response) is generated by FastAPI at **`/docs`** (Swagger UI) and
`/openapi.json` — locally http://localhost:8000/docs.

All itinerary and trip endpoints require the **`X-Trip-ID`** header: the
browser's anonymous ID, a UUID in canonical `8-4-4-4-12` form. A missing or
malformed header returns `400`; data owned by another ID is reported as `404`.
Errors use the shape `{"detail": "..."}` and never contain keys or credentials.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/places` | Real places around a point (Geoapify Places), with categories, radius, limit and sort |
| `GET` | `/api/geocode` | City / place name → candidate locations (Geoapify Geocoding) |
| `GET`, `POST` | `/api/itinerary` | List / add My Trip places |
| `DELETE` | `/api/itinerary/{place_id}` | Remove a saved place |
| `GET`, `POST` | `/api/trips` | List trips / create a trip (optionally generated) |
| `GET`, `PATCH`, `DELETE` | `/api/trips/{trip_id}` | Read / update / delete a trip |
| `PUT` | `/api/trips/{trip_id}/days/{day_id}/order` | Reorder a day |
| `PATCH`, `DELETE` | `/api/trips/{trip_id}/activities/{activity_id}` | Edit note or move / remove a stop |
| `POST` | `/api/trips/{trip_id}/activities` | Add a saved place to a trip |
| `POST` | `/api/trips/{trip_id}/days/{day_id}/regenerate` | Rebuild one day |
| `GET` | `/api/planner/status` | Whether the optional AI layer is configured |

Detailed request/response examples follow.

### Itinerary API — `/api/itinerary`

Itineraries are anonymous. The browser generates a trip ID once (e.g.
`crypto.randomUUID()`), keeps it (e.g. in `localStorage`) and sends it as the
`X-Trip-ID` header on every itinerary request. It must be a UUID in the
standard `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` form; all operations are scoped
to that trip.

| Method   | Path                          | Success | Notes |
|----------|-------------------------------|---------|-------|
| `GET`    | `/api/itinerary`              | `200`   | `{trip_id, count, places: [...]}`, oldest first |
| `POST`   | `/api/itinerary`              | `201`   | body is a place as returned by `/api/places`; returns the saved place |
| `DELETE` | `/api/itinerary/{place_id}`   | `204`   | |

POST body:

| Field        | Required | Rules |
|--------------|----------|-------|
| `id`         | yes      | Geoapify place ID; 1–512 chars of `A-Z a-z 0-9 _ . : -` |
| `latitude`   | yes      | -90 to 90 |
| `longitude`  | yes      | -180 to 180 |
| `name`       | no       | up to 500 chars |
| `address`    | no       | up to 1000 chars |
| `categories` | no       | list of up to 50 strings, 1–100 chars each |

Errors: `400` missing or invalid `X-Trip-ID`, `422` invalid body or place ID,
`409` place already in this trip, `404` place not in this trip, `503` database
not configured or unavailable. Error responses never include credentials.

Examples (PowerShell users: use `curl.exe`):

```bash
TRIP=3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6b

curl -H "X-Trip-ID: $TRIP" http://localhost:8000/api/itinerary

curl -X POST http://localhost:8000/api/itinerary \
  -H "X-Trip-ID: $TRIP" -H "Content-Type: application/json" \
  -d '{"id":"51e6...","name":"Louvre Museum","address":"Rue de Rivoli, 75001 Paris, France","latitude":48.8606,"longitude":2.3376,"categories":["entertainment.museum"]}'

curl -X DELETE -H "X-Trip-ID: $TRIP" http://localhost:8000/api/itinerary/51e6...
```

### `GET /api/places` — destination discovery

Searches the Geoapify Places API around a point.

| Param        | Required | Default     | Notes                                                        |
|--------------|----------|-------------|--------------------------------------------------------------|
| `latitude`   | yes      |             | -90 to 90                                                    |
| `longitude`  | yes      |             | -180 to 180                                                  |
| `radius`     | no       | `5000`      | meters, 1 to 50000                                           |
| `categories` | no       | `tourism`   | comma-separated [Geoapify categories](https://apidocs.geoapify.com/docs/places/#categories), max 20 |
| `limit`      | no       | `20`        | 1 to 100                                                     |
| `sort`       | no       | `relevance` | `relevance` (provider order), `name`, `name_desc`; unnamed places go last |

Example:

```bash
curl "http://localhost:8000/api/places?latitude=48.8566&longitude=2.3522&radius=2000&categories=tourism.sights,entertainment.museum&limit=5&sort=name"
```

```json
{
  "count": 1,
  "places": [
    {
      "id": "51...",
      "name": "Louvre Museum",
      "address": "Louvre Museum, Rue de Rivoli, 75001 Paris, France",
      "latitude": 48.8606,
      "longitude": 2.3376,
      "categories": ["entertainment", "entertainment.museum"]
    }
  ]
}
```

Errors: `422` invalid input, `400` provider rejected the request (e.g. unknown
category), `503` key not configured or provider rate limit, `504` provider
timeout, `502` provider unreachable or other provider error. An empty search
returns `200` with `{"count": 0, "places": []}`.

Name sorting ignores case and accents (`À la mémoire` sorts with `A`, `Église`
with `E`); places without a name are listed last.

### `GET /api/geocode` — find a location by name

Turns a city, landmark or address into coordinates using the Geoapify
Geocoding API, so the result can be passed to `/api/places`.

| Param   | Required | Default | Notes                                   |
|---------|----------|---------|-----------------------------------------|
| `text`  | yes      |         | 2 to 200 characters (whitespace is collapsed) |
| `limit` | no       | `5`     | 1 to 10 candidates                      |

```bash
curl "http://localhost:8000/api/geocode?text=Kyoto"
```

```json
{
  "query": "Kyoto",
  "count": 1,
  "confident": true,
  "results": [
    {
      "id": "51...",
      "name": "Kyoto",
      "address": "Kyoto, Japan",
      "latitude": 35.0115754,
      "longitude": 135.7681441,
      "type": "city",
      "country": "Japan",
      "confidence": 1.0
    }
  ]
}
```

`confident` is `true` only when the top result has confidence ≥ 0.9 and no
other result scores ≥ 0.6. Otherwise (e.g. `Paris`, which matches Paris in
France and in Texas) clients should let the user choose; the frontend never
picks an uncertain match on its own. No matches returns `200` with
`count: 0`. Errors match `/api/places`: `422` invalid input, `503` key not
configured or rate limit, `504` timeout, `502` provider unreachable or error.

### Trips API — `/api/trips`

Stores planned trips for the browser identified by `X-Trip-ID` (same rules as
the itinerary API). A trip owned by another browser returns `404`, exactly like
a missing one. Creating a trip stores its cities and one day per trip day; with
`"generate": true` the days are filled automatically with real places from each
city (see *Automatic planner* and *Multi-city trips* below).

| Method   | Path                  | Success | Notes |
|----------|-----------------------|---------|-------|
| `POST`   | `/api/trips`          | `201`   | full trip (cities, days, activities) |
| `GET`    | `/api/trips`          | `200`   | `{count, trips: [summary]}`, most recently updated first |
| `GET`    | `/api/trips/{id}`     | `200`   | full trip |
| `PATCH`  | `/api/trips/{id}`     | `200`   | any of `title`, `start_date` (or `null`), `pace`, `interests`; day dates follow `start_date` |
| `DELETE` | `/api/trips/{id}`     | `204`   | also deletes its cities, days and activities |

```json
POST /api/trips
{
  "title": "Kansai in autumn",
  "start_date": "2026-11-03",
  "pace": "relaxed",
  "interests": ["culture", "food"],
  "cities": [
    {"name": "Kyoto", "address": "Kyoto, Japan", "latitude": 35.0116, "longitude": 135.7681, "days": 2},
    {"name": "Osaka", "address": "Osaka, Japan", "latitude": 34.6937, "longitude": 135.5023, "days": 1}
  ]
}
```

Rules: 1–10 cities, 1–30 days per city and 30 days in total (at least 2 for
a multi-city trip); give `days` for every city, or a trip-level `num_days`
that is shared out (see below); `pace` is
`relaxed`, `balanced` or `packed`; `interests` from `culture`, `history`,
`nature`, `food`, `shopping`, `nightlife`, `beaches`, `entertainment`; `title` up to 120 chars
(defaults to "Trip to …"). Unknown fields are rejected. Errors: `400` bad
`X-Trip-ID`, `422` invalid input or trip ID, `404` not found, `503` storage
unavailable.

#### Automatic planner (`"generate": true`)

Deterministic, no AI. For each city in the trip it:

1. fetches real places from Geoapify, one request per interest (Culture →
   museums and cultural venues, History → sights and heritage, Nature → parks
   and natural areas, Food → restaurants and cafés, Shopping, Nightlife,
   Beaches, Entertainment → zoos, aquariums, theme parks, cinemas…; no
   interests → general sightseeing), within 10 km, widening once to 25 km if
   there are too few;
2. drops unnamed places and duplicates, and avoids picking places within
   150 m of each other unless nothing else is left;
3. picks places in turn from each interest, up to 2 / 3 / 5 per day for
   relaxed / balanced / packed;
4. groups them into days of nearby places and orders each day nearest-first;
5. labels them Morning / Afternoon / Evening in visiting order.

It never invents places, exact times, opening hours, prices or travel times.
Slots are an order, not a schedule. Everything is fetched and planned before
anything is saved; the trip, days and activities are then written in one
transaction. If Geoapify fails (`502`/`503`/`504`, message starts with
"Could not generate the itinerary.") or finds fewer places than days (`422`
"Not enough places found near …"), nothing is saved. If it finds some but not
enough for the chosen pace, the trip is created with fewer activities per day
and the response includes a `warnings` message.

#### Multi-city trips

Send the cities in travel order. Each city either has its own `days`, or the
trip has `num_days` and cities without `days` share it evenly (earlier cities
get any extra day; every city gets at least one). The same city twice in a row
is rejected (`422`); returning to a city later is allowed.

```json
POST /api/trips
{
  "generate": true,
  "pace": "balanced",
  "interests": ["culture"],
  "num_days": 5,
  "cities": [
    {"name": "Kyoto", "latitude": 35.0116, "longitude": 135.7681, "days": 3},
    {"name": "Osaka", "latitude": 34.6937, "longitude": 135.5023}
  ]
}
```

Each city is planned separately with the automatic planner (its own Geoapify
search around that city, the trip's interests and pace), and a place used in an
earlier city is never reused. The last day of every city except the final one
ends with a `"kind": "transfer"` activity named "Travel to [next city]" with no
coordinates, slot, transport mode, times, costs or durations. All cities are
fetched and planned before anything is saved, so if any city's search fails
(`502`/`503`/`504`, "Could not generate the itinerary for Osaka. …") or has too
few places (`422`, naming the city) nothing is stored. AI planning is
single-city only for now (`422` for multi-city trips).

Editing understands travel steps: they keep no time-of-day label, can be
reordered within their day, given a note or removed, but not moved to another
day; added or moved stops go before a trailing travel step; regenerating a day
keeps its travel step.

In the UI, choose **Several cities** in the Plan form, add up to 10 cities in
travel order (move them earlier or later, or remove them), and set days per
city; the total is shown. Every city is resolved with `/api/geocode`, and if a
name matches several places you must pick one before anything is generated.
Tip: Geoapify resolves some bare names to regions (for example "Osaka" gives
Osaka Prefecture); add the country ("Osaka, Japan") to get the city.

#### Editing a trip

All editing endpoints return the full, updated trip and are scoped like the
rest of `/api/trips`: the trip must belong to `X-Trip-ID`, and any day or
activity in the path or body must belong to that trip (`404` otherwise, or
`422` for a foreign `day_id` in a body). After every change a day's activities
are renumbered and their Morning / Afternoon / Evening labels follow the new
order. Each request is a single transaction.

| Method | Path | Body | Notes |
|--------|------|------|-------|
| `PUT` | `/api/trips/{id}/days/{day_id}/order` | `{"activity_ids": [3, 1, 2]}` | must list every activity of that day exactly once (duplicates, missing or foreign ids → `422`) |
| `PATCH` | `/api/trips/{id}/activities/{activity_id}` | `{"note": "…"}` and/or `{"day_id": 12, "position": 0}` | note up to 500 chars (blank removes it); moving appends to the target day unless `position` is given |
| `DELETE` | `/api/trips/{id}/activities/{activity_id}` | | remaining stops are renumbered |
| `POST` | `/api/trips/{id}/activities` | `{"place": {…saved place…}, "day_id": null, "note": null}` | adds a My Trip place; without `day_id` it goes to the day whose stops are closest; `409` if the place is already in the trip |
| `POST` | `/api/trips/{id}/days/{day_id}/regenerate` | | replaces that day with fresh automatic suggestions |

Regenerating a day reuses the automatic planner: it fetches real places for
the trip's interests, never uses a place already planned on another day,
prefers places that are not already on this day, and leaves every other day
untouched. Places are fetched before anything changes and the replacement is
one transaction, so an upstream error (`502`/`503`/`504`), "no places left"
(`422`) or a database error (`503`) leaves the day as it was. Notes on the
regenerated day are replaced along with its stops.

#### Optional AI selection (off unless configured)

Set `GEMINI_API_KEY` (and optionally `GEMINI_MODEL`, default
`gemini-3.5-flash-lite`) in `backend/.env` to enable it. Without a key nothing
changes. `GET /api/planner/status` returns `{"ai_available": bool,
"default_planner": "auto"}` and never returns the key.

Requests opt in with `"planner": "ai"` on `POST /api/trips` (with
`generate: true`) or as the JSON body of
`POST /api/trips/{id}/days/{day_id}/regenerate`; the default is `"auto"`.

- The AI only **chooses and groups** real candidate places that the backend
  already fetched from Geoapify and cleaned. It sees them under opaque aliases
  (`p1`, `p2`, …) with name, broad category, interest and rounded coordinates,
  plus the city name, interests and stops-per-day limit. Trip titles, notes,
  browser IDs and keys are never sent.
- The server rejects any answer with unknown or repeated places, the wrong
  number of days, or too many or too few stops in a day. Each day is still
  ordered nearest-first by the server and labelled Morning/Afternoon/Evening.
  Suggested day themes that mention numbers, times, prices, tickets or
  distances are replaced by the automatic theme.
- Missing key, timeout (8 s), rate limiting (then a 60 s pause), error
  responses, blocked or malformed output: the automatic planner is used and
  the response carries a warning ("AI selection was unavailable, so this plan
  was built automatically."). Trips, days and activities record `ai` or `auto`.
- The key is sent in a request header (never in the URL) and is never logged.
  The Gemini free tier's terms apply: prompts may be used to improve Google's
  products and read by human reviewers, users must be 18+, and only paid
  services may be offered to users in the EEA, UK and Switzerland. Keep it off
  in public deployments unless those terms are acceptable.
- Tests mock every Gemini request; the test suite also blocks all outbound
  network connections, so it cannot reach the real service.
- The frontend has no AI switch; the deployed app plans automatically.

## Frontend

### Views

- **Explore** (`#explore`): search by **place name** (default; e.g. "Kyoto" or
  "Central Park, New York") or switch to **coordinates** / use the browser's
  location. Choose a radius (0.5 to 50 km), optional categories and result
  count, then search. If a name matches several locations, the form lists them
  and searches only after you pick one. Results can be re-sorted by relevance
  or name. Selecting a place opens its details.
- **Plan** (`#plan`, `#plan/<trip id>`): a form for **one city or several
  cities** (each resolved with `/api/geocode`; you choose when several places
  match), days (1 to 30 in total), an optional start date, pace, interests and
  an optional trip name. It calls `POST /api/trips` with `generate: true` and
  opens the saved trip: a photo header, then one card per day with its theme
  and stops labelled Morning / Afternoon / Evening, each with address,
  categories and a map link (plus "Travel to …" steps between cities).
  Warnings (e.g. fewer places than the pace asks for) are shown above the days.
  Saved trips are listed under "Your trips" (`GET /api/trips`) and reopen from
  the database (`GET /api/trips/{id}`), so a refresh never loses a plan.
  Each stop can be moved up or down, moved to another day, given a personal
  note, or removed (with a confirmation). Places from My Trip can be added to
  the closest day or a chosen one, and any day can be regenerated. Every
  change is saved immediately and shown in a message at the bottom of the
  screen.
- **Destination details** (modal dialog): categories, address, coordinates, an
  OpenStreetMap link, and Add to My Trip / Remove.
- **My Trip** (`#trip`): saved places in the order added, with Remove.

### How it talks to the backend

- Only the TripWise backend is called for data (`/api/geocode`, `/api/places`,
  `/api/itinerary`, `/api/trips`). Geoapify is never called from the browser
  and no API key exists in frontend code.
- Destination photos in Plan come from Wikipedia's public REST API (the lead
  image of the city's article, no key needed) and link back to the article.
  If there is no suitable image, a placeholder is shown instead.
- On first visit the browser generates a trip ID with `crypto.randomUUID()`
  and stores it in `localStorage` (`tripwise.tripId`). Every itinerary request
  sends it as `X-Trip-ID`. Clearing site data starts a new, empty trip.
- Saving a place already in the trip (HTTP 409, e.g. from another tab) is shown
  as "already in My Trip" and the list is re-synced. Network failures, timeouts
  and API errors show an inline message with a retry.
- Routing uses URL hashes (`#explore`, `#plan`, `#plan/<id>`, `#trip`), so the
  built site works on any static host without server rewrite rules.

### Source layout

```
backend/
├── main.py              app, CORS, routers, OpenAPI docs
├── places.py            GET /api/places (Geoapify Places)
├── geocode.py           GET /api/geocode (Geoapify Geocoding)
├── itinerary.py         /api/itinerary (My Trip) + X-Trip-ID handling
├── trips.py             /api/trips create/list/read/update/delete + generation
├── trip_edits.py        reorder, move, note, remove, add, regenerate
├── planner.py           deterministic automatic planner
├── ai_planner.py        optional Gemini layer (off unless configured)
├── database.py          SQLAlchemy models, engine, table creation
├── api_docs.py          OpenAPI documentation helpers
├── init_db.py           create missing tables
└── tests/               pytest suite (mocked APIs, in-memory SQLite)

frontend/src/
├── App.jsx              shell: header, nav, views, details dialog, footer
├── components/          ExploreView, SearchForm, PlaceCard, PlaceDialog, TripView, DataCredit
├── components/plan/     PlanView, PlanForm, CityRoute, TripList, TripDetail, DayCard, StopItem, AddSavedPlace, DestinationImage
├── state/               TripContext (My Trip), Announcer (live region), hash routing
├── lib/                 api.js (backend client), tripId.js, format.js, planOptions.js, destinationImage.js
├── index.css            design tokens (light/dark), base styles
└── app.css              component styles
```

## Testing

Verified on 2026-10-16:

| Check | Command | Result |
|-------|---------|--------|
| Backend test suite | `cd backend && pip install -r requirements-dev.txt && pytest` | **485 passed** (with and without `backend/.env`) |
| Frontend lint | `cd frontend && npm run lint` | passes, no warnings |
| Frontend production build | `cd frontend && npm run build` | succeeds |

The backend tests mock Geoapify and Gemini, use an in-memory SQLite database
(with foreign keys enforced) and block all outbound network connections, so
they need no API key, no `DATABASE_URL` and no internet access; `DATABASE_URL`
and `GEMINI_*` values from `.env` are ignored during tests. They cover places,
geocoding, My Trip, trip CRUD, ownership checks, the automatic planner,
multi-city planning, itinerary editing, transactions/rollback, the optional AI
layer and the OpenAPI documentation.

During development the full user journeys were also checked in a real browser
with Puppeteer scripts that are **not part of this repository** (Explore,
city search with ambiguous matches, My Trip, single- and multi-city planning,
itinerary editing, error/empty/loading states, phone layout) and with an
axe-core accessibility scan (WCAG 2.1 A/AA, no violations on the scanned
views); all passed on 2026-10-16.

## Deployment configuration

Deploy the backend and frontend separately. Use **free tiers only**; nothing
here requires paid plans.

**Backend (any Python host)**
- Install: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT` (from `backend/`)
- Health check path: `/health`
- Environment: `GEOAPIFY_API_KEY`, `DATABASE_URL`, and `CORS_ORIGINS` set to the
  exact deployed frontend origin (e.g. `https://your-frontend.example`, no
  trailing slash). **Leave `GEMINI_API_KEY` unset** so AI stays disabled.
- Tables are created automatically on first start (or run `python init_db.py`).

**Frontend (any static host)**
- Build with `VITE_API_URL` set to the deployed backend URL:
  `npm ci && npm run build`, then publish `frontend/dist/`.
- No rewrite rules are needed (hash-based routing).

**Safety**
- Set secrets only in the host's environment settings; never commit `.env`.
  `.gitignore` excludes `.env`, `.env.*` (except `.env.example`),
  `node_modules`, virtual environments, `dist` and Python caches.
- Keys stay on the backend; the frontend only knows `VITE_API_URL`.
- Free-tier quotas (from the providers' pricing pages): Geoapify free plan
  3,000 credits/day and up to 5 requests/second (about 1 credit per simple
  Places or Geocoding request; one generated trip uses roughly one request per
  interest per city). Neon free plan: 100 CU-hours per project and 1 GB
  storage; compute suspends after 5 minutes idle, so the first request after
  a quiet period is slower.

## Limitations

- **No accounts:** data belongs to an anonymous browser ID stored in
  `localStorage`. Clearing site data or switching browsers/devices loses access
  to saved places and trips. The ID is a random UUID, not authentication.
- **Place data quality:** Geoapify/OpenStreetMap has no ratings or popularity,
  so results are the nearest matches and can include minor places; some places
  have no name. Some bare city names resolve to a region (e.g. "Osaka" →
  Osaka Prefecture); adding the country helps.
- **Plans are an order, not a schedule:** opening hours, prices and travel
  times are not checked; distances shown are straight-line only. "Travel to …"
  steps have no transport details.
- **Editing limits:** a trip's cities and day counts are fixed after creation;
  regenerating a day replaces all its stops and notes (no undo); two tabs
  editing the same trip use last-write-wins.
- **Destination photos** depend on Wikipedia having a suitable lead image; a
  placeholder is shown otherwise.
- **No migrations:** startup only creates missing tables; schema changes would
  need a migration tool.
- **Optional AI layer** is mocked in tests and has not been run against the
  real Gemini service; it is disabled by default.
- **Free-tier limits** of Geoapify and Neon apply (see Deployment configuration).

## Data sources and attribution

Place data from [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
powered by [Geoapify](https://www.geoapify.com/). The app shows this attribution
next to search results, on trip pages and in the footer. Destination photos
are lead images from [Wikipedia](https://www.wikipedia.org/) articles, linked
to their source article.

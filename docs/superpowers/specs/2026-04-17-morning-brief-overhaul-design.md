# Morning Brief Overhaul + LLM Action Plan — Design Spec

**Date:** 2026-04-17  
**Status:** Approved

---

## Overview

A complete overhaul of the Morning Brief feature covering: section-driven architecture with a config registry, brief archiving with history viewer, Canvas/Academics section, configurable section toggles in Settings, and a new LLM action plan capability that reads the brief to create calendar events and tasks.

---

## Architecture

### Section Registry (`morning_brief.py`)

Refactor `morning_brief.py` from a monolithic script into a section-driven architecture. An ordered `SECTIONS` dict maps each section key to a `(fetch_fn, format_fn)` pair.

```
SECTIONS = OrderedDict([
    ('weather',  (fetch_weather,  format_weather)),
    ('calendar', (fetch_calendar, format_calendar)),
    ('gmail',    (fetch_gmail,    format_gmail)),
    ('markets',  (fetch_markets,  format_markets)),
    ('canvas',   (fetch_canvas,   format_canvas)),
])
```

On startup:
1. Load `flask_app/data/brief_config.json` — default all sections to `true` if missing.
2. Filter `SECTIONS` to only enabled keys.
3. Run enabled fetch functions in parallel via `ThreadPoolExecutor`.
4. Assemble only enabled section outputs into the LLM prompt.
5. On success, write output to:
   - `flask_app/data/morning_brief.md` (current/today)
   - `flask_app/data/briefs/YYYY-MM-DD.md` (archive copy)
6. Update `brief_status.json` as normal.

### `brief_config.json` schema

```json
{
  "weather":  true,
  "calendar": true,
  "gmail":    true,
  "markets":  true,
  "canvas":   true
}
```

---

## Canvas / Academics Section

### Data

The Canvas section fetches two things:
- **Upcoming assignments** — due within the next 7 days (not yet submitted)
- **Overdue assignments** — past due date, not submitted

Uses the existing Canvas API token from `.env` (`CANVAS_API_TOKEN`, `CANVAS_BASE_URL`).

### Format

```
## Academics

**Upcoming (next 7 days):**
- [Course Name] Assignment Title — due 2026-04-20

**Overdue:**
- [Course Name] Assignment Title — was due 2026-04-15
```

If both lists are empty: `(nothing upcoming or overdue)`.

---

## Backend — New API Endpoints (`brief.py`)

### `GET /api/brief/history`

Scans `flask_app/data/briefs/`, returns the last 5 dated entries sorted newest-first.

Response:
```json
[
  {"date": "2026-04-17", "label": "Today"},
  {"date": "2026-04-16", "label": "Yesterday"},
  {"date": "2026-04-15", "label": "Apr 15"},
  ...
]
```

"Today" and "Yesterday" labels applied relative to current date; all others use `MMM D` format.

### `GET /api/brief/archive/<date>`

Serves the raw markdown of `flask_app/data/briefs/<date>.md`.  
Returns 404 with JSON error if the file does not exist.

### `GET /api/brief/config`

Returns the current `brief_config.json`. Creates the file with all sections enabled if it does not exist.

### `PATCH /api/brief/config`

Accepts a partial `{section_key: bool}` body. Merges into the existing config and writes back atomically.

```json
{"canvas": false}
```

---

## Frontend — Morning Brief Tab (`morning_brief.js`)

### History Dropdown

- A `<select>` element rendered above the brief preview area.
- Populated on tab activation via `GET /api/brief/history`.
- Default option: "Today" — loads `/api/brief/preview`.
- Selecting a past date fetches `/api/brief/archive/<date>` and renders the markdown.
- If history is empty or only today exists, the dropdown is hidden.

### No other UI changes to the brief tab.

---

## Frontend — Settings Tab (`settings.js`)

A new **"Morning Brief"** section added to the settings panel with one toggle per section:

| Label | Key |
|-------|-----|
| Weather | `weather` |
| Calendar | `calendar` |
| Gmail / Email | `gmail` |
| Markets | `markets` |
| Canvas / Academics | `canvas` |

On page load, `GET /api/brief/config` populates toggle states.  
Each toggle fires `PATCH /api/brief/config` immediately on change — no save button.

---

## LLM Action Plan Feature (`llm.py`)

### New Tool: `get_morning_brief`

```json
{
  "name": "get_morning_brief",
  "description": "Fetch today's morning brief — a summary of email, calendar, markets, weather, and academics. Call this when the user asks for an action plan or wants to know what's happening today.",
  "parameters": { "type": "object", "properties": {}, "required": [] }
}
```

Handler reads `flask_app/data/morning_brief.md` directly from disk and returns its content as a string. Returns a descriptive error string if the file does not exist.

### System Prompt Addition

Appended to the existing system message:

> "When the user asks for an 'action plan', 'plan my day', or anything similar: first call `get_morning_brief` to fetch today's brief, then systematically review it and create calendar events and tasks for any commitments, deadlines, or priorities mentioned. Always summarise what you created at the end. If you are about to create more than 5 items, list them first and ask for confirmation before proceeding."

---

## Data Flow Summary

```
morning_brief.py
  └─ loads brief_config.json
  └─ runs enabled fetch_fns in parallel
  └─ assembles prompt from enabled sections
  └─ calls oMLX → generates markdown
  └─ writes data/morning_brief.md (current)
  └─ writes data/briefs/YYYY-MM-DD.md (archive)

brief.py
  ├─ GET /api/brief/history      → lists data/briefs/*.md
  ├─ GET /api/brief/archive/<d>  → serves data/briefs/<d>.md
  ├─ GET /api/brief/config       → reads brief_config.json
  └─ PATCH /api/brief/config     → merges + writes brief_config.json

morning_brief.js
  └─ history dropdown → fetches history, renders archive on select

settings.js
  └─ brief section toggles → reads/writes /api/brief/config

llm.py
  ├─ get_morning_brief tool → reads data/morning_brief.md
  └─ system prompt → action plan playbook
```

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/morning_brief.py` | Full refactor to section registry + archive write |
| `flask_app/routes/brief.py` | Add 4 new endpoints |
| `flask_app/static/js/morning_brief.js` | Add history dropdown |
| `flask_app/static/js/settings.js` | Add brief config section |
| `flask_app/routes/llm.py` | Add `get_morning_brief` tool + system prompt update |
| `flask_app/templates/index.html` | Minor: add dropdown element if not already in markup |

---

## Out of Scope

- "Regenerate section" button (deferred)
- Brief SSE per-section progress (deferred)
- Backend tests for new endpoints (tracked separately as Feature 9)

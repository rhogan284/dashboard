# Investment Research Tab — Design Spec
**Date:** 2026-04-01  
**Status:** Approved

---

## Overview

Add an "Investment Research" tab to the dashboard: a persistent, memory-aware AI research assistant powered by Qwen3.5 via Ollama. The assistant has access to live financial data, web search, the user's portfolio database, and local files (PDFs, spreadsheets). All conversations are stored and summarised to give Qwen continuity across sessions.

---

## 1. Data Layer

Three new SQLite tables in `flask_app/data/` (same location as existing data files). Initialised and migrated by the new `research` blueprint on startup — no changes to existing tables.

### `research_sessions`
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `title` | TEXT | Auto-generated from first exchange |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp, updated on each message |
| `auto_summary` | TEXT | Qwen-generated 3–5 sentence summary, written when session ends |

### `research_messages`
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `session_id` | INTEGER | FK → research_sessions.id |
| `role` | TEXT | `user` / `assistant` / `tool` |
| `content` | TEXT | Message content |
| `created_at` | TEXT | ISO timestamp |

### `research_pinboard`
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `title` | TEXT | Short label |
| `content` | TEXT | Full note/thesis body |
| `tags` | TEXT | Comma-separated tag string |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

---

## 2. Tools

Five tools available to the research assistant.

### `search_web`
Reuses the existing Tavily integration from `routes/llm.py` verbatim. No changes needed.

### `get_stock_data`
Wraps yfinance. Parameters:
- `ticker` (string) — e.g. `"AAPL"`, `"ASX:GOLD"`
- `info_type` (enum) — `price` | `fundamentals` | `history`
- `period` (string, optional) — for history, e.g. `"1mo"`, `"3mo"`, `"1y"`

Returns structured plain text. yfinance must be added to the dashboard venv (`requirements.txt`).

### `get_financial_news`
Tavily search scoped to financial/market news. Parameters:
- `query` (string) — e.g. `"CRDO earnings outlook 2026"`
- `tickers` (list, optional) — appended to query for specificity

Runs targeted Tavily searches and returns summarised results.

### `query_portfolio`
Read-only access to `portfolio_app/portfolio.db`. Three fixed operations (no raw SQL from the model):
- `holdings` — all current positions with ticker, platform, units, avg cost, sleeve
- `trades` — last 50 trades by date
- `performance` — monthly tracker snapshots

The DB path defaults to `/Users/ryanhogan/Desktop/Coding Work/portfolio_app/portfolio.db` and is overridable via `PORTFOLIO_DB_PATH` env var.

### `read_local_file`
Parameters:
- `path` (string) — absolute path to file on disk
- `sheet` (string, optional) — for `.xlsx`, sheet name to read

Supported formats:
- `.pdf` — pdfplumber (already in portfolio venv, must add to dashboard venv)
- `.csv` — pandas
- `.xlsx` — openpyxl

Returns extracted text/data truncated to 6000 tokens. The user provides the path in their chat message.

---

## 3. Memory System

Two components injected into the system prompt on every request.

### Auto-summaries
- When a session ends (user starts new chat or navigates away), a background request to Qwen generates a 3–5 sentence summary of the session.
- Summary stored in `research_sessions.auto_summary`.
- The 5 most recent session summaries are prepended to the system prompt under `=== Past Research Summaries ===`.

### Pinboard
- All pinboard notes always included in system prompt under `=== Investment Notes & Theses ===`.
- UI shows a character count warning if total pinboard content exceeds ~2000 characters.

### System prompt structure
```
You are an investment research assistant for Ryan Hogan.
Today is {date}. Your local UTC offset is {offset}.
You have access to tools for web search, financial data, news, portfolio data, and local files.
Be concise, cite your sources, and flag uncertainty clearly.

=== Portfolio Holdings ===
{auto-injected holdings summary from query_portfolio}

=== Investment Notes & Theses ===
{all pinboard notes, newest first}

=== Past Research Summaries ===
{last 5 session auto_summaries, newest first}
```

The portfolio holdings summary is always auto-injected — Qwen knows current positions without needing to call the tool explicitly.

---

## 4. Flask Blueprint: `routes/research.py`

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/research/sessions` | List all sessions (id, title, created_at, updated_at) |
| POST | `/api/research/sessions` | Create new session, returns id |
| GET | `/api/research/sessions/<id>` | Get session metadata + all messages |
| DELETE | `/api/research/sessions/<id>` | Delete session and its messages |
| POST | `/api/research/chat` | Send message, stream NDJSON response (same format as `/api/chat`) |
| POST | `/api/research/sessions/<id>/summarise` | Trigger background summary generation |
| GET | `/api/research/sessions/<id>/title` | Get/refresh auto-generated title |
| GET | `/api/research/pinboard` | List all pinboard notes |
| POST | `/api/research/pinboard` | Add note (title, content, tags) |
| PATCH | `/api/research/pinboard/<id>` | Update note |
| DELETE | `/api/research/pinboard/<id>` | Delete note |

### Chat endpoint behaviour
`POST /api/research/chat` accepts `{ session_id, messages, think }` and streams NDJSON identical to `/api/chat`. On each request it:
1. Loads pinboard notes and last 5 session summaries from DB
2. Auto-injects current portfolio holdings into system prompt
3. Runs the Ollama tool-call loop
4. Persists each user/assistant/tool message to `research_messages`
5. Updates `research_sessions.updated_at`

---

## 5. UI Layout

### Tab structure
New "Research" tab button added to the existing tab nav bar. The tab panel is a horizontal split.

### Left sidebar (~260px, fixed)
- **"New Chat"** button at the top
- Scrollable **session list** (newest first): title + relative date. Click to load. Active session highlighted.
- Divider
- **Pinboard section**: header + "+" button to add note. List of saved notes showing title and tag pills. Click to expand/edit inline. Delete button per note.

### Main chat area (fills remaining space)
- Scrollable **message history** — same markdown-rendered bubble style as existing LLM chat
- Thinking indicator and tool status labels (reuse existing patterns from `llm.js`)
- **Input bar**:
  - Textarea (same style as main chat)
  - Think toggle pill inside textarea (same as main chat, bottom-right)
  - Small **"📎"** toggle button that reveals a file path input field
  - Send button + New Chat button (stacked, same as main chat)

### Session lifecycle
- Clicking "New Chat" creates a new session record immediately (titled "New session")
- After the first assistant response, a background call to `/api/research/sessions/<id>/title` generates a descriptive title from the exchange
- Navigating away from a session (switching to another session or tab) triggers `/api/research/sessions/<id>/summarise` in the background
- Loading a past session restores full message history and re-renders the chat

---

## 6. Dependencies to Add

Add to `flask_app/requirements.txt`:
- `yfinance` — stock data
- `pdfplumber` — PDF text extraction
- `pandas` — CSV parsing
- `openpyxl` — Excel parsing

---

## 7. New Files

| File | Purpose |
|------|---------|
| `flask_app/routes/research.py` | Blueprint: DB init, all API routes, tool handlers, chat loop |
| `flask_app/static/js/research.js` | UI: session management, chat, pinboard, file path toggle |

### Modified Files
| File | Change |
|------|--------|
| `flask_app/app.py` | Register `research_bp` |
| `flask_app/templates/index.html` | Add Research tab button and tab panel |
| `flask_app/requirements.txt` | Add yfinance, pdfplumber, pandas, openpyxl |

---

## Out of Scope (Phase 2)
- Vector embeddings / semantic search over past sessions (ChromaDB)
- Scheduled research reports (morning brief integration)
- Export chat to PDF/markdown

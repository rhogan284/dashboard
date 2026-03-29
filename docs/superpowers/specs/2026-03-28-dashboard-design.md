# Dashboard App — Design Spec
**Date:** 2026-03-28

## Context

A personal React dashboard that serves as a home base for daily work. The main page surfaces the time, a local LLM prompt interface, Google Calendar events, and a to-do/notes area. It is designed to grow: the header contains tabs that will eventually link to separate project pages built over time.

---

## Tech Stack

| Concern | Choice | Reason |
|---|---|---|
| Framework | React + Vite + TypeScript | Fast dev server, type safety, modern tooling |
| Styling | Tailwind CSS | Dark dashboard aesthetic, utility-first for speed |
| Routing | React Router v6 | Tab-based navigation between dashboard and future pages |
| LLM | Ollama REST API (`localhost:11434`) | Most common local LLM runner; no external dependency |
| Calendar | Google Calendar API v3 + OAuth 2.0 | Direct integration, no middleware |
| Persistence | localStorage | No backend required for todos/notes MVP |

---

## Layout

```
┌─────────────────────────────────────────────────────┐
│  HEADER — App name + tab navigation                  │
├──────────────┬──────────────────┬────────────────────┤
│              │                  │                    │
│   CALENDAR   │  CLOCK           │   TO-DO / NOTES    │
│              │  ──────────────  │                    │
│  (upcoming   │  LLM PROMPT BOX  │  (add tasks,       │
│   events)    │  + response      │   freeform notes)  │
│              │                  │                    │
└──────────────┴──────────────────┴────────────────────┘
```

- Dark theme throughout
- Three-column grid; center column slightly wider to give the clock/LLM more breathing room
- Columns are independently scrollable if content overflows

---

## Component Architecture

```
src/
  components/
    layout/
      Header.tsx           ← App title + tab nav links
      DashboardLayout.tsx  ← 3-column CSS grid wrapper
    widgets/
      Clock.tsx            ← Live digital clock (date + time, ticks every second)
      LLMPrompt.tsx        ← Textarea input, submit button, streaming response display
      CalendarWidget.tsx   ← OAuth trigger + scrollable event list
      TodoWidget.tsx       ← Add / check / delete todo items
      NotesWidget.tsx      ← Freeform textarea, auto-saved to localStorage
  pages/
    Home.tsx               ← Assembles DashboardLayout with all 4 widgets
  hooks/
    useClock.ts            ← setInterval tick, returns current date/time strings
    useGoogleCalendar.ts   ← OAuth flow, token storage, event fetching
    useLLM.ts              ← Fetch to Ollama /api/generate, handles streaming
    useTodos.ts            ← CRUD operations + localStorage sync
    useNotes.ts            ← Debounced localStorage save for notes textarea
  lib/
    googleCalendar.ts      ← Google Calendar API client wrapper
    llmClient.ts           ← Ollama client (configurable model, prompt formatting)
  App.tsx                  ← Router setup, top-level layout
  main.tsx                 ← Entry point
```

---

## Widget Behaviors

### Clock
- Displays current date (e.g., "Saturday, March 28") above the time
- Time shown in large type, updates every second via `setInterval`
- No external dependency

### LLM Prompt
- Textarea for user input beneath the clock
- Submit on Enter or button click
- Connects to Ollama at `localhost:11434/api/generate`
- Streams response tokens as they arrive (chunked fetch)
- Displays a spinner while waiting; shows error message if Ollama is unreachable
- Model name configurable via `.env.local` (defaults to `llama3`)

### Calendar Widget
- On mount: checks localStorage for a valid Google OAuth token
- If no token: shows "Connect Google Calendar" button that triggers OAuth popup
- If token valid: fetches events for the next 7 days from primary calendar
- Displays events grouped by day with time and title
- Refresh button to re-fetch; token auto-refreshed on expiry

### To-Do Widget
- Input field + "Add" button to create items
- Each item has a checkbox (marks complete with strikethrough) and delete button
- All items persisted to localStorage, restored on load
- Completed items displayed below active items (not removed, for reference)

### Notes Widget
- Single freeform textarea below the todo list, within the same right panel
- Auto-saves to localStorage after 500ms debounce
- No explicit save button needed

---

## Header / Navigation

- App title on the left (e.g., "Dashboard")
- Tab links on the right: "Home" is always first
- Additional tabs added as new project pages are built
- Active tab highlighted; each tab maps to a React Router route
- Home route: `/`
- Future project routes: `/projects/:name` or named paths like `/finance`, `/fitness`

---

## Routing

```
/           → Home.tsx (main dashboard)
/[tab]      → Future project pages (full-page, no 3-column layout constraint)
```

---

## Environment / Config

`.env.local` (not committed):
```
VITE_GOOGLE_CLIENT_ID=...
VITE_GOOGLE_API_KEY=...
VITE_OLLAMA_BASE_URL=http://localhost:11434
VITE_OLLAMA_MODEL=llama3
```

---

## File Structure

```
Dashboard/
  src/
  public/
  index.html
  vite.config.ts
  tailwind.config.ts
  tsconfig.json
  package.json
  .env.local
  .gitignore
  docs/
    superpowers/
      specs/
        2026-03-28-dashboard-design.md
```

---

## Verification

After implementation, verify end-to-end by:
1. `npm run dev` — app loads on localhost, dark theme visible
2. Clock ticks live with correct date and time
3. Entering a prompt and submitting — response streams in (requires Ollama running locally)
4. Clicking "Connect Google Calendar" — OAuth popup appears, events load after auth
5. Adding/completing/deleting todos — state persists after page refresh
6. Typing in Notes — content survives page refresh
7. Navigating between header tabs — routes change, pages render without errors

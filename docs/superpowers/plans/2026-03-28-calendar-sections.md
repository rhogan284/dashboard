# Calendar Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group calendar events into three labeled sections — Today, This Week, Next Week — each with per-day sub-labels (except Today), replacing the current flat per-day grouping.

**Architecture:** Extend the backend fetch window to 14 days so next week is always covered. Add a `classifyEvent()` function to the frontend that buckets each event into today/this_week/next_week using ISO week boundaries. Update `renderEvents()` to render a section header per non-empty bucket, then the existing per-day group DOM inside each.

**Tech Stack:** Python/Flask (backend one-liner), Vanilla JS (frontend)

---

## File Map

| File | Change |
|---|---|
| `flask_app/routes/calendar.py` | Extend `timeMax` from 7 to 14 days |
| `flask_app/static/js/calendar.js` | Add `classifyEvent()`, rewrite `renderEvents()` |

---

## Task 1: Extend backend fetch window

**Files:**
- Modify: `flask_app/routes/calendar.py`

- [ ] **Step 1: Change timeMax from 7 to 14 days**

In `flask_app/routes/calendar.py`, change line:
```python
end = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 7 * 86400))
```
To:
```python
end = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 14 * 86400))
```

- [ ] **Step 2: Verify Flask still starts**

```bash
cd flask_app && source .venv/bin/activate && python -c "from app import create_app; create_app()" && echo OK
```

Expected: `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add flask_app/routes/calendar.py
git commit -m "feat: extend calendar fetch window to 14 days for next-week coverage"
```

---

## Task 2: Add classifyEvent() to calendar.js

**Files:**
- Modify: `flask_app/static/js/calendar.js`

The function computes three ISO-week boundary strings (all `YYYY-MM-DD`) at call time, then compares the event's start key against them.

- ISO week: Monday = start of week, Sunday = end of week
- `endOfThisWeek`: the Sunday of the current ISO week
- `startOfNextWeek`: the Monday after that Sunday (= endOfThisWeek + 1 day)
- `endOfNextWeek`: the Sunday after startOfNextWeek (= startOfNextWeek + 6 days)

- [ ] **Step 1: Add the classifyEvent function**

Add the following function inside the IIFE in `flask_app/static/js/calendar.js`, after the `formatDayLabel` function (after line 37):

```javascript
  function getISOBoundaries() {
    const now = new Date();
    const todayStr = now.toISOString().split('T')[0];

    // Day of week: 0=Sun,1=Mon,...,6=Sat — convert to ISO (0=Mon,...,6=Sun)
    const dow = (now.getDay() + 6) % 7; // 0=Mon, 6=Sun
    const daysToSunday = 6 - dow;

    const endOfThisWeek = new Date(now);
    endOfThisWeek.setDate(now.getDate() + daysToSunday);
    const endOfThisWeekStr = endOfThisWeek.toISOString().split('T')[0];

    const startOfNextWeek = new Date(endOfThisWeek);
    startOfNextWeek.setDate(endOfThisWeek.getDate() + 1);
    const startOfNextWeekStr = startOfNextWeek.toISOString().split('T')[0];

    const endOfNextWeek = new Date(startOfNextWeek);
    endOfNextWeek.setDate(startOfNextWeek.getDate() + 6);
    const endOfNextWeekStr = endOfNextWeek.toISOString().split('T')[0];

    return { todayStr, endOfThisWeekStr, startOfNextWeekStr, endOfNextWeekStr };
  }

  function classifyEvent(event, boundaries) {
    const key = getStartKey(event);
    const { todayStr, endOfThisWeekStr, startOfNextWeekStr, endOfNextWeekStr } = boundaries;
    if (key === todayStr) return 'today';
    if (key > todayStr && key <= endOfThisWeekStr) return 'this_week';
    if (key >= startOfNextWeekStr && key <= endOfNextWeekStr) return 'next_week';
    return null;
  }
```

- [ ] **Step 2: Verify the app still loads without JS errors**

```bash
cd flask_app && source .venv/bin/activate && python app.py &
sleep 1 && curl -s http://localhost:8001/ | grep -c "calendar-events"
kill %1
```

Expected: `1` (the element is present in the HTML, no server errors).

- [ ] **Step 3: Commit**

```bash
git add flask_app/static/js/calendar.js
git commit -m "feat: add classifyEvent() for Today/This Week/Next Week bucketing"
```

---

## Task 3: Rewrite renderEvents() with section headers

**Files:**
- Modify: `flask_app/static/js/calendar.js`

Replace the existing `renderEvents` function (lines 39–71) with the version below. It:
1. Computes boundaries once via `getISOBoundaries()`
2. Classifies each event into a bucket
3. For each non-empty bucket, renders a section header then the per-day groups
4. For the Today bucket, skips the day sub-label (renders the event list directly)
5. Shows "No upcoming events" only if all three buckets are empty

- [ ] **Step 1: Replace renderEvents**

Replace the entire `renderEvents` function in `flask_app/static/js/calendar.js`:

```javascript
  function renderDayGroup(dateStr, dayEvents, showDayLabel) {
    const group = document.createElement('div');
    if (showDayLabel) {
      const label = document.createElement('p');
      label.className = 'text-gray-400 text-xs font-semibold mb-1.5';
      label.textContent = formatDayLabel(dateStr);
      group.appendChild(label);
    }
    const ul = document.createElement('ul');
    ul.className = 'space-y-1.5';
    for (const event of dayEvents) {
      const li = document.createElement('li');
      li.className = 'flex gap-2 text-sm';
      li.innerHTML = `
        <span class="text-gray-500 w-16 shrink-0 tabular-nums">${formatTime(event)}</span>
        <span class="text-white leading-snug">${escapeHtml(event.summary || '')}</span>
      `;
      ul.appendChild(li);
    }
    group.appendChild(ul);
    return group;
  }

  function renderSection(label, events) {
    const section = document.createElement('div');
    const header = document.createElement('p');
    header.className = 'text-gray-400 text-xs uppercase tracking-widest mb-2';
    header.textContent = label;
    section.appendChild(header);

    const isToday = label === 'Today';
    const grouped = new Map();
    for (const event of events) {
      const key = getStartKey(event);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(event);
    }
    const inner = document.createElement('div');
    inner.className = 'space-y-3 mb-4';
    for (const [dateStr, dayEvents] of grouped) {
      inner.appendChild(renderDayGroup(dateStr, dayEvents, !isToday));
    }
    section.appendChild(inner);
    return section;
  }

  function renderEvents(events) {
    eventsEl.innerHTML = '';
    const boundaries = getISOBoundaries();
    const buckets = { today: [], this_week: [], next_week: [] };

    for (const event of events) {
      const bucket = classifyEvent(event, boundaries);
      if (bucket) buckets[bucket].push(event);
    }

    const hasAny = buckets.today.length || buckets.this_week.length || buckets.next_week.length;
    if (!hasAny) {
      eventsEl.innerHTML = '<p class="text-gray-500 text-sm">No upcoming events</p>';
      return;
    }

    if (buckets.today.length)     eventsEl.appendChild(renderSection('Today', buckets.today));
    if (buckets.this_week.length) eventsEl.appendChild(renderSection('This Week', buckets.this_week));
    if (buckets.next_week.length) eventsEl.appendChild(renderSection('Next Week', buckets.next_week));
  }
```

- [ ] **Step 2: Verify the full app still starts**

```bash
cd flask_app && source .venv/bin/activate && python app.py &
sleep 1 && curl -s http://localhost:8001/ | grep -c "calendar-events"
kill %1
```

Expected: `1`

- [ ] **Step 3: Commit**

```bash
git add flask_app/static/js/calendar.js
git commit -m "feat: calendar Today/This Week/Next Week section headers"
```

---

## Task 4: Manual verification

- [ ] **Step 1: Launch via Electron**

```bash
cd electron && npm start
```

- [ ] **Step 2: Connect Google Calendar and verify layout**

- Click "Connect Google Calendar", complete OAuth
- Confirm events are grouped under section headers: **Today**, **This Week**, **Next Week**
- Confirm Today section shows no day sub-label
- Confirm This Week and Next Week show per-day labels (e.g. "Wednesday, Apr 2")
- Confirm empty sections are not rendered

- [ ] **Step 3: Test edge case — no events today**

If today has no events, confirm the Today section is absent entirely (not shown with an empty body).

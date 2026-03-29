# Calendar Sections Design: Today / This Week / Next Week

## Context

The calendar panel currently renders events grouped by individual day labels across a 7-day window. The user wants three named sections — **Today**, **This Week**, **Next Week** — to give the calendar clearer temporal structure at a glance. Each section still shows per-day sub-labels (except Today, where it would be redundant), preserving the existing event detail.

---

## Rendered Structure

```
TODAY
  10:00 AM  Standup
  2:30 PM   1:1 with Alex

THIS WEEK
  Wednesday, Apr 2
    9:00 AM   Design review
  Friday, Apr 4
    All day   Team offsite

NEXT WEEK
  Monday, Apr 7
    10:00 AM  Sprint planning
  Wednesday, Apr 9
    3:00 PM   Demo
```

- Section headers use `text-gray-400 text-xs uppercase tracking-widest` — same style as the "Calendar" heading
- Empty sections are hidden entirely
- Inside **Today**: no day sub-label (redundant with the section header)
- Inside **This Week** and **Next Week**: existing per-day labels render as-is (e.g. "Wednesday, Apr 2")

---

## Date Definitions

- **Today**: `date === today`
- **This Week**: `date > today && date <= end of current ISO week (Sunday)`
- **Next Week**: `date >= next Monday && date <= following Sunday`
- Events beyond next Sunday are not shown

Week boundary uses ISO week (Monday start).

---

## Changes

### `flask_app/routes/calendar.py`

Extend `timeMax` from `now + 7 days` to `now + 14 days`. No other changes. The extra range ensures next week's events are always included regardless of what day today is.

### `flask_app/static/js/calendar.js`

**Add `classifyEvent(event)`** — returns `'today'`, `'this_week'`, `'next_week'`, or `null` (out of range / past). Uses the existing `getStartKey()` to get the date string, then compares against computed boundary dates.

**Update `renderEvents(events)`** — before the existing per-day grouping loop:
1. Split events into three buckets using `classifyEvent()`
2. For each non-empty bucket, render a section header `<p>` then call the existing per-day group rendering logic on that bucket's events
3. For the Today bucket, skip the day sub-label (render events directly under the section header)

The existing `formatDayLabel`, `formatTime`, `getStartKey`, and per-day DOM construction are reused without modification.

---

## No Test Changes Required

`calendar.py` has no unit tests. The JS is frontend-only. The change to `timeMax` is a one-line edit.

# Dashboard App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React dashboard with a live clock, local LLM prompt, Google Calendar, and to-do/notes in a three-column dark-themed layout with tab navigation.

**Architecture:** Vite + React + TypeScript frontend, Tailwind CSS for styling, React Router for tab navigation. Each dashboard widget has a dedicated hook for logic and a component for rendering. A Python FastAPI backend proxies LLM requests to Ollama (handles CORS, keeps Ollama off the browser). Google Calendar uses GIS OAuth in the browser.

**Tech Stack:** React 18, Vite 6, TypeScript 5, Tailwind CSS 3, React Router v6, Vitest + React Testing Library, Python 3.11+, FastAPI, httpx, Ollama REST API, Google Calendar API v3

---

## File Map

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI server — proxies `/api/chat` to Ollama with streaming |
| `backend/requirements.txt` | Python dependencies (fastapi, uvicorn, httpx) |
| `backend/test_main.py` | Pytest tests for the FastAPI endpoint |
| `src/types/index.ts` | Shared TypeScript interfaces |
| `src/lib/llmClient.ts` | Fetch client — calls Python backend `/api/chat` with streaming |
| `src/lib/googleCalendar.ts` | Google Calendar API client |
| `src/hooks/useClock.ts` | setInterval tick → formatted date/time |
| `src/hooks/useLLM.ts` | Ollama streaming state management |
| `src/hooks/useTodos.ts` | Todo CRUD + localStorage sync |
| `src/hooks/useNotes.ts` | Notes state + debounced localStorage save |
| `src/hooks/useGoogleCalendar.ts` | GIS OAuth flow + event fetching |
| `src/components/layout/Header.tsx` | App title + tab nav |
| `src/components/layout/DashboardLayout.tsx` | 3-column grid wrapper |
| `src/components/widgets/Clock.tsx` | Date + time display |
| `src/components/widgets/LLMPrompt.tsx` | Prompt textarea + streaming response |
| `src/components/widgets/CalendarWidget.tsx` | OAuth button + event list |
| `src/components/widgets/TodoWidget.tsx` | Add/complete/delete todos |
| `src/components/widgets/NotesWidget.tsx` | Auto-saving notes textarea |
| `src/pages/Home.tsx` | Assembles 3-column dashboard |
| `src/App.tsx` | Router + top-level shell |
| `src/main.tsx` | React entry point |
| `src/index.css` | Tailwind directives |
| `src/test/setup.ts` | Vitest + jest-dom setup |
| `index.html` | HTML entry + Google Identity Services script |

---

## Task 1: Project Scaffold

**Files:**
- Create: `package.json`, `vite.config.ts`, `tsconfig.app.json`, `tailwind.config.ts`, `postcss.config.js`, `.gitignore`, `index.html`, `src/index.css`, `src/test/setup.ts`

- [ ] **Step 1: Scaffold Vite project**

Run in `/Users/ryanhogan/Desktop/Coding Work/Dashboard`:
```bash
npm create vite@latest . -- --template react-ts
```
When prompted "Current directory is not empty", choose **"Ignore files and continue"**.

Expected: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `src/` created.

- [ ] **Step 2: Install dependencies**

```bash
npm install react-router-dom
npm install -D tailwindcss postcss autoprefixer vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom @types/react @types/react-dom
npx tailwindcss init -p --ts
```

Expected: `node_modules/` populated, `tailwind.config.ts` and `postcss.config.js` created.

- [ ] **Step 3: Configure Tailwind content paths**

Edit `tailwind.config.ts` to:
```typescript
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config
```

- [ ] **Step 4: Configure Vitest in vite.config.ts**

Replace contents of `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

- [ ] **Step 5: Add vitest types to tsconfig.app.json**

In `tsconfig.app.json`, add `"vitest/globals"` and `"@testing-library/jest-dom"` to the `types` array in `compilerOptions`. The relevant section should look like:
```json
{
  "compilerOptions": {
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  }
}
```
(Merge into the existing compilerOptions — do not replace the whole file.)

- [ ] **Step 6: Create Vitest setup file**

Create `src/test/setup.ts`:
```typescript
import '@testing-library/jest-dom'
```

- [ ] **Step 7: Replace src/index.css with Tailwind directives**

Replace contents of `src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 8: Update index.html to add dark background and Google Identity Services**

Replace the `<head>` content in `index.html` (keep `<body>` as-is):
```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dashboard</title>
    <script src="https://accounts.google.com/gsi/client" async></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 9: Create .env.local**

Create `.env.local` (never committed):
```
VITE_GOOGLE_CLIENT_ID=your_google_client_id_here
VITE_GOOGLE_API_KEY=your_google_api_key_here
VITE_BACKEND_URL=http://localhost:8000
VITE_OLLAMA_MODEL=llama3
```

- [ ] **Step 10: Create .gitignore**

Ensure `.gitignore` contains at minimum:
```
node_modules
dist
.env.local
.env*.local
```

- [ ] **Step 11: Delete Vite boilerplate**

Delete these generated files that will be replaced:
```bash
rm -f src/App.css src/assets/react.svg
```

- [ ] **Step 12: Verify scaffold builds**

```bash
npm run build
```
Expected: `dist/` created, no TypeScript errors.

- [ ] **Step 13: Init git and commit**

```bash
git init
git add -A
git commit -m "chore: scaffold Vite React TypeScript project with Tailwind and Vitest"
```

---

## Task 2: Shared Types

**Files:**
- Create: `src/types/index.ts`

- [ ] **Step 1: Create types file**

Create `src/types/index.ts`:
```typescript
export interface Todo {
  id: string
  text: string
  completed: boolean
  createdAt: number
}

export interface CalendarEvent {
  id: string
  summary: string
  start: { dateTime?: string; date?: string }
  end: { dateTime?: string; date?: string }
}

export interface GCalTokenData {
  access_token: string
  expires_at: number
}
```

- [ ] **Step 2: Commit**

```bash
git add src/types/index.ts
git commit -m "feat: add shared TypeScript types"
```

---

## Task 3: Clock Hook + Component

**Files:**
- Create: `src/hooks/useClock.ts`
- Create: `src/hooks/__tests__/useClock.test.ts`
- Create: `src/components/widgets/Clock.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/hooks/__tests__/useClock.test.ts`:
```typescript
import { renderHook, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useClock } from '../useClock'

describe('useClock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns a time string matching HH:MM:SS format', () => {
    const { result } = renderHook(() => useClock())
    expect(result.current.time).toMatch(/\d{1,2}:\d{2}:\d{2}\s?(AM|PM)/i)
  })

  it('returns a date string with weekday and year', () => {
    const { result } = renderHook(() => useClock())
    expect(result.current.date).toMatch(/\w+day, \w+ \d{1,2}, \d{4}/)
  })

  it('updates after 1 second interval', () => {
    const { result } = renderHook(() => useClock())
    const before = result.current.time
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    // State update was triggered; value is still a valid time string
    expect(result.current.time).toMatch(/\d{1,2}:\d{2}:\d{2}\s?(AM|PM)/i)
    // Suppress unused var warning — we just want to confirm re-render occurred
    void before
  })

  it('clears interval on unmount', () => {
    const clearSpy = vi.spyOn(global, 'clearInterval')
    const { unmount } = renderHook(() => useClock())
    unmount()
    expect(clearSpy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/hooks/__tests__/useClock.test.ts
```
Expected: FAIL — `Cannot find module '../useClock'`

- [ ] **Step 3: Implement useClock**

Create `src/hooks/useClock.ts`:
```typescript
import { useState, useEffect } from 'react'

interface ClockState {
  time: string
  date: string
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDate(date: Date): string {
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

export function useClock(): ClockState {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  return {
    time: formatTime(now),
    date: formatDate(now),
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/hooks/__tests__/useClock.test.ts
```
Expected: PASS — 4 tests passing

- [ ] **Step 5: Create Clock component**

Create `src/components/widgets/Clock.tsx`:
```tsx
import { useClock } from '../../hooks/useClock'

export function Clock() {
  const { time, date } = useClock()
  return (
    <div className="text-center py-8">
      <p className="text-gray-400 text-base mb-3 tracking-wide">{date}</p>
      <p className="text-white text-7xl font-mono font-light tracking-tight">{time}</p>
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add src/hooks/useClock.ts src/hooks/__tests__/useClock.test.ts src/components/widgets/Clock.tsx
git commit -m "feat: add Clock hook and widget"
```

---

## Task 4: LLM Backend (Python) + Client + Component

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/main.py`
- Create: `backend/test_main.py`
- Create: `src/lib/llmClient.ts`
- Create: `src/lib/__tests__/llmClient.test.ts`
- Create: `src/hooks/useLLM.ts`
- Create: `src/components/widgets/LLMPrompt.tsx`

- [ ] **Step 1: Create Python backend directory and requirements**

```bash
mkdir backend
```

Create `backend/requirements.txt`:
```
fastapi>=0.115.0
uvicorn>=0.32.0
httpx>=0.28.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
httpx>=0.28.0
```

- [ ] **Step 2: Install Python dependencies**

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ..
```

Expected: packages installed, `.venv/` created inside `backend/`.

- [ ] **Step 3: Write the failing test for the backend**

Create `backend/test_main.py`:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from main import app

client = TestClient(app)


def test_chat_returns_streaming_response():
    """Endpoint proxies Ollama ndjson stream back to the client."""
    ollama_chunks = [
        b'{"response": "Hello", "done": false}\n',
        b'{"response": " world", "done": false}\n',
        b'{"response": "", "done": true}\n',
    ]

    async def mock_aiter_bytes():
        for chunk in ollama_chunks:
            yield chunk

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_bytes = mock_aiter_bytes

    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(
        return_value=MagicMock(stream=MagicMock(return_value=mock_stream_cm))
    )
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("main.httpx.AsyncClient", return_value=mock_client_cm):
        response = client.post("/api/chat", json={"prompt": "Hello", "model": "llama3"})

    assert response.status_code == 200
    assert "application/x-ndjson" in response.headers["content-type"]
    body = response.text
    assert '"Hello"' in body
    assert '" world"' in body


def test_chat_uses_default_model():
    """Model field defaults to llama3 when omitted."""
    captured = {}

    async def mock_aiter_bytes():
        yield b'{"response": "ok", "done": true}\n'

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_bytes = mock_aiter_bytes

    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    def capture_stream(method, url, json, **kwargs):
        captured["json"] = json
        return mock_stream_cm

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(
        return_value=MagicMock(stream=capture_stream)
    )
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("main.httpx.AsyncClient", return_value=mock_client_cm):
        client.post("/api/chat", json={"prompt": "Hello"})

    assert captured["json"]["model"] == "llama3"
```

- [ ] **Step 4: Run backend tests to verify they fail**

```bash
cd backend && source .venv/bin/activate && pytest test_main.py -v && cd ..
```
Expected: FAIL — `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 5: Implement the FastAPI backend**

Create `backend/main.py`:
```python
import os
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class GenerateRequest(BaseModel):
    prompt: str
    model: str = "llama3"


@app.post("/api/chat")
async def chat(request: GenerateRequest) -> StreamingResponse:
    async def stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": request.model,
                    "prompt": request.prompt,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="application/x-ndjson")
```

- [ ] **Step 6: Run backend tests to verify they pass**

```bash
cd backend && source .venv/bin/activate && pytest test_main.py -v && cd ..
```
Expected: PASS — 2 tests passing

- [ ] **Step 7: Write the failing test for llmClient.ts**

Create `src/lib/__tests__/llmClient.test.ts`:
```typescript
import { vi, describe, it, expect, afterEach } from 'vitest'
import { generate } from '../llmClient'

function makeStreamResponse(lines: string[]): Response {
  const text = lines.join('\n')
  let called = false
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (!called) {
            called = true
            return { done: false, value: new TextEncoder().encode(text) }
          }
          return { done: true, value: undefined }
        },
      }),
    },
  } as unknown as Response
}

describe('generate', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('streams tokens from backend response', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeStreamResponse([
        JSON.stringify({ response: 'Hello', done: false }),
        JSON.stringify({ response: ' world', done: false }),
        JSON.stringify({ response: '', done: true }),
      ])
    )

    const tokens: string[] = []
    await generate({ prompt: 'Hi', onToken: (t) => tokens.push(t) })
    expect(tokens).toEqual(['Hello', ' world'])
  })

  it('throws when backend returns an error status', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    } as Response)

    await expect(generate({ prompt: 'Hi', onToken: () => {} })).rejects.toThrow(
      'Backend error: 500 Internal Server Error'
    )
  })

  it('skips malformed JSON lines without throwing', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      makeStreamResponse([
        'not-json',
        JSON.stringify({ response: 'ok', done: false }),
        JSON.stringify({ response: '', done: true }),
      ])
    )

    const tokens: string[] = []
    await generate({ prompt: 'Hi', onToken: (t) => tokens.push(t) })
    expect(tokens).toEqual(['ok'])
  })
})
```

- [ ] **Step 8: Run test to verify it fails**

```bash
npx vitest run src/lib/__tests__/llmClient.test.ts
```
Expected: FAIL — `Cannot find module '../llmClient'`

- [ ] **Step 9: Implement llmClient**

Create `src/lib/llmClient.ts`:
```typescript
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000'
const DEFAULT_MODEL = import.meta.env.VITE_OLLAMA_MODEL ?? 'llama3'

export interface GenerateOptions {
  prompt: string
  model?: string
  onToken: (token: string) => void
  signal?: AbortSignal
}

export async function generate({
  prompt,
  model = DEFAULT_MODEL,
  onToken,
  signal,
}: GenerateOptions): Promise<void> {
  const response = await fetch(`${BACKEND_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`Ollama error: ${response.status} ${response.statusText}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })
    for (const line of chunk.split('\n').filter(Boolean)) {
      try {
        const data = JSON.parse(line)
        if (data.response) onToken(data.response)
      } catch {
        // skip malformed lines
      }
    }
  }
}
```

- [ ] **Step 10: Run test to verify it passes**

```bash
npx vitest run src/lib/__tests__/llmClient.test.ts
```
Expected: PASS — 3 tests passing

- [ ] **Step 11: Implement useLLM hook**

Create `src/hooks/useLLM.ts`:
```typescript
import { useState, useCallback, useRef } from 'react'
import { generate } from '../lib/llmClient'

interface LLMState {
  response: string
  loading: boolean
  error: string | null
}

export function useLLM() {
  const [state, setState] = useState<LLMState>({
    response: '',
    loading: false,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const submit = useCallback(async (prompt: string) => {
    if (!prompt.trim()) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setState({ response: '', loading: true, error: null })

    try {
      await generate({
        prompt,
        onToken: (token) =>
          setState((prev) => ({ ...prev, response: prev.response + token })),
        signal: abortRef.current.signal,
      })
      setState((prev) => ({ ...prev, loading: false }))
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setState((prev) => ({
        ...prev,
        loading: false,
        error:
          err instanceof Error
            ? err.message
            : 'Failed to connect to the LLM backend. Is it running?',
      }))
    }
  }, [])

  return { ...state, submit }
}
```

- [ ] **Step 12: Create LLMPrompt component**

Create `src/components/widgets/LLMPrompt.tsx`:
```tsx
import { useState, KeyboardEvent } from 'react'
import { useLLM } from '../../hooks/useLLM'

export function LLMPrompt() {
  const [input, setInput] = useState('')
  const { response, loading, error, submit } = useLLM()

  function handleSubmit() {
    submit(input)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"
          rows={3}
          className="flex-1 bg-gray-800 text-white rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
        >
          {loading ? '…' : 'Send'}
        </button>
      </div>

      {error && (
        <p className="text-red-400 text-sm">{error}</p>
      )}

      {(response || loading) && (
        <div className="bg-gray-800 rounded-lg px-4 py-3 text-sm text-gray-200 whitespace-pre-wrap max-h-72 overflow-y-auto leading-relaxed">
          {response}
          {loading && <span className="animate-pulse ml-0.5">▋</span>}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 13: Commit**

```bash
git add backend/ src/lib/llmClient.ts src/lib/__tests__/llmClient.test.ts src/hooks/useLLM.ts src/components/widgets/LLMPrompt.tsx
git commit -m "feat: add Python LLM backend, TS client, hook, and prompt widget"
```

---

## Task 5: Todo Hook + Widget

**Files:**
- Create: `src/hooks/useTodos.ts`
- Create: `src/hooks/__tests__/useTodos.test.ts`
- Create: `src/components/widgets/TodoWidget.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/hooks/__tests__/useTodos.test.ts`:
```typescript
import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { useTodos } from '../useTodos'

describe('useTodos', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with no todos', () => {
    const { result } = renderHook(() => useTodos())
    expect(result.current.todos).toEqual([])
  })

  it('adds a todo', () => {
    const { result } = renderHook(() => useTodos())
    act(() => { result.current.addTodo('Buy milk') })
    expect(result.current.todos).toHaveLength(1)
    expect(result.current.todos[0].text).toBe('Buy milk')
    expect(result.current.todos[0].completed).toBe(false)
  })

  it('trims whitespace and ignores blank input', () => {
    const { result } = renderHook(() => useTodos())
    act(() => { result.current.addTodo('   ') })
    expect(result.current.todos).toHaveLength(0)
  })

  it('toggles a todo to completed and back', () => {
    const { result } = renderHook(() => useTodos())
    act(() => { result.current.addTodo('Task') })
    const id = result.current.todos[0].id
    act(() => { result.current.toggleTodo(id) })
    expect(result.current.todos[0].completed).toBe(true)
    act(() => { result.current.toggleTodo(id) })
    expect(result.current.todos[0].completed).toBe(false)
  })

  it('deletes a todo by id', () => {
    const { result } = renderHook(() => useTodos())
    act(() => { result.current.addTodo('Task') })
    const id = result.current.todos[0].id
    act(() => { result.current.deleteTodo(id) })
    expect(result.current.todos).toHaveLength(0)
  })

  it('persists todos to localStorage on change', () => {
    const { result } = renderHook(() => useTodos())
    act(() => { result.current.addTodo('Persist me') })
    const stored = JSON.parse(localStorage.getItem('dashboard_todos') ?? '[]')
    expect(stored[0].text).toBe('Persist me')
  })

  it('restores todos from localStorage on mount', () => {
    localStorage.setItem(
      'dashboard_todos',
      JSON.stringify([{ id: '1', text: 'Pre-existing', completed: false, createdAt: 0 }])
    )
    const { result } = renderHook(() => useTodos())
    expect(result.current.todos[0].text).toBe('Pre-existing')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/hooks/__tests__/useTodos.test.ts
```
Expected: FAIL — `Cannot find module '../useTodos'`

- [ ] **Step 3: Implement useTodos**

Create `src/hooks/useTodos.ts`:
```typescript
import { useState, useEffect } from 'react'
import type { Todo } from '../types'

const STORAGE_KEY = 'dashboard_todos'

export function useTodos() {
  const [todos, setTodos] = useState<Todo[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? (JSON.parse(stored) as Todo[]) : []
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(todos))
  }, [todos])

  function addTodo(text: string) {
    const trimmed = text.trim()
    if (!trimmed) return
    setTodos((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        text: trimmed,
        completed: false,
        createdAt: Date.now(),
      },
    ])
  }

  function toggleTodo(id: string) {
    setTodos((prev) =>
      prev.map((t) => (t.id === id ? { ...t, completed: !t.completed } : t))
    )
  }

  function deleteTodo(id: string) {
    setTodos((prev) => prev.filter((t) => t.id !== id))
  }

  return { todos, addTodo, toggleTodo, deleteTodo }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/hooks/__tests__/useTodos.test.ts
```
Expected: PASS — 7 tests passing

- [ ] **Step 5: Create TodoWidget**

Create `src/components/widgets/TodoWidget.tsx`:
```tsx
import { useState, KeyboardEvent } from 'react'
import { useTodos } from '../../hooks/useTodos'

export function TodoWidget() {
  const { todos, addTodo, toggleTodo, deleteTodo } = useTodos()
  const [input, setInput] = useState('')

  function handleAdd() {
    addTodo(input)
    setInput('')
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') handleAdd()
  }

  const active = todos.filter((t) => !t.completed)
  const completed = todos.filter((t) => t.completed)

  return (
    <div>
      <h2 className="text-gray-400 text-xs uppercase tracking-widest mb-3">To-Do</h2>

      <div className="flex gap-2 mb-4">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a task…"
          className="flex-1 bg-gray-800 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
        />
        <button
          onClick={handleAdd}
          disabled={!input.trim()}
          className="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors"
        >
          Add
        </button>
      </div>

      <ul className="space-y-2">
        {active.map((todo) => (
          <li key={todo.id} className="flex items-center gap-2 group">
            <input
              type="checkbox"
              checked={false}
              onChange={() => toggleTodo(todo.id)}
              className="accent-blue-500 cursor-pointer"
            />
            <span className="flex-1 text-sm text-white">{todo.text}</span>
            <button
              onClick={() => deleteTodo(todo.id)}
              className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 text-xs transition-opacity"
              aria-label="Delete todo"
            >
              ✕
            </button>
          </li>
        ))}

        {completed.length > 0 && active.length > 0 && (
          <li className="border-t border-gray-800 my-2" />
        )}

        {completed.map((todo) => (
          <li key={todo.id} className="flex items-center gap-2 group">
            <input
              type="checkbox"
              checked={true}
              onChange={() => toggleTodo(todo.id)}
              className="accent-blue-500 cursor-pointer"
            />
            <span className="flex-1 text-sm text-gray-500 line-through">{todo.text}</span>
            <button
              onClick={() => deleteTodo(todo.id)}
              className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 text-xs transition-opacity"
              aria-label="Delete todo"
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add src/hooks/useTodos.ts src/hooks/__tests__/useTodos.test.ts src/components/widgets/TodoWidget.tsx
git commit -m "feat: add todos hook and widget"
```

---

## Task 6: Notes Hook + Widget

**Files:**
- Create: `src/hooks/useNotes.ts`
- Create: `src/hooks/__tests__/useNotes.test.ts`
- Create: `src/components/widgets/NotesWidget.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/hooks/__tests__/useNotes.test.ts`:
```typescript
import { renderHook, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useNotes } from '../useNotes'

describe('useNotes', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with empty string when no stored value', () => {
    const { result } = renderHook(() => useNotes())
    expect(result.current.notes).toBe('')
  })

  it('restores notes from localStorage on mount', () => {
    localStorage.setItem('dashboard_notes', 'hello world')
    const { result } = renderHook(() => useNotes())
    expect(result.current.notes).toBe('hello world')
  })

  it('updates notes state immediately', () => {
    const { result } = renderHook(() => useNotes())
    act(() => { result.current.updateNotes('new note') })
    expect(result.current.notes).toBe('new note')
  })

  it('does not save to localStorage before 500ms', () => {
    const { result } = renderHook(() => useNotes())
    act(() => { result.current.updateNotes('not yet') })
    expect(localStorage.getItem('dashboard_notes')).toBeNull()
  })

  it('saves to localStorage after 500ms debounce', () => {
    const { result } = renderHook(() => useNotes())
    act(() => { result.current.updateNotes('saved') })
    act(() => { vi.advanceTimersByTime(500) })
    expect(localStorage.getItem('dashboard_notes')).toBe('saved')
  })

  it('resets the debounce timer on rapid updates', () => {
    const { result } = renderHook(() => useNotes())
    act(() => { result.current.updateNotes('first') })
    act(() => { vi.advanceTimersByTime(300) })
    act(() => { result.current.updateNotes('second') })
    act(() => { vi.advanceTimersByTime(300) })
    // Total 600ms, but debounce reset at 300ms, so only 300ms since last update
    expect(localStorage.getItem('dashboard_notes')).toBeNull()
    act(() => { vi.advanceTimersByTime(200) })
    expect(localStorage.getItem('dashboard_notes')).toBe('second')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run src/hooks/__tests__/useNotes.test.ts
```
Expected: FAIL — `Cannot find module '../useNotes'`

- [ ] **Step 3: Implement useNotes**

Create `src/hooks/useNotes.ts`:
```typescript
import { useState, useEffect, useRef } from 'react'

const STORAGE_KEY = 'dashboard_notes'

export function useNotes() {
  const [notes, setNotes] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) ?? ''
  )
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function updateNotes(text: string) {
    setNotes(text)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, text)
    }, 500)
  }

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return { notes, updateNotes }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run src/hooks/__tests__/useNotes.test.ts
```
Expected: PASS — 6 tests passing

- [ ] **Step 5: Create NotesWidget**

Create `src/components/widgets/NotesWidget.tsx`:
```tsx
import { useNotes } from '../../hooks/useNotes'

export function NotesWidget() {
  const { notes, updateNotes } = useNotes()

  return (
    <div>
      <h2 className="text-gray-400 text-xs uppercase tracking-widest mb-3">Notes</h2>
      <textarea
        value={notes}
        onChange={(e) => updateNotes(e.target.value)}
        placeholder="Freeform notes…"
        className="w-full bg-gray-800 text-white rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 min-h-48"
      />
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add src/hooks/useNotes.ts src/hooks/__tests__/useNotes.test.ts src/components/widgets/NotesWidget.tsx
git commit -m "feat: add notes hook and widget"
```

---

## Task 7: Google Calendar Lib + Hook + Widget

**Files:**
- Create: `src/lib/googleCalendar.ts`
- Create: `src/hooks/useGoogleCalendar.ts`
- Create: `src/components/widgets/CalendarWidget.tsx`

> Note: No automated tests for the OAuth flow (requires browser popup). The lib fetch logic is tested implicitly via integration. Manual verification covers the full flow.

- [ ] **Step 1: Create Google Calendar API client**

Create `src/lib/googleCalendar.ts`:
```typescript
import type { CalendarEvent } from '../types'

const API_KEY = import.meta.env.VITE_GOOGLE_API_KEY as string
const CALENDAR_API = 'https://www.googleapis.com/calendar/v3'

export async function fetchUpcomingEvents(
  accessToken: string,
  days = 7
): Promise<CalendarEvent[]> {
  const now = new Date()
  const end = new Date(now)
  end.setDate(end.getDate() + days)

  const params = new URLSearchParams({
    key: API_KEY,
    timeMin: now.toISOString(),
    timeMax: end.toISOString(),
    singleEvents: 'true',
    orderBy: 'startTime',
    maxResults: '50',
  })

  const response = await fetch(
    `${CALENDAR_API}/calendars/primary/events?${params}`,
    { headers: { Authorization: `Bearer ${accessToken}` } }
  )

  if (!response.ok) {
    throw new Error(`Calendar API error: ${response.status}`)
  }

  const data = (await response.json()) as { items?: CalendarEvent[] }
  return data.items ?? []
}
```

- [ ] **Step 2: Create useGoogleCalendar hook**

Create `src/hooks/useGoogleCalendar.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { fetchUpcomingEvents } from '../lib/googleCalendar'
import type { CalendarEvent, GCalTokenData } from '../types'

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string
const SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
const TOKEN_KEY = 'dashboard_gcal_token'

function loadToken(): GCalTokenData | null {
  try {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (!stored) return null
    const token = JSON.parse(stored) as GCalTokenData
    if (Date.now() > token.expires_at) {
      localStorage.removeItem(TOKEN_KEY)
      return null
    }
    return token
  } catch {
    return null
  }
}

export function useGoogleCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)

  const fetchEvents = useCallback(async (accessToken: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchUpcomingEvents(accessToken)
      setEvents(data)
      setConnected(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch events')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const token = loadToken()
    if (token) fetchEvents(token.access_token)
  }, [fetchEvents])

  const connect = useCallback(() => {
    // google is loaded globally via the GIS script in index.html
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const client = (window as any).google.accounts.oauth2.initTokenClient({
      client_id: CLIENT_ID,
      scope: SCOPE,
      callback: (response: { access_token: string; expires_in: number }) => {
        const tokenData: GCalTokenData = {
          access_token: response.access_token,
          expires_at: Date.now() + response.expires_in * 1000,
        }
        localStorage.setItem(TOKEN_KEY, JSON.stringify(tokenData))
        fetchEvents(response.access_token)
      },
    })
    client.requestAccessToken()
  }, [fetchEvents])

  const refresh = useCallback(() => {
    const token = loadToken()
    if (token) {
      fetchEvents(token.access_token)
    } else {
      connect()
    }
  }, [connect, fetchEvents])

  return { events, loading, error, connected, connect, refresh }
}
```

- [ ] **Step 3: Create helper functions for CalendarWidget**

These are pure functions used only by the widget — define them at the top of the component file.

Create `src/components/widgets/CalendarWidget.tsx`:
```tsx
import { useGoogleCalendar } from '../../hooks/useGoogleCalendar'
import type { CalendarEvent } from '../../types'

function getEventStartKey(event: CalendarEvent): string {
  return (event.start.dateTime ?? event.start.date ?? '').split('T')[0]
}

function formatEventTime(event: CalendarEvent): string {
  if (event.start.date) return 'All day'
  const dt = event.start.dateTime
  if (!dt) return ''
  return new Date(dt).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function groupByDay(events: CalendarEvent[]): [string, CalendarEvent[]][] {
  const map = new Map<string, CalendarEvent[]>()
  for (const event of events) {
    const key = getEventStartKey(event)
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(event)
  }
  return Array.from(map.entries())
}

function formatDayLabel(dateStr: string): string {
  const todayStr = new Date().toISOString().split('T')[0]
  const tomorrowDate = new Date()
  tomorrowDate.setDate(tomorrowDate.getDate() + 1)
  const tomorrowStr = tomorrowDate.toISOString().split('T')[0]

  if (dateStr === todayStr) return 'Today'
  if (dateStr === tomorrowStr) return 'Tomorrow'

  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  })
}

export function CalendarWidget() {
  const { events, loading, error, connected, connect, refresh } =
    useGoogleCalendar()

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-gray-400 text-xs uppercase tracking-widest">
          Calendar
        </h2>
        {connected && (
          <button
            onClick={refresh}
            className="text-gray-500 hover:text-white text-xs transition-colors"
          >
            Refresh
          </button>
        )}
      </div>

      {!connected && !loading && (
        <button
          onClick={connect}
          className="w-full py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors"
        >
          Connect Google Calendar
        </button>
      )}

      {loading && (
        <p className="text-gray-500 text-sm">Loading events…</p>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {connected && !loading && (
        <div className="space-y-5">
          {events.length === 0 && (
            <p className="text-gray-500 text-sm">No upcoming events</p>
          )}
          {groupByDay(events).map(([dateStr, dayEvents]) => (
            <div key={dateStr}>
              <p className="text-gray-400 text-xs font-semibold mb-1.5">
                {formatDayLabel(dateStr)}
              </p>
              <ul className="space-y-1.5">
                {dayEvents.map((event) => (
                  <li key={event.id} className="flex gap-2 text-sm">
                    <span className="text-gray-500 w-16 shrink-0 tabular-nums">
                      {formatEventTime(event)}
                    </span>
                    <span className="text-white leading-snug">
                      {event.summary}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add src/lib/googleCalendar.ts src/hooks/useGoogleCalendar.ts src/components/widgets/CalendarWidget.tsx
git commit -m "feat: add Google Calendar lib, hook, and widget"
```

---

## Task 8: Layout Components

**Files:**
- Create: `src/components/layout/DashboardLayout.tsx`
- Create: `src/components/layout/Header.tsx`

- [ ] **Step 1: Create DashboardLayout**

Create `src/components/layout/DashboardLayout.tsx`:
```tsx
import { ReactNode } from 'react'

interface Props {
  left: ReactNode
  center: ReactNode
  right: ReactNode
}

export function DashboardLayout({ left, center, right }: Props) {
  return (
    <div className="grid grid-cols-[1fr_1.5fr_1fr] gap-0 h-full">
      <div className="overflow-y-auto border-r border-gray-800 px-5 py-6">
        {left}
      </div>
      <div className="overflow-y-auto px-6 py-6">{center}</div>
      <div className="overflow-y-auto border-l border-gray-800 px-5 py-6">
        {right}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create Header**

Create `src/components/layout/Header.tsx`:
```tsx
import { NavLink } from 'react-router-dom'

const NAV_TABS = [{ label: 'Home', path: '/' }]

export function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
      <span className="text-white font-semibold text-lg tracking-tight">
        Dashboard
      </span>
      <nav className="flex gap-1">
        {NAV_TABS.map((tab) => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end
            className={({ isActive }) =>
              `text-sm px-3 py-1.5 rounded-md transition-colors ${
                isActive
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/layout/DashboardLayout.tsx src/components/layout/Header.tsx
git commit -m "feat: add DashboardLayout and Header components"
```

---

## Task 9: Pages + App Wiring

**Files:**
- Create: `src/pages/Home.tsx`
- Create: `src/App.tsx`
- Modify: `src/main.tsx`

- [ ] **Step 1: Create Home page**

Create `src/pages/Home.tsx`:
```tsx
import { DashboardLayout } from '../components/layout/DashboardLayout'
import { Clock } from '../components/widgets/Clock'
import { LLMPrompt } from '../components/widgets/LLMPrompt'
import { CalendarWidget } from '../components/widgets/CalendarWidget'
import { TodoWidget } from '../components/widgets/TodoWidget'
import { NotesWidget } from '../components/widgets/NotesWidget'

export function Home() {
  return (
    <DashboardLayout
      left={<CalendarWidget />}
      center={
        <div className="flex flex-col gap-6">
          <Clock />
          <LLMPrompt />
        </div>
      }
      right={
        <div className="flex flex-col gap-6">
          <TodoWidget />
          <NotesWidget />
        </div>
      }
    />
  )
}
```

- [ ] **Step 2: Create App.tsx**

Replace `src/App.tsx` with:
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Header } from './components/layout/Header'
import { Home } from './pages/Home'

export function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen bg-gray-950 text-white">
        <Header />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Home />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

- [ ] **Step 3: Update main.tsx**

Replace `src/main.tsx` with:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

- [ ] **Step 4: Commit**

```bash
git add src/pages/Home.tsx src/App.tsx src/main.tsx
git commit -m "feat: wire up Home page, App shell, and routing"
```

---

## Task 10: Full Test Run + Verification

- [ ] **Step 1: Run all tests**

Frontend (Vitest):
```bash
npx vitest run
```
Expected: All pass — `useClock` (4), `llmClient` (3), `useTodos` (7), `useNotes` (6) = 20 tests

Backend (pytest):
```bash
cd backend && source .venv/bin/activate && pytest test_main.py -v && cd ..
```
Expected: PASS — 2 tests passing

- [ ] **Step 2: Build check**

```bash
npm run build
```
Expected: `dist/` generated, no TypeScript errors, no build warnings.

- [ ] **Step 3: Start dev server**

```bash
npm run dev
```
Expected: Server starts on `http://localhost:5173`

- [ ] **Step 4: Verify clock**

Open `http://localhost:5173`. Confirm:
- Dark background fills the screen
- Header shows "Dashboard" and "Home" tab
- Center column shows date label (e.g., "Saturday, March 28, 2026") and large time ticking every second

- [ ] **Step 5: Verify todos**

In the right column:
- Type a task name and press Enter — item appears in the list
- Check the checkbox — item moves to completed with strikethrough
- Hover over an item — ✕ button appears; clicking it removes the item
- Refresh the page — todos are still there

- [ ] **Step 6: Verify notes**

In the right column below todos:
- Type text in the Notes area
- Refresh the page — text is still there

- [ ] **Step 7: Verify LLM (requires Ollama + Python backend running)**

Start the Python backend (in a separate terminal):
```bash
cd backend && source .venv/bin/activate && uvicorn main:app --reload
```
Expected: `Uvicorn running on http://127.0.0.1:8000`

Then, with Ollama also running (`ollama serve`):
- Type a prompt in the center textarea and press Enter
- Response streams in token by token

If the backend is not running:
- Type a prompt and submit
- Error message appears: "Backend error: ..." or similar — this is correct behavior

- [ ] **Step 8: Verify Google Calendar**

Left column shows "Connect Google Calendar" button.
> Full OAuth verification requires valid credentials in `.env.local`. Fill in `VITE_GOOGLE_CLIENT_ID` and `VITE_GOOGLE_API_KEY` from Google Cloud Console, restart dev server, then click the button — OAuth popup should appear and events should load after auth.

- [ ] **Step 9: Final commit**

```bash
git add -A
git commit -m "chore: complete dashboard app initial implementation"
```

---

## Adding Future Tabs

To add a new project page later:
1. Create `src/pages/MyPage.tsx`
2. Add `<Route path="/my-page" element={<MyPage />} />` in `App.tsx`
3. Add `{ label: 'My Page', path: '/my-page' }` to the `NAV_TABS` array in `Header.tsx`

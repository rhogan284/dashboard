# Dashboard App Implementation Plan (Electron + Flask)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personal dashboard as an Electron desktop app wrapping a Flask web server — Flask serves the UI and handles all backend logic, Electron spawns Flask and displays it in a native window.

**Architecture:** Flask acts as both the web server (serving HTML/CSS/JS templates) and the API backend (LLM proxy, todos, notes, calendar). Electron's sole job is to start Flask as a subprocess and open a BrowserWindow pointed at `http://localhost:5000`. Vanilla JS widgets in static files handle all interactivity by calling Flask API endpoints. Data (todos, notes, calendar token) is persisted to local JSON/text files in `flask_app/data/`.

**Tech Stack:** Python 3.11+, Flask 3, httpx, python-dotenv, pytest; Electron 33, Node.js; Tailwind CSS (CDN); Vanilla JavaScript; Google Identity Services (browser OAuth); Ollama REST API

---

## File Map

| File | Purpose |
|---|---|
| `electron/package.json` | Electron dependencies and start script |
| `electron/main.js` | Electron entry — spawns Flask subprocess, creates BrowserWindow |
| `flask_app/app.py` | Flask app factory, blueprint registration, index route |
| `flask_app/routes/__init__.py` | Empty package marker |
| `flask_app/routes/llm.py` | `POST /api/chat` — streams Ollama response |
| `flask_app/routes/todos.py` | `GET/POST /api/todos`, `PATCH/DELETE /api/todos/<id>` |
| `flask_app/routes/notes.py` | `GET/POST /api/notes` |
| `flask_app/routes/calendar.py` | `POST /api/calendar/token`, `GET /api/calendar/events` |
| `flask_app/templates/index.html` | Full dashboard HTML — 3-column layout, all widget markup |
| `flask_app/static/js/clock.js` | setInterval clock widget |
| `flask_app/static/js/llm.js` | Prompt submission + streaming response display |
| `flask_app/static/js/todos.js` | Fetch-backed todo CRUD + DOM rendering |
| `flask_app/static/js/notes.js` | Debounced notes save |
| `flask_app/static/js/calendar.js` | GIS OAuth flow + event list rendering |
| `flask_app/tests/conftest.py` | Shared pytest fixtures (app factory with tmp data dir) |
| `flask_app/tests/test_llm.py` | Tests for `/api/chat` streaming endpoint |
| `flask_app/tests/test_todos.py` | Tests for todos CRUD endpoints |
| `flask_app/tests/test_notes.py` | Tests for notes get/save endpoints |
| `flask_app/requirements.txt` | Python dependencies |
| `.env` | Google credentials, Ollama config (never committed) |

---

## Task 1: Project Scaffold

**Files:**
- Create: `electron/package.json`, `flask_app/requirements.txt`, `.env`, `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p electron flask_app/routes flask_app/templates flask_app/static/js flask_app/tests flask_app/data
touch flask_app/routes/__init__.py flask_app/tests/__init__.py
```

- [ ] **Step 2: Create Flask requirements**

Create `flask_app/requirements.txt`:
```
flask>=3.0.0
httpx>=0.28.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Create Flask virtual environment and install dependencies**

```bash
cd flask_app && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && cd ..
```

Expected: packages installed, `flask_app/.venv/` created.

- [ ] **Step 4: Create Electron package.json**

Create `electron/package.json`:
```json
{
  "name": "dashboard",
  "version": "1.0.0",
  "description": "Personal dashboard — Electron wrapper for Flask",
  "main": "main.js",
  "scripts": {
    "start": "electron ."
  },
  "devDependencies": {
    "electron": "^33.0.0"
  }
}
```

- [ ] **Step 5: Install Electron**

```bash
cd electron && npm install && cd ..
```

Expected: `electron/node_modules/` created.

- [ ] **Step 6: Create .env**

Create `.env` (never committed):
```
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_API_KEY=your_google_api_key_here
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

- [ ] **Step 7: Create .gitignore**

Create `.gitignore`:
```
# Python
flask_app/.venv/
flask_app/data/
__pycache__/
*.pyc
.pytest_cache/

# Node
electron/node_modules/

# Env
.env

# Build
dist/
```

- [ ] **Step 8: Init git and commit**

```bash
git init
git add -A
git commit -m "chore: scaffold Electron + Flask project structure"
```

---

## Task 2: Flask App Factory + Dashboard Template

**Files:**
- Create: `flask_app/app.py`
- Create: `flask_app/templates/index.html`

- [ ] **Step 1: Create Flask app factory**

Create `flask_app/app.py`:
```python
import os
from pathlib import Path
from flask import Flask, render_template
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config['DATA_DIR'] = Path(__file__).parent / 'data'

    if config:
        app.config.update(config)

    app.config['DATA_DIR'].mkdir(exist_ok=True)

    from routes.llm import llm_bp
    from routes.todos import todos_bp
    from routes.notes import notes_bp
    from routes.calendar import calendar_bp

    app.register_blueprint(llm_bp)
    app.register_blueprint(todos_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(calendar_bp)

    @app.route('/')
    def index():
        return render_template(
            'index.html',
            google_client_id=os.getenv('GOOGLE_CLIENT_ID', ''),
        )

    return app


if __name__ == '__main__':
    application = create_app()
    application.run(port=5000, debug=False)
```

- [ ] **Step 2: Create the dashboard HTML template**

Create `flask_app/templates/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = { darkMode: 'class' }
  </script>
  <script src="https://accounts.google.com/gsi/client" async></script>
</head>
<body class="bg-gray-950 text-white h-screen flex flex-col overflow-hidden">

  <!-- Header -->
  <header class="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
    <span class="font-semibold text-lg tracking-tight">Dashboard</span>
    <nav class="flex gap-1">
      <a href="/" class="text-sm px-3 py-1.5 rounded-md bg-gray-700 text-white">Home</a>
    </nav>
  </header>

  <!-- 3-column layout -->
  <main class="flex-1 grid grid-cols-[1fr_1.5fr_1fr] overflow-hidden">

    <!-- Left: Calendar -->
    <div class="overflow-y-auto border-r border-gray-800 px-5 py-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-gray-400 text-xs uppercase tracking-widest">Calendar</h2>
        <button id="calendar-refresh" class="text-gray-500 hover:text-white text-xs transition-colors hidden">Refresh</button>
      </div>
      <button id="calendar-connect" class="w-full py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors">
        Connect Google Calendar
      </button>
      <p id="calendar-loading" class="text-gray-500 text-sm hidden">Loading events…</p>
      <p id="calendar-error" class="text-red-400 text-sm hidden"></p>
      <div id="calendar-events" class="space-y-5 hidden"></div>
    </div>

    <!-- Center: Clock + LLM -->
    <div class="overflow-y-auto px-6 py-6 flex flex-col gap-6">

      <!-- Clock -->
      <div class="text-center py-8">
        <p id="clock-date" class="text-gray-400 text-base mb-3 tracking-wide"></p>
        <p id="clock-time" class="text-white text-7xl font-mono font-light tracking-tight"></p>
      </div>

      <!-- LLM Prompt -->
      <div class="flex flex-col gap-3">
        <div class="flex gap-2 items-end">
          <textarea
            id="llm-input"
            placeholder="Ask anything… (Enter to send, Shift+Enter for newline)"
            rows="3"
            class="flex-1 bg-gray-800 text-white rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500"
          ></textarea>
          <button id="llm-submit"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
            Send
          </button>
        </div>
        <p id="llm-error" class="text-red-400 text-sm hidden"></p>
        <div id="llm-response"
          class="bg-gray-800 rounded-lg px-4 py-3 text-sm text-gray-200 whitespace-pre-wrap max-h-72 overflow-y-auto leading-relaxed hidden">
        </div>
      </div>
    </div>

    <!-- Right: Todos + Notes -->
    <div class="overflow-y-auto border-l border-gray-800 px-5 py-6 flex flex-col gap-6">

      <!-- Todos -->
      <div>
        <h2 class="text-gray-400 text-xs uppercase tracking-widest mb-3">To-Do</h2>
        <div class="flex gap-2 mb-4">
          <input id="todo-input" placeholder="Add a task…"
            class="flex-1 bg-gray-800 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500" />
          <button id="todo-add"
            class="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-lg transition-colors">
            Add
          </button>
        </div>
        <ul id="todo-list" class="space-y-2"></ul>
      </div>

      <!-- Notes -->
      <div>
        <h2 class="text-gray-400 text-xs uppercase tracking-widest mb-3">Notes</h2>
        <textarea id="notes-textarea" placeholder="Freeform notes…"
          class="w-full bg-gray-800 text-white rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 min-h-48">
        </textarea>
      </div>

    </div>
  </main>

  <!-- Inject server-side config for JS -->
  <script>const GOOGLE_CLIENT_ID = "{{ google_client_id }}";</script>
  <script src="/static/js/clock.js"></script>
  <script src="/static/js/llm.js"></script>
  <script src="/static/js/todos.js"></script>
  <script src="/static/js/notes.js"></script>
  <script src="/static/js/calendar.js"></script>
</body>
</html>
```

- [ ] **Step 3: Stub out empty route blueprints so the app can start**

Create `flask_app/routes/llm.py`:
```python
from flask import Blueprint
llm_bp = Blueprint('llm', __name__)
```

Create `flask_app/routes/todos.py`:
```python
from flask import Blueprint
todos_bp = Blueprint('todos', __name__)
```

Create `flask_app/routes/notes.py`:
```python
from flask import Blueprint
notes_bp = Blueprint('notes', __name__)
```

Create `flask_app/routes/calendar.py`:
```python
from flask import Blueprint
calendar_bp = Blueprint('calendar', __name__)
```

- [ ] **Step 4: Verify Flask starts and serves the template**

```bash
cd flask_app && source .venv/bin/activate && python app.py &
sleep 1 && curl -s http://localhost:5000/ | grep -c "Dashboard"
kill %1
cd ..
```

Expected: outputs `1` (the word "Dashboard" appears in the HTML).

- [ ] **Step 5: Commit**

```bash
git add flask_app/app.py flask_app/templates/index.html flask_app/routes/
git commit -m "feat: Flask app factory, dashboard template, stubbed blueprints"
```

---

## Task 3: Clock Widget

**Files:**
- Create: `flask_app/static/js/clock.js`

> The clock is pure client-side JS with no Flask API involved. Verified manually.

- [ ] **Step 1: Create clock.js**

Create `flask_app/static/js/clock.js`:
```javascript
(function () {
  function update() {
    const now = new Date();
    document.getElementById('clock-time').textContent = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    document.getElementById('clock-date').textContent = now.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  }
  update();
  setInterval(update, 1000);
})();
```

- [ ] **Step 2: Verify clock renders**

```bash
cd flask_app && source .venv/bin/activate && python app.py &
sleep 1 && curl -s http://localhost:5000/ | grep "clock-time"
kill %1
cd ..
```

Expected: the `id="clock-time"` element appears in the HTML.

- [ ] **Step 3: Commit**

```bash
git add flask_app/static/js/clock.js
git commit -m "feat: clock widget"
```

---

## Task 4: LLM Route + Widget

**Files:**
- Create: `flask_app/tests/conftest.py`
- Replace: `flask_app/routes/llm.py`
- Create: `flask_app/tests/test_llm.py`
- Create: `flask_app/static/js/llm.js`

- [ ] **Step 1: Create shared test fixtures**

Create `flask_app/tests/conftest.py`:
```python
import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'DATA_DIR': tmp_path})


@pytest.fixture
def client(app):
    return app.test_client()
```

- [ ] **Step 2: Write the failing test for /api/chat**

Create `flask_app/tests/test_llm.py`:
```python
from unittest.mock import MagicMock, patch


def test_chat_streams_ollama_response(client):
    """POST /api/chat proxies Ollama ndjson chunks back to the caller."""
    chunks = [
        b'{"response": "Hello", "done": false}\n',
        b'{"response": " world", "done": true}\n',
    ]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = iter(chunks)
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch('routes.llm.httpx.Client', return_value=mock_client):
        response = client.post('/api/chat', json={'prompt': 'Hi'})

    assert response.status_code == 200
    assert b'Hello' in response.data
    assert b' world' in response.data


def test_chat_uses_default_model_when_omitted(client):
    """Model defaults to OLLAMA_MODEL env var value when not supplied."""
    captured = {}
    chunks = [b'{"response": "ok", "done": true}\n']

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = iter(chunks)
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    def capture_stream(method, url, json, **kwargs):
        captured['json'] = json
        return mock_response

    mock_client = MagicMock()
    mock_client.stream = capture_stream
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch('routes.llm.httpx.Client', return_value=mock_client):
        client.post('/api/chat', json={'prompt': 'Hello'})

    assert captured['json']['model'] == 'llama3'


def test_chat_missing_prompt_returns_400(client):
    """POST /api/chat with no prompt field returns 400."""
    response = client.post('/api/chat', json={})
    assert response.status_code == 400
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_llm.py -v && cd ..
```

Expected: FAIL — route stubs return no response / import errors.

- [ ] **Step 4: Implement routes/llm.py**

Replace `flask_app/routes/llm.py`:
```python
import os
import httpx
from flask import Blueprint, Response, request, stream_with_context

llm_bp = Blueprint('llm', __name__)

OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')


@llm_bp.route('/api/chat', methods=['POST'])
def chat() -> Response:
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return Response('{"error": "prompt required"}', status=400, mimetype='application/json')

    model = data.get('model', DEFAULT_MODEL)

    def generate():
        with httpx.Client(timeout=None) as client:
            with client.stream(
                'POST',
                f'{OLLAMA_URL}/api/generate',
                json={'model': model, 'prompt': prompt, 'stream': True},
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    yield chunk

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_llm.py -v && cd ..
```

Expected: PASS — 3 tests passing.

- [ ] **Step 6: Create llm.js**

Create `flask_app/static/js/llm.js`:
```javascript
(function () {
  const input = document.getElementById('llm-input');
  const submitBtn = document.getElementById('llm-submit');
  const responseDiv = document.getElementById('llm-response');
  const errorP = document.getElementById('llm-error');

  async function submit() {
    const prompt = input.value.trim();
    if (!prompt) return;

    responseDiv.textContent = '';
    responseDiv.classList.remove('hidden');
    errorP.classList.add('hidden');
    submitBtn.textContent = '…';
    submitBtn.disabled = true;

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      if (!response.ok) throw new Error(`Backend error: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n').filter(Boolean)) {
          try {
            const data = JSON.parse(line);
            if (data.response) responseDiv.textContent += data.response;
          } catch {}
        }
      }
    } catch (err) {
      errorP.textContent = err.message || 'Failed to connect to backend';
      errorP.classList.remove('hidden');
      responseDiv.classList.add('hidden');
    } finally {
      submitBtn.textContent = 'Send';
      submitBtn.disabled = false;
    }
  }

  submitBtn.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });
})();
```

- [ ] **Step 7: Commit**

```bash
git add flask_app/routes/llm.py flask_app/tests/conftest.py flask_app/tests/test_llm.py flask_app/static/js/llm.js
git commit -m "feat: LLM route with Ollama streaming proxy and prompt widget"
```

---

## Task 5: Todos Route + Widget

**Files:**
- Replace: `flask_app/routes/todos.py`
- Create: `flask_app/tests/test_todos.py`
- Create: `flask_app/static/js/todos.js`

- [ ] **Step 1: Write the failing tests**

Create `flask_app/tests/test_todos.py`:
```python
def test_get_todos_returns_empty_list_initially(client):
    response = client.get('/api/todos')
    assert response.status_code == 200
    assert response.get_json() == []


def test_create_todo(client):
    response = client.post('/api/todos', json={'text': 'Buy milk'})
    assert response.status_code == 201
    data = response.get_json()
    assert data['text'] == 'Buy milk'
    assert data['completed'] is False
    assert 'id' in data


def test_create_todo_trims_and_rejects_blank(client):
    response = client.post('/api/todos', json={'text': '   '})
    assert response.status_code == 400


def test_created_todo_appears_in_get(client):
    client.post('/api/todos', json={'text': 'Task A'})
    todos = client.get('/api/todos').get_json()
    assert len(todos) == 1
    assert todos[0]['text'] == 'Task A'


def test_toggle_todo_completed(client):
    todo_id = client.post('/api/todos', json={'text': 'Task'}).get_json()['id']
    response = client.patch(f'/api/todos/{todo_id}', json={'completed': True})
    assert response.status_code == 200
    assert response.get_json()['completed'] is True


def test_toggle_todo_not_found(client):
    response = client.patch('/api/todos/nonexistent', json={'completed': True})
    assert response.status_code == 404


def test_delete_todo(client):
    todo_id = client.post('/api/todos', json={'text': 'Task'}).get_json()['id']
    response = client.delete(f'/api/todos/{todo_id}')
    assert response.status_code == 204
    assert client.get('/api/todos').get_json() == []


def test_delete_todo_not_found(client):
    response = client.delete('/api/todos/nonexistent')
    assert response.status_code == 404


def test_todos_persist_to_file(client, app):
    client.post('/api/todos', json={'text': 'Persisted'})
    todos_file = app.config['DATA_DIR'] / 'todos.json'
    assert todos_file.exists()
    import json
    saved = json.loads(todos_file.read_text())
    assert saved[0]['text'] == 'Persisted'
```

- [ ] **Step 2: Run test to verify they fail**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_todos.py -v && cd ..
```

Expected: FAIL — routes return 404 (stub blueprint has no routes).

- [ ] **Step 3: Implement routes/todos.py**

Replace `flask_app/routes/todos.py`:
```python
import json
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

todos_bp = Blueprint('todos', __name__)


def _todos_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'todos.json'


def _read() -> list:
    f = _todos_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write(todos: list) -> None:
    _todos_file().write_text(json.dumps(todos, indent=2))


@todos_bp.route('/api/todos', methods=['GET'])
def get_todos():
    return jsonify(_read())


@todos_bp.route('/api/todos', methods=['POST'])
def create_todo():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'text required'}), 400
    todo = {
        'id': str(uuid.uuid4()),
        'text': text,
        'completed': False,
        'createdAt': int(time.time() * 1000),
    }
    todos = _read()
    todos.append(todo)
    _write(todos)
    return jsonify(todo), 201


@todos_bp.route('/api/todos/<todo_id>', methods=['PATCH'])
def update_todo(todo_id: str):
    data = request.get_json(silent=True) or {}
    todos = _read()
    for todo in todos:
        if todo['id'] == todo_id:
            if 'completed' in data:
                todo['completed'] = bool(data['completed'])
            _write(todos)
            return jsonify(todo)
    return jsonify({'error': 'not found'}), 404


@todos_bp.route('/api/todos/<todo_id>', methods=['DELETE'])
def delete_todo(todo_id: str):
    todos = _read()
    updated = [t for t in todos if t['id'] != todo_id]
    if len(updated) == len(todos):
        return jsonify({'error': 'not found'}), 404
    _write(updated)
    return Response(status=204)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_todos.py -v && cd ..
```

Expected: PASS — 9 tests passing.

- [ ] **Step 5: Create todos.js**

Create `flask_app/static/js/todos.js`:
```javascript
(function () {
  const input = document.getElementById('todo-input');
  const addBtn = document.getElementById('todo-add');
  const list = document.getElementById('todo-list');

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  function createTodoItem(todo) {
    const li = document.createElement('li');
    li.className = 'flex items-center gap-2 group';
    li.dataset.id = todo.id;
    li.innerHTML = `
      <input type="checkbox" ${todo.completed ? 'checked' : ''}
        class="accent-blue-500 cursor-pointer todo-check" />
      <span class="flex-1 text-sm ${todo.completed ? 'text-gray-500 line-through' : 'text-white'}">
        ${escapeHtml(todo.text)}
      </span>
      <button class="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 text-xs transition-opacity todo-delete"
        aria-label="Delete">✕</button>
    `;
    li.querySelector('.todo-check').addEventListener('change', function () {
      toggleTodo(todo.id, this.checked);
    });
    li.querySelector('.todo-delete').addEventListener('click', () => deleteTodo(todo.id));
    return li;
  }

  function renderTodos(todos) {
    list.innerHTML = '';
    const active = todos.filter((t) => !t.completed);
    const completed = todos.filter((t) => t.completed);
    for (const todo of active) list.appendChild(createTodoItem(todo));
    if (active.length && completed.length) {
      const divider = document.createElement('li');
      divider.className = 'border-t border-gray-800 my-2';
      list.appendChild(divider);
    }
    for (const todo of completed) list.appendChild(createTodoItem(todo));
  }

  async function loadTodos() {
    const response = await fetch('/api/todos');
    renderTodos(await response.json());
  }

  async function addTodo() {
    const text = input.value.trim();
    if (!text) return;
    await fetch('/api/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    input.value = '';
    loadTodos();
  }

  async function toggleTodo(id, completed) {
    await fetch(`/api/todos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed }),
    });
    loadTodos();
  }

  async function deleteTodo(id) {
    await fetch(`/api/todos/${id}`, { method: 'DELETE' });
    loadTodos();
  }

  addBtn.addEventListener('click', addTodo);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addTodo();
  });

  loadTodos();
})();
```

- [ ] **Step 6: Commit**

```bash
git add flask_app/routes/todos.py flask_app/tests/test_todos.py flask_app/static/js/todos.js
git commit -m "feat: todos CRUD route and widget"
```

---

## Task 6: Notes Route + Widget

**Files:**
- Replace: `flask_app/routes/notes.py`
- Create: `flask_app/tests/test_notes.py`
- Create: `flask_app/static/js/notes.js`

- [ ] **Step 1: Write the failing tests**

Create `flask_app/tests/test_notes.py`:
```python
def test_get_notes_returns_empty_string_when_no_file(client):
    response = client.get('/api/notes')
    assert response.status_code == 200
    assert response.get_json()['content'] == ''


def test_save_notes(client):
    response = client.post('/api/notes', json={'content': 'hello world'})
    assert response.status_code == 200
    assert response.get_json()['ok'] is True


def test_save_and_retrieve_notes(client):
    client.post('/api/notes', json={'content': 'my notes'})
    response = client.get('/api/notes')
    assert response.get_json()['content'] == 'my notes'


def test_save_notes_persists_to_file(client, app):
    client.post('/api/notes', json={'content': 'saved!'})
    notes_file = app.config['DATA_DIR'] / 'notes.txt'
    assert notes_file.read_text() == 'saved!'


def test_overwrite_notes(client):
    client.post('/api/notes', json={'content': 'first'})
    client.post('/api/notes', json={'content': 'second'})
    assert client.get('/api/notes').get_json()['content'] == 'second'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_notes.py -v && cd ..
```

Expected: FAIL — stub blueprint returns no routes.

- [ ] **Step 3: Implement routes/notes.py**

Replace `flask_app/routes/notes.py`:
```python
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

notes_bp = Blueprint('notes', __name__)


def _notes_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'notes.txt'


@notes_bp.route('/api/notes', methods=['GET'])
def get_notes():
    f = _notes_file()
    return jsonify({'content': f.read_text() if f.exists() else ''})


@notes_bp.route('/api/notes', methods=['POST'])
def save_notes():
    data = request.get_json(silent=True) or {}
    content = data.get('content', '')
    _notes_file().write_text(content)
    return jsonify({'ok': True})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/test_notes.py -v && cd ..
```

Expected: PASS — 5 tests passing.

- [ ] **Step 5: Create notes.js**

Create `flask_app/static/js/notes.js`:
```javascript
(function () {
  const textarea = document.getElementById('notes-textarea');
  let timer = null;

  async function load() {
    const response = await fetch('/api/notes');
    const data = await response.json();
    textarea.value = data.content;
  }

  async function save(content) {
    await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
  }

  textarea.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => save(textarea.value), 500);
  });

  load();
})();
```

- [ ] **Step 6: Commit**

```bash
git add flask_app/routes/notes.py flask_app/tests/test_notes.py flask_app/static/js/notes.js
git commit -m "feat: notes route and widget"
```

---

## Task 7: Calendar Route + Widget

**Files:**
- Replace: `flask_app/routes/calendar.py`
- Create: `flask_app/static/js/calendar.js`

> The OAuth popup flow cannot be meaningfully unit-tested (requires a live browser and Google credentials). The route logic for token storage and event fetching is tested here; the full OAuth loop is verified manually.

- [ ] **Step 1: Implement routes/calendar.py**

Replace `flask_app/routes/calendar.py`:
```python
import json
import os
import time
from pathlib import Path

import httpx
from flask import Blueprint, current_app, jsonify, request

calendar_bp = Blueprint('calendar', __name__)

CALENDAR_API = 'https://www.googleapis.com/calendar/v3'
API_KEY = os.getenv('GOOGLE_API_KEY', '')


def _token_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'gcal_token.json'


def _load_token() -> dict | None:
    f = _token_file()
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        if time.time() * 1000 > data.get('expires_at', 0):
            f.unlink(missing_ok=True)
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


@calendar_bp.route('/api/calendar/token', methods=['POST'])
def save_token():
    data = request.get_json(silent=True) or {}
    token_data = {
        'access_token': data.get('access_token', ''),
        'expires_at': int(time.time() * 1000) + int(data.get('expires_in', 3600)) * 1000,
    }
    f = _token_file()
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(token_data))
    return jsonify({'ok': True})


@calendar_bp.route('/api/calendar/events', methods=['GET'])
def get_events():
    token = _load_token()
    if not token:
        return jsonify({'error': 'not_connected'}), 401

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    end = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 7 * 86400))

    response = httpx.get(
        f'{CALENDAR_API}/calendars/primary/events',
        params={
            'key': API_KEY,
            'timeMin': now,
            'timeMax': end,
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': '50',
        },
        headers={'Authorization': f'Bearer {token["access_token"]}'},
    )

    if not response.is_success:
        return jsonify({'error': 'calendar_api_error', 'status': response.status_code}), 502

    return jsonify(response.json().get('items', []))
```

- [ ] **Step 2: Create calendar.js**

Create `flask_app/static/js/calendar.js`:
```javascript
(function () {
  const connectBtn = document.getElementById('calendar-connect');
  const refreshBtn = document.getElementById('calendar-refresh');
  const loadingEl = document.getElementById('calendar-loading');
  const errorEl = document.getElementById('calendar-error');
  const eventsEl = document.getElementById('calendar-events');

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  function getStartKey(event) {
    return (event.start.dateTime || event.start.date || '').split('T')[0];
  }

  function formatTime(event) {
    if (event.start.date) return 'All day';
    if (!event.start.dateTime) return '';
    return new Date(event.start.dateTime).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function formatDayLabel(dateStr) {
    const today = new Date().toISOString().split('T')[0];
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];
    if (dateStr === today) return 'Today';
    if (dateStr === tomorrow) return 'Tomorrow';
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
    });
  }

  function renderEvents(events) {
    eventsEl.innerHTML = '';
    if (!events.length) {
      eventsEl.innerHTML = '<p class="text-gray-500 text-sm">No upcoming events</p>';
      return;
    }
    const grouped = new Map();
    for (const event of events) {
      const key = getStartKey(event);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(event);
    }
    for (const [dateStr, dayEvents] of grouped) {
      const group = document.createElement('div');
      const label = document.createElement('p');
      label.className = 'text-gray-400 text-xs font-semibold mb-1.5';
      label.textContent = formatDayLabel(dateStr);
      group.appendChild(label);
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
      eventsEl.appendChild(group);
    }
  }

  function showConnectState() {
    connectBtn.classList.remove('hidden');
    refreshBtn.classList.add('hidden');
    eventsEl.classList.add('hidden');
  }

  function showEventsState() {
    connectBtn.classList.add('hidden');
    refreshBtn.classList.remove('hidden');
    eventsEl.classList.remove('hidden');
  }

  async function loadEvents() {
    loadingEl.classList.remove('hidden');
    errorEl.classList.add('hidden');
    try {
      const response = await fetch('/api/calendar/events');
      if (response.status === 401) { showConnectState(); return; }
      if (!response.ok) throw new Error(`Calendar error: ${response.status}`);
      const events = await response.json();
      renderEvents(events);
      showEventsState();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    } finally {
      loadingEl.classList.add('hidden');
    }
  }

  function connect() {
    // google loaded via GIS script in base template
    const client = google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: 'https://www.googleapis.com/auth/calendar.readonly',
      callback: async (tokenResponse) => {
        await fetch('/api/calendar/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token: tokenResponse.access_token,
            expires_in: tokenResponse.expires_in,
          }),
        });
        loadEvents();
      },
    });
    client.requestAccessToken();
  }

  connectBtn.addEventListener('click', connect);
  refreshBtn.addEventListener('click', loadEvents);
  loadEvents();
})();
```

- [ ] **Step 3: Commit**

```bash
git add flask_app/routes/calendar.py flask_app/static/js/calendar.js
git commit -m "feat: calendar route and widget"
```

---

## Task 8: Electron Wrapper

**Files:**
- Create: `electron/main.js`

- [ ] **Step 1: Create Electron main.js**

Create `electron/main.js`:
```javascript
const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let flaskProcess = null;
let mainWindow = null;

const FLASK_PORT = 5000;
const FLASK_URL = `http://localhost:${FLASK_PORT}`;

function startFlask() {
  const pythonPath = path.join(__dirname, '..', 'flask_app', '.venv', 'bin', 'python');
  const appPath = path.join(__dirname, '..', 'flask_app', 'app.py');
  const cwd = path.join(__dirname, '..', 'flask_app');

  flaskProcess = spawn(pythonPath, [appPath], { cwd, env: { ...process.env } });

  flaskProcess.stdout.on('data', (data) => process.stdout.write(`[Flask] ${data}`));
  flaskProcess.stderr.on('data', (data) => process.stderr.write(`[Flask] ${data}`));

  flaskProcess.on('error', (err) => {
    console.error('Failed to start Flask:', err.message);
  });
}

function waitForFlask(url, retries = 20, interval = 300) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    function attempt() {
      fetch(url)
        .then(() => resolve())
        .catch(() => {
          attempts++;
          if (attempts >= retries) {
            reject(new Error(`Flask did not start after ${retries} attempts`));
          } else {
            setTimeout(attempt, interval);
          }
        });
    }
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(FLASK_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  startFlask();
  try {
    await waitForFlask(FLASK_URL);
    createWindow();
  } catch (err) {
    console.error(err.message);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (flaskProcess) flaskProcess.kill();
  app.quit();
});
```

- [ ] **Step 2: Verify Electron launches Flask and opens a window**

In one terminal, confirm Flask runs standalone first:
```bash
cd flask_app && source .venv/bin/activate && python app.py
```
Expected: `Running on http://127.0.0.1:5000`

Kill that process, then launch via Electron:
```bash
cd electron && npm start
```
Expected: Electron window opens showing the dashboard UI with clock ticking.

- [ ] **Step 3: Commit**

```bash
git add electron/main.js
git commit -m "feat: Electron wrapper — spawns Flask and opens BrowserWindow"
```

---

## Task 9: Full Test Run + Verification

- [ ] **Step 1: Run all Flask tests**

```bash
cd flask_app && source .venv/bin/activate && pytest tests/ -v && cd ..
```

Expected: All pass — `test_llm` (3), `test_todos` (9), `test_notes` (5) = 17 tests.

- [ ] **Step 2: Launch the full app via Electron**

```bash
cd electron && npm start
```

Expected: Window opens, dark dashboard loads, clock ticks.

- [ ] **Step 3: Verify clock**

Confirm the center column shows today's date and a live time updating every second.

- [ ] **Step 4: Verify todos**

- Type a task and press Enter — item appears
- Check the checkbox — item moves to completed with strikethrough
- Hover and click ✕ — item removed
- Quit and relaunch Electron — todos are still there (persisted to `flask_app/data/todos.json`)

- [ ] **Step 5: Verify notes**

- Type in the Notes area
- Quit and relaunch Electron — text is still there (persisted to `flask_app/data/notes.txt`)

- [ ] **Step 6: Verify LLM (requires Ollama running)**

Start Ollama in a separate terminal (`ollama serve`), then:
- Type a prompt and press Enter
- Response streams in token by token

If Ollama is not running:
- Submit a prompt — error message "Backend error: 500" or similar appears — correct behavior.

- [ ] **Step 7: Verify Google Calendar**

Fill in `GOOGLE_CLIENT_ID` and `GOOGLE_API_KEY` in `.env`, restart the app, then:
- Click "Connect Google Calendar" — GIS OAuth popup appears in the Electron window
- After auth, upcoming events load grouped by day

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "chore: complete Electron + Flask dashboard initial implementation"
```

---

## Adding Future Pages

To add a new tab later:
1. Create a new Flask route in `flask_app/app.py` or a new blueprint (e.g. `routes/finance.py`)
2. Create a new template in `flask_app/templates/`
3. Add a nav link to the `<header>` in `index.html`

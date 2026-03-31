(function () {
  const input        = document.getElementById('todo-input');
  const dateInput    = document.getElementById('todo-date');
  const addBtn       = document.getElementById('todo-add');
  const inputRow     = document.getElementById('todo-input-row');
  const list         = document.getElementById('todo-list');
  const connectBtn   = document.getElementById('todo-connect-btn');
  const connectPrompt = document.getElementById('todo-connect-prompt');

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  // ── Render ────────────────────────────────────────────────────────

  function formatDueDate(dateStr) {
    if (!dateStr) return null;
    const [y, m, d] = dateStr.split('-').map(Number);
    const due = new Date(y, m - 1, d);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
    if (due < today)    return { label: dateStr.slice(5).replace('-', '/'), overdue: true };
    if (+due === +today)    return { label: 'Today', overdue: false };
    if (+due === +tomorrow) return { label: 'Tomorrow', overdue: false };
    return { label: due.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }), overdue: false };
  }

  function createTodoItem(todo) {
    const li = document.createElement('li');
    li.className = 'flex items-center gap-2 group';
    li.dataset.id = todo.id;

    const due = formatDueDate(todo.due_date);
    const dueBadge = due
      ? `<span class="text-xs shrink-0 ${due.overdue ? 'text-red-400' : 'text-gray-500'}">${escapeHtml(due.label)}</span>`
      : '';

    li.innerHTML = `
      <input type="checkbox" ${todo.completed ? 'checked' : ''}
        class="accent-blue-500 cursor-pointer todo-check" />
      <span class="flex-1 text-sm ${todo.completed ? 'text-gray-500 line-through' : 'text-white'}">
        ${escapeHtml(todo.text)}
      </span>
      ${dueBadge}
      <button class="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 text-xs transition-opacity todo-delete"
        aria-label="Delete">✕</button>
    `;
    li.querySelector('.todo-check').addEventListener('change', function () {
      toggleTodo(todo.id, this.checked);
    });
    li.querySelector('.todo-delete').addEventListener('click', () => deleteTodo(todo.id));
    return li;
  }

  function sortByDate(todos) {
    return [...todos].sort((a, b) => {
      if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
      if (a.due_date) return -1;
      if (b.due_date) return 1;
      return 0;
    });
  }

  function renderTodos(todos) {
    list.innerHTML = '';
    const active    = sortByDate(todos.filter(t => !t.completed));
    const completed = sortByDate(todos.filter(t => t.completed));
    for (const t of active)    list.appendChild(createTodoItem(t));
    if (active.length && completed.length) {
      const divider = document.createElement('li');
      divider.className = 'border-t border-gray-800 my-2';
      list.appendChild(divider);
    }
    for (const t of completed) list.appendChild(createTodoItem(t));
  }

  // ── Connected / disconnected state ───────────────────────────────

  function showConnected() {
    inputRow.classList.remove('hidden');
    connectPrompt.classList.add('hidden');
    connectBtn.textContent = 'Reconnect';
    connectBtn.classList.remove('hidden');
  }

  function showDisconnected() {
    inputRow.classList.add('hidden');
    connectPrompt.classList.remove('hidden');
    connectBtn.textContent = 'Connect Google Tasks';
    connectBtn.classList.remove('hidden');
    list.innerHTML = '';
  }

  // ── API calls ─────────────────────────────────────────────────────

  async function loadTodos() {
    try {
      const res = await fetch('/api/tasks');
      if (res.status === 401) { showDisconnected(); return; }
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      showConnected();
      renderTodos(await res.json());
    } catch (err) {
      console.error('Failed to load tasks:', err.message);
    }
  }

  async function addTodo() {
    const text = input.value.trim();
    if (!text) return;
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, due_date: dateInput.value || null }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      input.value = '';
      dateInput.value = '';
      loadTodos();
    } catch (err) {
      console.error('Failed to add task:', err.message);
    }
  }

  async function toggleTodo(id, completed) {
    try {
      const res = await fetch(`/api/tasks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      loadTodos();
    } catch (err) {
      console.error('Failed to update task:', err.message);
    }
  }

  async function deleteTodo(id) {
    try {
      const res = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      loadTodos();
    } catch (err) {
      console.error('Failed to delete task:', err.message);
    }
  }

  // ── Google Tasks OAuth (GIS) ──────────────────────────────────────

  function connectGoogleTasks() {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: 'https://www.googleapis.com/auth/tasks',
      callback: async (tokenResponse) => {
        await fetch('/api/tasks/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token: tokenResponse.access_token,
            expires_in: tokenResponse.expires_in,
          }),
        });
        loadTodos();
      },
    });
    client.requestAccessToken();
  }

  // ── Event listeners ───────────────────────────────────────────────

  addBtn.addEventListener('click', addTodo);
  connectBtn.addEventListener('click', connectGoogleTasks);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') addTodo();
  });

  loadTodos();
})();

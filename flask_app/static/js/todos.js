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

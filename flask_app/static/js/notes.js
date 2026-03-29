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

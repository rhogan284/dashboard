(function () {
  const textarea = document.getElementById('notes-textarea');
  let timer = null;

  async function load() {
    try {
      const response = await fetch('/api/notes');
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const data = await response.json();
      textarea.value = data.content;
    } catch (err) {
      console.error('Failed to load notes:', err.message);
    }
  }

  async function save(content) {
    try {
      const response = await fetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
    } catch (err) {
      console.error('Failed to save notes:', err.message);
    }
  }

  textarea.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => save(textarea.value), 500);
  });

  load();
})();

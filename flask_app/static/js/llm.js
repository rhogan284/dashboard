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

(function () {
  const input       = document.getElementById('llm-input');
  const submitBtn   = document.getElementById('llm-submit');
  const newChatBtn  = document.getElementById('llm-new-chat');
  const historyDiv  = document.getElementById('llm-history');
  const scrollArea  = document.getElementById('llm-scroll-area');
  const thinkingDiv = document.getElementById('llm-thinking');
  const timerSpan   = document.getElementById('llm-timer');
  const errorP      = document.getElementById('llm-error');

  let messages = [];
  let timerInterval = null;
  let toolStatus = null;

  // ── Rendering ─────────────────────────────────────────────────────

  function scrollToBottom() {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  function renderHistory() {
    historyDiv.innerHTML = '';
    for (const msg of messages) {
      const bubble = document.createElement('div');
      bubble.className = msg.role === 'user'
        ? 'self-end bg-blue-700 text-white text-sm rounded-lg px-4 py-2 max-w-[85%] whitespace-pre-wrap'
        : 'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] whitespace-pre-wrap';
      bubble.textContent = msg.content;
      historyDiv.appendChild(bubble);
    }

    newChatBtn.classList.toggle('hidden', messages.length === 0);
    scrollToBottom();
  }

  // ── Thinking timer ────────────────────────────────────────────────

  function startTimer() {
    toolStatus = null;
    const startTime = Date.now();
    thinkingDiv.classList.remove('hidden');
    timerSpan.textContent = 'Thinking… 0s';
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      timerSpan.textContent = toolStatus
        ? `${toolStatus} (${elapsed}s)`
        : `Thinking… ${elapsed}s`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    toolStatus = null;
    thinkingDiv.classList.add('hidden');
    timerSpan.textContent = 'Thinking… 0s';
  }

  // ── Submit ────────────────────────────────────────────────────────

  async function submit() {
    const prompt = input.value.trim();
    if (!prompt) return;

    messages.push({ role: 'user', content: prompt });
    input.value = '';
    errorP.classList.add('hidden');
    renderHistory();
    startTimer();
    submitBtn.disabled = true;

    let assistantContent = '';

    // Append a live bubble for in-progress streaming (outside messages[])
    const streamBubble = document.createElement('div');
    streamBubble.className =
      'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] whitespace-pre-wrap';
    streamBubble.textContent = '';
    historyDiv.appendChild(streamBubble);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages }),
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
            if (data.error) throw new Error(data.error);
            if (data.status) { toolStatus = data.status; }
            const token = data.message?.content;
            if (token) {
              assistantContent += token;
              streamBubble.textContent = assistantContent;
              scrollToBottom();
            }
          } catch (parseErr) {
            if (parseErr.message && !parseErr.message.startsWith('Unexpected')) throw parseErr;
          }
        }
      }

      // Commit assistant turn and do a clean render
      messages.push({ role: 'assistant', content: assistantContent });
      renderHistory();

    } catch (err) {
      // Roll back optimistic user push
      messages.pop();
      streamBubble.remove();
      renderHistory();
      errorP.textContent = err.message || 'Failed to connect to backend';
      errorP.classList.remove('hidden');
    } finally {
      stopTimer();
      submitBtn.disabled = false;
      input.focus();
    }
  }

  // ── New Chat ──────────────────────────────────────────────────────

  function newChat() {
    messages = [];
    renderHistory();
    errorP.classList.add('hidden');
    input.value = '';
    input.focus();
  }

  // ── Event listeners ───────────────────────────────────────────────

  submitBtn.addEventListener('click', submit);
  newChatBtn.addEventListener('click', newChat);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });
})();

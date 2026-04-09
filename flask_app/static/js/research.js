(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────────────────
  let activeSessionId = null;
  let messages = [];
  let thinkingEnabled = false;
  let timerInterval = null;
  let toolStatus = null;

  // ── DOM refs ──────────────────────────────────────────────────────────────────
  const newChatBtn      = document.getElementById('research-new-chat');
  const sessionList     = document.getElementById('research-session-list');
  const pinboardList    = document.getElementById('research-pinboard-list');
  const pinboardWarn    = document.getElementById('research-pinboard-warn');
  const addPinBtn       = document.getElementById('research-add-pin');
  const historyDiv      = document.getElementById('research-history');
  const scrollArea      = document.getElementById('research-scroll-area');
  const thinkingDiv     = document.getElementById('research-thinking');
  const timerSpan       = document.getElementById('research-timer');
  const errorP          = document.getElementById('research-error');
  const input           = document.getElementById('research-input');
  const submitBtn       = document.getElementById('research-submit');
  const thinkToggleBtn  = document.getElementById('research-think-toggle');
  const attachToggle    = document.getElementById('research-attach-toggle');
  const reviewBtn        = document.getElementById('research-portfolio-review');
  const filePathInput   = document.getElementById('research-file-path');
  const filePathRow     = document.getElementById('research-file-path-row');
  const activityLogDiv  = document.getElementById('research-activity-log');

  // ── Utilities ──────────────────────────────────────────────────────────────────

  function relativeDate(isoStr) {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  }

  function scrollToBottom() {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  // ── Thinking timer ─────────────────────────────────────────────────────────────

  function startTimer() {
    toolStatus = null;
    activityLogDiv.innerHTML = '';
    const startTime = Date.now();
    thinkingDiv.classList.remove('hidden');
    timerSpan.textContent = 'Thinking… 0s';
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      timerSpan.textContent = `Thinking… ${elapsed}s`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    toolStatus = null;
    activityLogDiv.innerHTML = '';
    thinkingDiv.classList.add('hidden');
    timerSpan.textContent = 'Thinking… 0s';
  }

  function logActivity(text) {
    const line = document.createElement('div');
    line.className = 'text-gray-500 text-xs';
    line.textContent = `→ ${text}`;
    activityLogDiv.appendChild(line);
    scrollToBottom();
  }

  // ── Message rendering ──────────────────────────────────────────────────────────

  function renderHistory() {
    historyDiv.innerHTML = '';
    for (const msg of messages) {
      if (msg.role === 'tool') continue;
      const bubble = document.createElement('div');
      if (msg.role === 'user') {
        bubble.className =
          'self-end bg-blue-700 text-white text-sm rounded-lg px-4 py-2 max-w-[85%] whitespace-pre-wrap';
        bubble.textContent = msg.content;
      } else {
        bubble.className =
          'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] prose prose-sm prose-invert max-w-none';
        bubble.innerHTML = marked.parse(msg.content);
      }
      historyDiv.appendChild(bubble);
    }
    scrollToBottom();
  }

  // ── Session list ───────────────────────────────────────────────────────────────

  async function loadSessions() {
    try {
      const res = await fetch('/api/research/sessions');
      if (!res.ok) return;
      const sessions = await res.json();
      renderSessionList(sessions);
    } catch (_) {}
  }

  function updateActiveHighlight() {
    for (const li of sessionList.children) {
      const isActive = parseInt(li.dataset.id) === activeSessionId;
      li.className = `flex items-start justify-between gap-1 px-2 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
        isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
      }`;
    }
  }

  function renderSessionList(sessions) {
    sessionList.innerHTML = '';
    for (const s of sessions) {
      const li = document.createElement('li');
      li.dataset.id = s.id;
      const isActive = s.id === activeSessionId;
      li.className = `flex items-start justify-between gap-1 px-2 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
        isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
      }`;

      const left = document.createElement('div');
      left.className = 'flex-1 min-w-0';
      const title = document.createElement('div');
      title.className = 'truncate text-xs font-medium text-gray-100';
      title.textContent = s.title;
      const date = document.createElement('div');
      date.className = 'text-gray-500 text-xs mt-0.5';
      date.textContent = relativeDate(s.updated_at);
      left.appendChild(title);
      left.appendChild(date);

      const delBtn = document.createElement('button');
      delBtn.className = 'text-gray-600 hover:text-red-400 text-xs shrink-0 pt-0.5 transition-colors';
      delBtn.textContent = '✕';
      delBtn.title = 'Delete session';
      delBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch(`/api/research/sessions/${s.id}`, { method: 'DELETE' });
        if (activeSessionId === s.id) {
          activeSessionId = null;
          messages = [];
          renderHistory();
        }
        loadSessions();
      });

      li.appendChild(left);
      li.appendChild(delBtn);
      li.addEventListener('click', () => loadSession(s.id));
      sessionList.appendChild(li);
    }
  }

  async function loadSession(id) {
    if (activeSessionId === id) return;
    activeSessionId = id;
    updateActiveHighlight();
    try {
      const res = await fetch(`/api/research/sessions/${id}`);
      if (!res.ok) return;
      if (activeSessionId !== id) return;  // user clicked away — discard stale response
      const data = await res.json();
      messages = data.messages
        .filter(m => m.role !== 'tool')
        .map(m => ({ role: m.role, content: m.content }));
      renderHistory();
      errorP.classList.add('hidden');
      if (data.title === 'New session' && messages.length > 0) {
        refreshTitle();
      }
    } catch (err) {
      if (activeSessionId !== id) return;
      errorP.textContent = 'Failed to load session.';
      errorP.classList.remove('hidden');
    }
  }

  // ── Pinboard ───────────────────────────────────────────────────────────────────

  async function loadPinboard() {
    try {
      const res = await fetch('/api/research/pinboard');
      if (!res.ok) return;
      const notes = await res.json();
      renderPinboard(notes);
    } catch (_) {}
  }

  function renderPinboard(notes) {
    pinboardList.innerHTML = '';
    const totalChars = notes.reduce((sum, n) => sum + n.content.length, 0);
    pinboardWarn.classList.toggle('hidden', totalChars <= 2000);

    for (const note of notes) {
      const li = document.createElement('li');
      li.className = 'group rounded-lg overflow-hidden';

      const header = document.createElement('div');
      header.className =
        'flex items-center justify-between px-2 py-1.5 cursor-pointer hover:bg-gray-800 rounded-lg transition-colors';
      const titleSpan = document.createElement('span');
      titleSpan.className = 'text-xs text-gray-300 truncate flex-1';
      titleSpan.textContent = note.title;

      const tags = (note.tags || '').split(',').map(t => t.trim()).filter(Boolean);

      const delBtn = document.createElement('button');
      delBtn.className = 'ml-1 text-gray-600 hover:text-red-400 text-xs transition-colors opacity-0 group-hover:opacity-100';
      delBtn.textContent = '✕';
      delBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await fetch(`/api/research/pinboard/${note.id}`, { method: 'DELETE' });
        loadPinboard();
      });

      header.appendChild(titleSpan);
      tags.forEach(t => {
        const s = document.createElement('span');
        s.className = 'ml-1 px-1 py-0.5 bg-gray-700 text-gray-500 text-xs rounded';
        s.textContent = t;
        header.appendChild(s);
      });
      header.appendChild(delBtn);

      const body = document.createElement('div');
      body.className = 'hidden px-2 pb-2 space-y-1';
      const titleInput = document.createElement('input');
      titleInput.value = note.title;
      titleInput.className =
        'w-full bg-gray-800 text-white text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500';
      const contentTA = document.createElement('textarea');
      contentTA.value = note.content;
      contentTA.rows = 4;
      contentTA.className =
        'w-full bg-gray-800 text-gray-200 text-xs rounded px-2 py-1 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500';
      const tagsInput = document.createElement('input');
      tagsInput.value = note.tags;
      tagsInput.placeholder = 'tags (comma-separated)';
      tagsInput.className =
        'w-full bg-gray-800 text-gray-400 text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500';
      const saveBtn = document.createElement('button');
      saveBtn.textContent = 'Save';
      saveBtn.className = 'px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors';
      saveBtn.addEventListener('click', async () => {
        await fetch(`/api/research/pinboard/${note.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: titleInput.value.trim(),
            content: contentTA.value.trim(),
            tags: tagsInput.value.trim(),
          }),
        });
        loadPinboard();
      });

      body.appendChild(titleInput);
      body.appendChild(contentTA);
      body.appendChild(tagsInput);
      body.appendChild(saveBtn);

      header.addEventListener('click', () => {
        body.classList.toggle('hidden');
      });

      li.appendChild(header);
      li.appendChild(body);
      pinboardList.appendChild(li);
    }
  }

  function showAddPinForm() {
    const existing = document.getElementById('research-add-pin-form');
    if (existing) { existing.remove(); return; }

    const form = document.createElement('li');
    form.id = 'research-add-pin-form';
    form.className = 'rounded-lg bg-gray-800 p-2 space-y-1 mb-1';

    const titleInput = document.createElement('input');
    titleInput.placeholder = 'Title';
    titleInput.className =
      'w-full bg-gray-700 text-white text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500';
    const contentTA = document.createElement('textarea');
    contentTA.placeholder = 'Note body…';
    contentTA.rows = 3;
    contentTA.className =
      'w-full bg-gray-700 text-gray-200 text-xs rounded px-2 py-1 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500';
    const tagsInput = document.createElement('input');
    tagsInput.placeholder = 'tags (comma-separated)';
    tagsInput.className =
      'w-full bg-gray-700 text-gray-400 text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500';
    const row = document.createElement('div');
    row.className = 'flex gap-1';
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Add';
    saveBtn.className =
      'flex-1 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors';
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className =
      'flex-1 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs rounded transition-colors';

    saveBtn.addEventListener('click', async () => {
      const title = titleInput.value.trim();
      if (!title) return;
      await fetch('/api/research/pinboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          content: contentTA.value.trim(),
          tags: tagsInput.value.trim(),
        }),
      });
      form.remove();
      loadPinboard();
    });
    cancelBtn.addEventListener('click', () => form.remove());

    row.appendChild(saveBtn);
    row.appendChild(cancelBtn);
    form.appendChild(titleInput);
    form.appendChild(contentTA);
    form.appendChild(tagsInput);
    form.appendChild(row);
    pinboardList.prepend(form);
    titleInput.focus();
  }

  // ── Session lifecycle ──────────────────────────────────────────────────────────

  function createNewSession() {
    triggerSummarise(activeSessionId);
    activeSessionId = null;
    messages = [];
    renderHistory();
    errorP.classList.add('hidden');
    updateActiveHighlight();
    input.focus();
  }

  function triggerSummarise(sessionId) {
    if (!sessionId) return;
    fetch(`/api/research/sessions/${sessionId}/summarise`, { method: 'POST' }).catch(() => {});
  }

  // ── Portfolio Review ───────────────────────────────────────────────────────────

  async function startPortfolioReview() {
    reviewBtn.disabled = true;
    reviewBtn.textContent = 'Reviewing…';

    triggerSummarise(activeSessionId);
    // Show a short placeholder bubble instead of the full prompt
    const today = new Date().toLocaleDateString('en-AU', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
    messages = [{ role: 'user', content: `Portfolio Review — ${today}` }];
    renderHistory();
    startTimer();
    errorP.classList.add('hidden');

    const streamBubble = document.createElement('div');
    streamBubble.className =
      'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] prose prose-sm prose-invert max-w-none';
    historyDiv.appendChild(streamBubble);
    scrollToBottom();

    let assistantContent = '';

    try {
      const response = await fetch('/api/research/review', { method: 'POST' });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || `Backend error: ${response.status}`);
      }

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
            if (data.session_id) {
              activeSessionId = data.session_id;
            }
            if (data.status) { toolStatus = data.status; logActivity(data.status); }
            const token = data.message?.content;
            if (token) {
              assistantContent += token;
              streamBubble.innerHTML = marked.parse(assistantContent);
              scrollToBottom();
            }
          } catch (parseErr) {
            if (parseErr.message && !parseErr.message.startsWith('Unexpected')) throw parseErr;
          }
        }
      }

      loadSessions();
      messages.push({ role: 'assistant', content: assistantContent });
      renderHistory();
      refreshTitle();

    } catch (err) {
      messages.pop();
      streamBubble.remove();
      renderHistory();
      errorP.textContent = err.message || 'Failed to start portfolio review';
      errorP.classList.remove('hidden');
    } finally {
      stopTimer();
      reviewBtn.disabled = false;
      reviewBtn.textContent = 'Portfolio Review';
    }
  }

  async function refreshTitle() {
    const id = activeSessionId;
    if (!id || messages.length === 0) return;
    const first = messages.find(m => m.role === 'user');
    if (!first) return;
    const line = first.content.split('\n')[0].trim();
    if (!line || line.length < 3) return;
    const title = line.length > 60 ? line.slice(0, 57) + '…' : line;
    fetch(`/api/research/sessions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then(() => loadSessions()).catch(() => {});
  }

  // ── Submit ─────────────────────────────────────────────────────────────────────

  async function submit() {
    const prompt = input.value.trim();
    if (!prompt) return;

    if (!activeSessionId) {
      const res = await fetch('/api/research/sessions', { method: 'POST' });
      if (!res.ok) return;
      const { id } = await res.json();
      activeSessionId = id;
      loadSessions();
    }

    const filePath = filePathInput.value.trim();
    const fullPrompt = filePath ? `${prompt}\n\nFile: ${filePath}` : prompt;

    messages.push({ role: 'user', content: fullPrompt });
    input.value = '';
    errorP.classList.add('hidden');
    renderHistory();
    startTimer();
    submitBtn.disabled = true;

    const isFirstExchange = messages.length === 1;

    const streamBubble = document.createElement('div');
    streamBubble.className =
      'self-start bg-gray-800 text-gray-100 text-sm rounded-lg px-4 py-2 max-w-[85%] prose prose-sm prose-invert max-w-none';
    historyDiv.appendChild(streamBubble);

    let assistantContent = '';

    try {
      const response = await fetch('/api/research/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: activeSessionId,
          messages,
          think: thinkingEnabled,
        }),
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
            if (data.status) { toolStatus = data.status; logActivity(data.status); }
            const token = data.message?.content;
            if (token) {
              assistantContent += token;
              streamBubble.innerHTML = marked.parse(assistantContent);
              scrollToBottom();
            }
          } catch (parseErr) {
            if (parseErr.message && !parseErr.message.startsWith('Unexpected')) throw parseErr;
          }
        }
      }

      messages.push({ role: 'assistant', content: assistantContent });
      renderHistory();

      if (isFirstExchange) {
        refreshTitle();
      }

    } catch (err) {
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

  // ── Navigate-away hook (called by morning_brief.js) ────────────────────────────

  window.researchWillLeave = function () {
    triggerSummarise(activeSessionId);
  };

  // ── Init: called when Research tab becomes active ──────────────────────────────

  window.researchTabActivated = function () {
    loadSessions();
    loadPinboard();
  };

  // ── Event listeners ────────────────────────────────────────────────────────────

  newChatBtn.addEventListener('click', createNewSession);
  reviewBtn.addEventListener('click', startPortfolioReview);

  submitBtn.addEventListener('click', submit);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });

  thinkToggleBtn.addEventListener('click', () => {
    thinkingEnabled = !thinkingEnabled;
    thinkToggleBtn.className = thinkingEnabled
      ? 'px-2 py-1 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded-md transition-colors'
      : 'px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 text-xs rounded-md transition-colors';
  });

  attachToggle.addEventListener('click', () => {
    const hidden = filePathRow.classList.contains('hidden');
    filePathRow.classList.toggle('hidden', !hidden);
    attachToggle.className = hidden
      ? 'px-2 py-1 bg-blue-700 text-white text-xs rounded-md transition-colors'
      : 'px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 text-xs rounded-md transition-colors';
    if (hidden) filePathInput.focus();
  });

  addPinBtn.addEventListener('click', showAddPinForm);

})();

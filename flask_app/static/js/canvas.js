(function () {
  'use strict';

  // ── State ─────────────────────────────────────────────────────────────────────
  let activeSessionId = null;
  let activeCourseId = null;
  let messages = [];
  let thinkingEnabled = true;

  // ── DOM refs ──────────────────────────────────────────────────────────────────
  const newChatBtn     = document.getElementById('canvas-new-chat');
  const courseList     = document.getElementById('canvas-course-list');
  const sessionList    = document.getElementById('canvas-session-list');
  const historyDiv     = document.getElementById('canvas-history');
  const scrollArea     = document.getElementById('canvas-scroll-area');
  const thinkingDiv    = document.getElementById('canvas-thinking');
  const timerSpan      = document.getElementById('canvas-timer');
  const errorP         = document.getElementById('canvas-error');
  const input          = document.getElementById('canvas-input');
  const submitBtn      = document.getElementById('canvas-submit');
  const thinkToggleBtn = document.getElementById('canvas-think-toggle');
  const attachToggle   = document.getElementById('canvas-attach-toggle');
  const filePathInput  = document.getElementById('canvas-file-path');
  const filePathRow    = document.getElementById('canvas-file-path-row');
  const syncBtn        = document.getElementById('canvas-sync-btn');
  const activityLogDiv = document.getElementById('canvas-activity-log');

  // ── Shared chat utilities ──────────────────────────────────────────────────────
  const { scrollToBottom, relativeDate, startTimer, stopTimer, logActivity, renderHistory, makeStreamBubble } =
    createChatUtils({ historyDiv, scrollArea, thinkingDiv, timerSpan, activityLogDiv });

  // ── Helpers ────────────────────────────────────────────────────────────────────

  function showError(msg) {
    errorP.textContent = msg;
    errorP.classList.remove('hidden');
  }

  function clearError() {
    errorP.classList.add('hidden');
  }

  // ── Course list ────────────────────────────────────────────────────────────────

  async function loadCourses() {
    try {
      const [coursesRes, countsRes] = await Promise.all([
        fetch('/api/canvas/courses'),
        fetch('/api/canvas/session-counts'),
      ]);
      if (!coursesRes.ok) return;
      const courses = await coursesRes.json();
      if (courses.error) return;
      const counts = countsRes.ok ? await countsRes.json() : {};
      renderCourseList(courses, counts);
    } catch (_) {}
  }

  function renderCourseList(courses, counts) {
    courseList.innerHTML = '';

    // "All Courses" row — shows general (unlinked) sessions
    const allLi = document.createElement('li');
    const allActive = activeCourseId === null;
    allLi.className = `flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer text-xs transition-colors ${
      allActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
    }`;
    const allLabel = document.createElement('span');
    allLabel.textContent = 'All Courses';
    allLi.appendChild(allLabel);
    const nullCount = counts['null'];
    if (nullCount) {
      const badge = document.createElement('span');
      badge.className = 'text-gray-500 text-xs';
      badge.textContent = nullCount;
      allLi.appendChild(badge);
    }
    allLi.addEventListener('click', () => selectCourse(null));
    courseList.appendChild(allLi);

    for (const c of courses) {
      const li = document.createElement('li');
      const isActive = c.id === activeCourseId;
      li.className = `flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer text-xs transition-colors ${
        isActive ? 'bg-gray-700 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'
      }`;
      const label = document.createElement('span');
      label.className = 'truncate';
      label.textContent = c.course_code || c.name;
      label.title = c.name;
      li.appendChild(label);
      const count = counts[String(c.id)];
      if (count) {
        const badge = document.createElement('span');
        badge.className = 'text-gray-500 text-xs shrink-0';
        badge.textContent = count;
        li.appendChild(badge);
      }
      li.addEventListener('click', () => selectCourse(c.id));
      courseList.appendChild(li);
    }
  }

  function selectCourse(courseId) {
    activeCourseId = courseId;
    activeSessionId = null;
    messages = [];
    renderHistory(messages);
    loadCourses();
    loadSessions();
  }

  // ── Session list ───────────────────────────────────────────────────────────────

  async function loadSessions() {
    try {
      const param = activeCourseId === null ? 'null' : activeCourseId;
      const res = await fetch(`/api/canvas/sessions?course_id=${param}`);
      if (!res.ok) return;
      const sessions = await res.json();
      renderSessionList(sessions);
    } catch (_) {}
  }

  function updateSessionHighlight() {
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
        await fetch(`/api/canvas/sessions/${s.id}`, { method: 'DELETE' });
        if (activeSessionId === s.id) {
          activeSessionId = null;
          messages = [];
          renderHistory(messages);
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
    updateSessionHighlight();
    try {
      const res = await fetch(`/api/canvas/sessions/${id}`);
      if (!res.ok) return;
      if (activeSessionId !== id) return;
      const data = await res.json();
      messages = data.messages
        .filter(m => m.role !== 'tool')
        .map(m => ({ role: m.role, content: m.content }));
      renderHistory(messages);
      clearError();
      if (data.title === 'New session' && messages.length > 0) {
        refreshTitle();
      }
    } catch (_) {
      if (activeSessionId !== id) return;
      showError('Failed to load session.');
    }
  }

  // ── Session lifecycle ──────────────────────────────────────────────────────────

  async function createNewSession() {
    triggerSummarise(activeSessionId);
    const body = activeCourseId !== null ? { course_id: activeCourseId } : {};
    const res = await fetch('/api/canvas/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) return;
    const { id } = await res.json();
    activeSessionId = id;
    messages = [];
    renderHistory(messages);
    clearError();
    loadSessions();
    loadCourses();
    input.focus();
  }

  function triggerSummarise(sessionId) {
    if (!sessionId) return;
    fetch(`/api/canvas/sessions/${sessionId}/summarise`, { method: 'POST' }).catch(() => {});
  }

  async function refreshTitle() {
    const id = activeSessionId;
    if (!id || messages.length === 0) return;
    const first = messages.find(m => m.role === 'user');
    if (!first) return;
    const line = first.content.split('\n')[0].trim();
    if (!line || line.length < 3) return;
    const title = line.length > 60 ? line.slice(0, 57) + '…' : line;
    fetch(`/api/canvas/sessions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then(() => loadSessions()).catch(() => {});
  }

  // ── Calendar sync ──────────────────────────────────────────────────────────────

  async function syncCalendar() {
    syncBtn.disabled = true;
    syncBtn.textContent = 'Syncing…';
    clearError();
    try {
      const res = await fetch('/api/canvas/sync-calendar', { method: 'POST' });
      const data = await res.json();
      if (!res.ok || data.error) {
        showError(data.error || 'Sync failed.');
      } else {
        syncBtn.textContent = `✓ ${data.created} added`;
        setTimeout(() => { syncBtn.textContent = 'Sync Cal'; }, 3000);
      }
    } catch (err) {
      showError('Calendar sync failed.');
    } finally {
      syncBtn.disabled = false;
    }
  }

  // ── Submit ─────────────────────────────────────────────────────────────────────

  async function submit() {
    const text = input.value.trim();
    if (!text) return;
    const filePath = filePathInput.value.trim();
    const prompt = filePath ? `${text}\n\nFile: ${filePath}` : text;

    if (!activeSessionId) {
      const body = activeCourseId !== null ? { course_id: activeCourseId } : {};
      const res = await fetch('/api/canvas/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) return;
      const { id } = await res.json();
      activeSessionId = id;
      loadSessions();
      loadCourses();
    }

    messages.push({ role: 'user', content: prompt });
    input.value = '';
    clearError();
    renderHistory(messages);
    startTimer();
    submitBtn.disabled = true;

    const isFirstExchange = messages.length === 1;

    const streamBubble = makeStreamBubble();

    let assistantContent = '';

    try {
      const body = { session_id: activeSessionId, messages, think: thinkingEnabled };
      if (activeCourseId !== null) body.course_id = activeCourseId;

      const response = await fetch('/api/canvas/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
            if (data.status) logActivity(data.status);
            const token = data.chunk ?? data.message?.content;
            if (token) {
              assistantContent += token;
              streamBubble.innerHTML = DOMPurify.sanitize(marked.parse(assistantContent));
              scrollToBottom();
            }
          } catch (parseErr) {
            if (parseErr.message && !parseErr.message.startsWith('Unexpected')) throw parseErr;
          }
        }
      }

      messages.push({ role: 'assistant', content: assistantContent });
      renderHistory(messages);

      if (isFirstExchange) {
        refreshTitle();
      }

    } catch (err) {
      messages.pop();
      streamBubble.remove();
      renderHistory(messages);
      showError(err.message || 'Failed to connect to backend');
    } finally {
      stopTimer();
      submitBtn.disabled = false;
      input.focus();
    }
  }

  // ── Init ───────────────────────────────────────────────────────────────────────

  window.canvasTabActivated = function () {
    loadCourses();
    loadSessions();
    if (!activeSessionId) {
      const body = activeCourseId !== null ? { course_id: activeCourseId } : {};
      fetch('/api/canvas/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
        .then(r => r.json())
        .then(({ id }) => {
          activeSessionId = id;
          loadSessions();
          loadCourses();
        })
        .catch(() => {});
    }
  };

  // ── Event listeners ────────────────────────────────────────────────────────────

  newChatBtn.addEventListener('click', createNewSession);
  syncBtn.addEventListener('click', syncCalendar);
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
      ? 'px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 text-xs rounded-md transition-colors'
      : 'px-2 py-1 bg-amber-600 hover:bg-amber-700 text-white text-xs rounded-md transition-colors';
  });

  attachToggle.addEventListener('click', () => {
    const hidden = filePathRow.classList.contains('hidden');
    filePathRow.classList.toggle('hidden', !hidden);
    attachToggle.className = hidden
      ? 'px-2 py-1 bg-blue-700 text-white text-xs rounded-md transition-colors'
      : 'px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-400 text-xs rounded-md transition-colors';
    if (hidden) filePathInput.focus();
  });

})();

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

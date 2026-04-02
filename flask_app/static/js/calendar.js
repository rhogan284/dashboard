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
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const localDate = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const today = localDate(now);
    const tomorrow = localDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
    if (dateStr === today) return 'Today';
    if (dateStr === tomorrow) return 'Tomorrow';
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
    });
  }

  function getISOBoundaries() {
    const now = new Date();
    const todayStr = now.toISOString().split('T')[0];

    // Day of week: 0=Sun,1=Mon,...,6=Sat — convert to ISO (0=Mon,...,6=Sun)
    const dow = (now.getDay() + 6) % 7; // 0=Mon, 6=Sun
    const daysToSunday = 6 - dow;

    const endOfThisWeek = new Date(now);
    endOfThisWeek.setDate(now.getDate() + daysToSunday);
    const endOfThisWeekStr = endOfThisWeek.toISOString().split('T')[0];

    const startOfNextWeek = new Date(endOfThisWeek);
    startOfNextWeek.setDate(endOfThisWeek.getDate() + 1);
    const startOfNextWeekStr = startOfNextWeek.toISOString().split('T')[0];

    const endOfNextWeek = new Date(startOfNextWeek);
    endOfNextWeek.setDate(startOfNextWeek.getDate() + 6);
    const endOfNextWeekStr = endOfNextWeek.toISOString().split('T')[0];

    return { todayStr, endOfThisWeekStr, startOfNextWeekStr, endOfNextWeekStr };
  }

  function classifyEvent(event, boundaries) {
    const key = getStartKey(event);
    const { todayStr, endOfThisWeekStr, startOfNextWeekStr, endOfNextWeekStr } = boundaries;
    if (key === todayStr) return 'today';
    if (key > todayStr && key <= endOfThisWeekStr) return 'this_week';
    if (key >= startOfNextWeekStr && key <= endOfNextWeekStr) return 'next_week';
    return null;
  }

  function renderDayGroup(dateStr, dayEvents, showDayLabel) {
    const group = document.createElement('div');
    if (showDayLabel) {
      const label = document.createElement('p');
      label.className = 'text-gray-500 text-xs font-medium uppercase tracking-wide mt-3 mb-1.5';
      label.textContent = formatDayLabel(dateStr);
      group.appendChild(label);
    }
    const list = document.createElement('div');
    list.className = 'space-y-1.5';
    for (const event of dayEvents) {
      const card = document.createElement('div');
      card.className = 'bg-gray-800 rounded-lg px-3 py-2.5 flex gap-3 items-start';
      card.innerHTML = `
        <span class="text-blue-400 text-xs tabular-nums shrink-0 pt-0.5 w-14">${formatTime(event)}</span>
        <span class="text-white text-sm leading-snug">${escapeHtml(event.summary || '')}</span>
      `;
      list.appendChild(card);
    }
    group.appendChild(list);
    return group;
  }

  function renderSection(label, events) {
    const section = document.createElement('div');
    section.className = 'mb-5';

    const header = document.createElement('div');
    header.className = 'flex items-center gap-2 mb-2';
    header.innerHTML = `
      <span class="w-1 h-4 bg-blue-500 rounded-full shrink-0"></span>
      <span class="text-white text-sm font-semibold">${label}</span>
    `;
    section.appendChild(header);

    const isToday = label === 'Today';
    const grouped = new Map();
    for (const event of events) {
      const key = getStartKey(event);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(event);
    }
    const inner = document.createElement('div');
    for (const [dateStr, dayEvents] of grouped) {
      inner.appendChild(renderDayGroup(dateStr, dayEvents, !isToday));
    }
    section.appendChild(inner);
    return section;
  }

  function renderEvents(events) {
    eventsEl.innerHTML = '';
    const boundaries = getISOBoundaries();
    const buckets = { today: [], this_week: [], next_week: [] };

    for (const event of events) {
      const bucket = classifyEvent(event, boundaries);
      if (bucket) buckets[bucket].push(event);
    }

    const hasAny = buckets.today.length || buckets.this_week.length || buckets.next_week.length;
    if (!hasAny) {
      eventsEl.innerHTML = '<p class="text-gray-500 text-sm">No upcoming events</p>';
      return;
    }

    if (buckets.today.length)     eventsEl.appendChild(renderSection('Today', buckets.today));
    if (buckets.this_week.length) eventsEl.appendChild(renderSection('This Week', buckets.this_week));
    if (buckets.next_week.length) eventsEl.appendChild(renderSection('Next Week', buckets.next_week));
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

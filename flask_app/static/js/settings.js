(function () {
  const settingsBtn    = document.getElementById('settings-btn');
  const dropdown       = document.getElementById('settings-dropdown');
  const container      = document.getElementById('settings-container');
  const tasksDot       = document.getElementById('settings-tasks-dot');
  const tasksSublabel  = document.getElementById('settings-tasks-sublabel');
  const tasksBtn       = document.getElementById('settings-tasks-btn');
  const googleDot      = document.getElementById('settings-google-dot');
  const googleSublabel = document.getElementById('settings-google-sublabel');
  const googleBtn      = document.getElementById('settings-google-btn');

  // ── Toggle ───────────────────────────────────────────────────────────────────

  settingsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const opening = dropdown.classList.contains('hidden');
    dropdown.classList.toggle('hidden');
    if (opening) refreshStatus();
  });

  document.addEventListener('click', (e) => {
    if (!container.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });

  // ── Status ───────────────────────────────────────────────────────────────────

  async function refreshStatus() {
    // Google Tasks
    try {
      const res = await fetch('/api/tasks');
      if (res.ok) {
        tasksDot.className = 'w-2 h-2 rounded-full bg-green-500 shrink-0';
        tasksSublabel.textContent = 'Tasks access granted';
        tasksBtn.textContent = 'Reconnect';
      } else {
        tasksDot.className = 'w-2 h-2 rounded-full bg-gray-600 shrink-0';
        tasksSublabel.textContent = 'Not connected';
        tasksBtn.textContent = 'Connect';
      }
    } catch {
      tasksDot.className = 'w-2 h-2 rounded-full bg-gray-600 shrink-0';
      tasksSublabel.textContent = 'Not connected';
      tasksBtn.textContent = 'Connect';
    }

    // Google Account (Brief / Gmail / Calendar)
    try {
      const res = await fetch('/api/brief/status');
      if (res.ok) {
        const data = await res.json();
        if (data.gmail_connected) {
          googleDot.className = 'w-2 h-2 rounded-full bg-green-500 shrink-0';
          googleSublabel.textContent = 'Gmail + Calendar access granted';
          googleBtn.textContent = 'Reconnect';
        } else {
          googleDot.className = 'w-2 h-2 rounded-full bg-gray-600 shrink-0';
          googleSublabel.textContent = 'Not connected';
          googleBtn.textContent = 'Connect';
        }
      }
    } catch {
      googleDot.className = 'w-2 h-2 rounded-full bg-gray-600 shrink-0';
      googleSublabel.textContent = 'Not connected';
      googleBtn.textContent = 'Connect';
    }
  }

  window.refreshSettingsStatus = refreshStatus;

  // ── Connect handlers ─────────────────────────────────────────────────────────

  tasksBtn.addEventListener('click', () => {
    if (window.connectGoogleTasks) {
      window.connectGoogleTasks(refreshStatus);
    }
  });

  googleBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/brief/auth');
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, '_blank');
      } else {
        console.error('Could not get auth URL:', data.error || 'unknown error');
      }
    } catch (e) {
      console.error('Network error fetching auth URL', e);
    }
  });
})();

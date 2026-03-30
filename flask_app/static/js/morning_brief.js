(function () {
  'use strict';

  // ── Tab switching ────────────────────────────────────────────────────────────
  const tabs = {
    dashboard: document.getElementById('tab-dashboard'),
    brief: document.getElementById('tab-brief'),
  };
  const tabBtns = document.querySelectorAll('.tab-btn');

  function activateTab(name) {
    Object.entries(tabs).forEach(([key, el]) => {
      if (!el) return;
      el.classList.toggle('hidden', key !== name);
      // flex-1 must be on the active tab so it fills available space
      el.classList.toggle('flex-1', key === name);
    });
    tabBtns.forEach(btn => {
      const active = btn.dataset.tab === name;
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-gray-700', active);
      btn.classList.toggle('border-b-2', active);
      btn.classList.toggle('border-blue-500', active);
      btn.classList.toggle('text-gray-400', !active);
      btn.classList.toggle('bg-transparent', !active);
    });
    // Fetch status only when on brief tab; clear interval on dashboard
    if (name === 'brief') {
      fetchStatus();
    } else {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    }
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });

  // ── Status polling ───────────────────────────────────────────────────────────
  const statusIcon = document.getElementById('brief-status-icon');
  const statusText = document.getElementById('brief-status-text');
  const statusTime = document.getElementById('brief-status-time');
  const connectBanner = document.getElementById('brief-connect-banner');
  const generateBtn = document.getElementById('brief-generate-btn');
  const previewFrame = document.getElementById('brief-preview-frame');
  const previewToggleHint = document.getElementById('brief-preview-toggle-hint');

  let pollInterval = null;
  let lastGeneratedAt = null;

  function formatTime(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'));
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  function applyStatus(data) {
    connectBanner.classList.toggle('hidden', data.gmail_connected === true);

    const icons = { success: '✅', error: '❌', running: '⏳', never_run: '⏳' };
    const texts = {
      success: 'Brief generated — draft saved to Gmail.',
      error: `Generation failed: ${data.error || 'unknown error'}`,
      running: 'Generating brief… this may take a minute.',
      never_run: 'No brief generated yet.',
    };

    statusIcon.textContent = icons[data.status] || '⏳';
    statusText.textContent = texts[data.status] || 'Unknown status.';
    statusTime.textContent = data.generated_at ? `Last run: ${formatTime(data.generated_at)}` : '';

    generateBtn.disabled = data.status === 'running';
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/api/brief/status');
      if (!res.ok) {
        statusText.textContent = 'Could not reach the brief service.';
        return;
      }
      const data = await res.json();
      const newGeneratedAt = data.generated_at;

      applyStatus(data);

      // If a new brief was generated, reload preview iframe
      if (newGeneratedAt && newGeneratedAt !== lastGeneratedAt) {
        lastGeneratedAt = newGeneratedAt;
        previewFrame.src = '/api/brief/preview?' + Date.now();
      }

      // Stop polling once no longer running
      if (data.status !== 'running' && pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    } catch (e) {
      console.error('Failed to fetch brief status', e);
    }
  }

  // ── Generate button ──────────────────────────────────────────────────────────
  generateBtn.addEventListener('click', async () => {
    generateBtn.disabled = true;
    try {
      const res = await fetch('/api/brief/generate', { method: 'POST' });
      const data = await res.json();
      if (data.started) {
        applyStatus({ status: 'running', gmail_connected: true, generated_at: lastGeneratedAt, error: null });
        // Poll every 3 seconds
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(fetchStatus, 3000);
      } else {
        statusText.textContent = `Failed to start: ${data.error || 'unknown error'}`;
        generateBtn.disabled = false;
      }
    } catch (e) {
      statusText.textContent = 'Network error starting generation.';
      generateBtn.disabled = false;
    }
  });

  // ── Gmail connect button ─────────────────────────────────────────────────────
  document.getElementById('brief-connect-btn').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/brief/auth');
      const data = await res.json();
      if (data.auth_url) {
        window.open(data.auth_url, '_blank');
      } else {
        alert('Could not get auth URL: ' + (data.error || 'unknown error'));
      }
    } catch (e) {
      alert('Network error fetching auth URL.');
    }
  });

  // ── Details toggle hint ──────────────────────────────────────────────────────
  const previewSection = document.getElementById('brief-preview-section');
  previewSection.addEventListener('toggle', () => {
    previewToggleHint.textContent = previewSection.open ? '▼ collapse' : '▶ expand';
  });

  // ── On load ──────────────────────────────────────────────────────────────────
  // Check if returning from OAuth (/?brief_connected=1)
  const params = new URLSearchParams(window.location.search);
  if (params.get('brief_connected') === '1') {
    activateTab('brief');
    // Strip the query param from the URL without reload
    window.history.replaceState({}, '', window.location.pathname);
  } else {
    activateTab('dashboard');
  }
})();

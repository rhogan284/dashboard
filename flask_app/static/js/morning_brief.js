(function () {
  'use strict';

  // ── Tab switching ────────────────────────────────────────────────────────────
  const tabs = {
    dashboard: document.getElementById('tab-dashboard'),
    brief: document.getElementById('tab-brief'),
    portfolio: document.getElementById('tab-portfolio'),
    research: document.getElementById('tab-research'),
    canvas: document.getElementById('tab-canvas'),
  };
  const tabBtns = document.querySelectorAll('.tab-btn');

  // ── Portfolio webview lazy load ──────────────────────────────────────────────
  const portfolioWebview  = document.getElementById('portfolio-webview');
  const portfolioLoading  = document.getElementById('portfolio-loading');
  let portfolioLoaded = false;

  function loadPortfolio() {
    if (portfolioLoaded) return;
    portfolioWebview.src = 'http://localhost:8000/portfolio';
    portfolioWebview.addEventListener('did-finish-load', () => {
      portfolioLoading.style.display = 'none';
      portfolioWebview.style.display = 'flex';
      portfolioLoaded = true;
    }, { once: true });
  }

  let currentTab = 'dashboard';

  function activateTab(name) {
    if (currentTab === 'research' && name !== 'research') {
      window.researchWillLeave?.();
    }
    if (name === 'research') {
      window.researchTabActivated?.();
    }
    if (name === 'canvas') {
      window.canvasTabActivated?.();
    }
    currentTab = name;
    Object.entries(tabs).forEach(([key, el]) => {
      if (!el) return;
      el.classList.toggle('hidden', key !== name);
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
    if (name === 'brief') {
      fetchStatus();
    } else {
      if (statusSSE) {
        statusSSE.close();
        statusSSE = null;
      }
    }
    if (name === 'portfolio') {
      loadPortfolio();
    }
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });

  // ── Status polling ───────────────────────────────────────────────────────────
  const statusIcon      = document.getElementById('brief-status-icon');
  const statusText      = document.getElementById('brief-status-text');
  const statusTime      = document.getElementById('brief-status-time');
  const generateBtn     = document.getElementById('brief-generate-btn');
  const briefContent    = document.getElementById('brief-content');
  const briefEmpty      = document.getElementById('brief-empty');

  let statusSSE = null;
  let lastGeneratedAt = null;

  function formatTime(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'));
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  async function loadBrief() {
    try {
      const res = await fetch('/api/brief/preview?' + Date.now());
      const md = await res.text();
      if (md.trim()) {
        briefContent.innerHTML = DOMPurify.sanitize(marked.parse(md));
        briefContent.classList.remove('hidden');
        briefEmpty.classList.add('hidden');
      } else {
        briefContent.classList.add('hidden');
        briefEmpty.classList.remove('hidden');
      }
    } catch (e) {
      console.error('Failed to load brief content', e);
    }
  }

  function applyStatus(data) {
    const icons = { success: '✅', error: '❌', running: '⏳', never_run: '⏳' };
    const texts = {
      success: 'Brief generated.',
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
      applyStatus(data);
      const newGeneratedAt = data.generated_at;
      if (newGeneratedAt && newGeneratedAt !== lastGeneratedAt) {
        lastGeneratedAt = newGeneratedAt;
        if (data.status === 'success') loadBrief();
      }
    } catch (e) {
      console.error('Failed to fetch brief status', e);
    }
  }

  function startSSE() {
    if (statusSSE) statusSSE.close();
    statusSSE = new EventSource('/api/brief/stream');
    statusSSE.onmessage = (e) => {
      const data = JSON.parse(e.data);
      applyStatus(data);
      const newGeneratedAt = data.generated_at;
      if (newGeneratedAt && newGeneratedAt !== lastGeneratedAt) {
        lastGeneratedAt = newGeneratedAt;
        if (data.status === 'success') loadBrief();
      }
      if (data.status !== 'running') {
        statusSSE.close();
        statusSSE = null;
      }
    };
    statusSSE.onerror = () => {
      statusSSE.close();
      statusSSE = null;
      fetchStatus();
    };
  }

  // ── Generate button ──────────────────────────────────────────────────────────
  generateBtn.addEventListener('click', async () => {
    generateBtn.disabled = true;
    try {
      const res = await fetch('/api/brief/generate', { method: 'POST' });
      const data = await res.json();
      if (data.started) {
        applyStatus({ status: 'running', gmail_connected: true, generated_at: lastGeneratedAt, error: null });
        startSSE();
      } else {
        statusText.textContent = `Failed to start: ${data.error || 'unknown error'}`;
        generateBtn.disabled = false;
      }
    } catch (e) {
      statusText.textContent = 'Network error starting generation.';
      generateBtn.disabled = false;
    }
  });

  // ── On load ──────────────────────────────────────────────────────────────────
  const params = new URLSearchParams(window.location.search);
  if (params.get('brief_connected') === '1') {
    activateTab('brief');
    window.history.replaceState({}, '', window.location.pathname);
  } else {
    activateTab('dashboard');
  }
})();

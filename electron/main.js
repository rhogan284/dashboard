const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let flaskProcess = null;
let portfolioProcess = null;
let mainWindow = null;

const FLASK_PORT = 8001;
const FLASK_URL = `http://localhost:${FLASK_PORT}`;

const DASHBOARD_DIR = path.join('/Users', 'ryanhogan', 'Desktop', 'Coding Work', 'Dashboard');

const PORTFOLIO_PORT = 8000;
const PORTFOLIO_APP_DIR = path.join('/Users', 'ryanhogan', 'Desktop', 'Coding Work', 'portfolio_app');
const PORTFOLIO_PYTHON = path.join(PORTFOLIO_APP_DIR, '.venv', 'bin', 'python');
const PORTFOLIO_SCRIPT = path.join(PORTFOLIO_APP_DIR, 'app.py');

function startPortfolio() {
  portfolioProcess = spawn(PORTFOLIO_PYTHON, [PORTFOLIO_SCRIPT], {
    cwd: PORTFOLIO_APP_DIR,
    env: { ...process.env },
  });
  portfolioProcess.stdout.on('data', (data) => process.stdout.write(`[Portfolio] ${data}`));
  portfolioProcess.stderr.on('data', (data) => process.stderr.write(`[Portfolio] ${data}`));
  portfolioProcess.on('error', (err) => {
    console.error('Failed to start portfolio app:', err.message);
  });
}

function startFlask() {
  const pythonPath = path.join(DASHBOARD_DIR, 'flask_app', '.venv', 'bin', 'python');
  const appPath = path.join(DASHBOARD_DIR, 'flask_app', 'app.py');
  const cwd = path.join(DASHBOARD_DIR, 'flask_app');

  flaskProcess = spawn(pythonPath, [appPath], { cwd, env: { ...process.env } });

  flaskProcess.stdout.on('data', (data) => process.stdout.write(`[Flask] ${data}`));
  flaskProcess.stderr.on('data', (data) => process.stderr.write(`[Flask] ${data}`));

  flaskProcess.on('error', (err) => {
    console.error('Failed to start Flask:', err.message);
  });
}

function waitForFlask(url, retries = 40, interval = 300) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    function attempt() {
      fetch(url)
        .then(() => resolve())
        .catch((err) => {
          attempts++;
          if (attempts >= retries) {
            reject(new Error(`Flask did not start after ${retries} attempts (${retries * interval / 1000}s): ${err.message}`));
          } else {
            setTimeout(attempt, interval);
          }
        });
    }
    attempt();
  });
}

function createSplash() {
  const splash = new BrowserWindow({
    width: 400,
    height: 160,
    frame: false,
    alwaysOnTop: true,
    webPreferences: { nodeIntegration: false },
  });
  splash.loadURL(
    'data:text/html,' +
    encodeURIComponent(
      '<body style="background:#111827;color:#f9fafb;font-family:system-ui;' +
      'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
      'height:100vh;margin:0;gap:12px">' +
      '<p style="font-size:1.1rem;margin:0">Starting Dashboard\u2026</p>' +
      '</body>'
    )
  );
  return splash;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // webSecurity disabled so the embedded portfolio webview (port 8000) can
      // load resources from a different origin than the main app (port 8001).
      webSecurity: false,
      webviewTag: true,
    },
  });

  // Strip "Electron/x.x.x" from the UA so Google OAuth doesn't block the popup
  const ua = mainWindow.webContents.getUserAgent().replace(/\s*Electron\/[\d.]+/, '');
  mainWindow.webContents.setUserAgent(ua);

  mainWindow.loadURL(FLASK_URL);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  startFlask();
  startPortfolio();
  const splash = createSplash();
  try {
    await waitForFlask(FLASK_URL);
    createWindow();
    splash.close();
  } catch (err) {
    console.error('[Startup]', err.message);
    splash.close();
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (flaskProcess) flaskProcess.kill();
  if (portfolioProcess) portfolioProcess.kill();
  app.quit();
});

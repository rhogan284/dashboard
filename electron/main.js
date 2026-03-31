const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let flaskProcess = null;
let mainWindow = null;

const FLASK_PORT = 8001;
const FLASK_URL = `http://localhost:${FLASK_PORT}`;

function startFlask() {
  const pythonPath = path.join(__dirname, '..', 'flask_app', '.venv', 'bin', 'python');
  const appPath = path.join(__dirname, '..', 'flask_app', 'app.py');
  const cwd = path.join(__dirname, '..', 'flask_app');

  flaskProcess = spawn(pythonPath, [appPath], { cwd, env: { ...process.env } });

  flaskProcess.stdout.on('data', (data) => process.stdout.write(`[Flask] ${data}`));
  flaskProcess.stderr.on('data', (data) => process.stderr.write(`[Flask] ${data}`));

  flaskProcess.on('error', (err) => {
    console.error('Failed to start Flask:', err.message);
  });
}

function waitForFlask(url, retries = 20, interval = 300) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    function attempt() {
      fetch(url)
        .then(() => resolve())
        .catch(() => {
          attempts++;
          if (attempts >= retries) {
            reject(new Error(`Flask did not start after ${retries} attempts`));
          } else {
            setTimeout(attempt, interval);
          }
        });
    }
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
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
  try {
    await waitForFlask(FLASK_URL);
    createWindow();
  } catch (err) {
    console.error(err.message);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (flaskProcess) flaskProcess.kill();
  app.quit();
});

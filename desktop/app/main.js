// Preza desktop shell: starts the bundled backend (the `preza` server, frozen),
// waits until it answers, and shows it in a window. Nothing else lives here —
// the app itself is the web UI the backend serves.
const { app, BrowserWindow, shell, dialog, Menu } = require("electron");
const { spawn } = require("node:child_process");
const net = require("node:net");
const http = require("node:http");
const path = require("node:path");

let backend = null;
let win = null;

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function backendPath() {
  const exe = process.platform === "win32" ? "preza-backend.exe" : "preza-backend";
  return app.isPackaged
    ? path.join(process.resourcesPath, "backend", exe)
    : path.join(__dirname, "..", "build", "dist", "preza-backend", exe);
}

function waitForServer(port, timeoutMs = 90000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const probe = () => {
      const req = http.get({ host: "127.0.0.1", port, path: "/api/system", timeout: 2000 }, (res) => {
        res.resume();
        res.statusCode === 200 ? resolve() : retry();
      });
      req.on("error", retry);
      req.on("timeout", () => req.destroy());
    };
    const retry = () =>
      Date.now() - started > timeoutMs ? reject(new Error("Сервер не запустился")) : setTimeout(probe, 300);
    probe();
  });
}

function stopBackend() {
  if (backend && !backend.killed) backend.kill();
  backend = null;
}

async function start() {
  const splash = new BrowserWindow({
    width: 420,
    height: 300,
    frame: false,
    resizable: false,
    show: false,
    backgroundColor: "#0b0b12",
  });
  splash.loadFile(path.join(__dirname, "splash.html"));
  splash.once("ready-to-show", () => splash.show());

  try {
    const port = await freePort();
    backend = spawn(backendPath(), ["--no-browser", "--host", "127.0.0.1", "--port", String(port)], {
      stdio: "ignore",
      windowsHide: true,
    });
    backend.once("exit", (code) => {
      if (!app.isQuitting && code) dialog.showErrorBox("Preza", `Сервер остановился (код ${code}).`);
    });
    await waitForServer(port);

    win = new BrowserWindow({
      width: 1360,
      height: 880,
      minWidth: 980,
      minHeight: 640,
      title: "Preza",
      backgroundColor: "#0b0b12",
      // A normal title bar: it is what makes the window draggable (a hidden one needs
      // drag regions drawn into the page).
      titleBarStyle: "default",
      show: false,
      webPreferences: { contextIsolation: true, sandbox: true },
    });
    win.once("ready-to-show", () => {
      splash.destroy();
      win.show();
    });
    // Links to other sites open in the browser, never inside the app.
    win.webContents.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url);
      return { action: "deny" };
    });
    win.webContents.on("will-navigate", (event, url) => {
      if (!url.startsWith(`http://127.0.0.1:${port}`)) {
        event.preventDefault();
        shell.openExternal(url);
      }
    });
    await win.loadURL(`http://127.0.0.1:${port}`);
  } catch (error) {
    splash.destroy();
    dialog.showErrorBox("Preza не запустилась", String(error && error.message ? error.message : error));
    app.quit();
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(
      Menu.buildFromTemplate([
        ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
        { role: "editMenu" },
        { role: "viewMenu" },
        { role: "windowMenu" },
      ]),
    );
    start();
  });
  app.on("before-quit", () => {
    app.isQuitting = true;
    stopBackend();
  });
  app.on("window-all-closed", () => app.quit());
}

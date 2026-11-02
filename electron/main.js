const { app, BrowserWindow, clipboard, ClipboardItem, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

const ROOT = path.join(__dirname, "..");

let win = null;
let backend = null;
let nextId = 1;
const pending = new Map();

/**
 * Decide how to start the Python backend.
 * - Installed app: a self-contained executable built by PyInstaller and
 *   shipped in <resources>/backend (no Python needed on the user's machine).
 * - Development: server.py run by the project's .venv (or system) Python.
 */
function resolveBackend() {
  if (app.isPackaged) {
    const exe = process.platform === "win32" ? "data-boss-backend.exe" : "data-boss-backend";
    const dir = path.join(process.resourcesPath, "backend");
    return { command: path.join(dir, exe), args: [], cwd: dir };
  }
  let python = process.env.DATA_BOSS_PYTHON;
  if (!python) {
    const venvPython =
      process.platform === "win32"
        ? path.join(ROOT, ".venv", "Scripts", "python.exe")
        : path.join(ROOT, ".venv", "bin", "python");
    python = fs.existsSync(venvPython)
      ? venvPython
      : process.platform === "win32"
        ? "python"
        : "python3";
  }
  return { command: python, args: [path.join(ROOT, "server.py")], cwd: ROOT };
}

function startBackend() {
  const { command, args, cwd } = resolveBackend();
  backend = spawn(command, args, {
    cwd,
    env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true, // no console window flashing up on Windows
  });

  readline.createInterface({ input: backend.stdout }).on("line", (line) => {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      console.error("[backend] invalid message:", line);
      return;
    }
    const entry = pending.get(msg.id);
    if (!entry) return; // e.g. the initial "ready" message
    pending.delete(msg.id);
    if (msg.ok) entry.resolve(msg.result);
    else entry.reject(new Error(msg.error || "Unknown backend error"));
  });

  backend.stderr.on("data", (chunk) => process.stderr.write(`[backend] ${chunk}`));

  const fail = (reason) => {
    for (const { reject } of pending.values()) reject(new Error(reason));
    pending.clear();
    backend = null;
    if (win && !win.isDestroyed()) win.webContents.send("backend-exit", reason);
  };

  backend.on("error", (err) =>
    fail(`Could not start the data engine (${command}): ${err.message}`)
  );
  backend.on("exit", (code, signal) => {
    if (backend) fail(`Data engine stopped (code ${code}, signal ${signal}).`);
  });
}

function callBackend(cmd, args = {}) {
  if (!backend) return Promise.reject(new Error("Python backend is not running."));
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    backend.stdin.write(JSON.stringify({ id, cmd, args }) + "\n");
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    title: "Data Boss",
    backgroundColor: "#F7F7F8",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.loadFile(path.join(ROOT, "renderer", "index.html"));
}

ipcMain.handle("backend", (_e, cmd, args) => callBackend(cmd, args));

ipcMain.handle("open-csv", async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(win, {
    title: "Open CSV",
    properties: ["openFile"],
    filters: [{ name: "CSV files", extensions: ["csv"] }],
  });
  if (canceled || !filePaths.length) return null;
  return callBackend("load", { path: filePaths[0] });
});

ipcMain.handle("export-csv", async (_e, suggestedName) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: "Export CSV",
    defaultPath: suggestedName || "data.csv",
    filters: [{ name: "CSV files", extensions: ["csv"] }],
  });
  if (canceled || !filePath) return null;
  return callBackend("export", { path: filePath });
});

ipcMain.handle("save-image", async (_e, dataUrl, suggestedName) => {
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: "Save chart",
    defaultPath: suggestedName || "chart.png",
    filters: [{ name: "PNG image", extensions: ["png"] }],
  });
  if (canceled || !filePath) return null;
  const base64 = String(dataUrl).replace(/^data:image\/png;base64,/, "");
  await fs.promises.writeFile(filePath, Buffer.from(base64, "base64"));
  return { path: filePath };
});

// Electron 45+ clipboard is async and W3C-style (ClipboardItem); writeImage no longer exists.
ipcMain.handle("copy-text", async (_e, text) => {
  await clipboard.writeText(String(text));
  return true;
});

ipcMain.handle("copy-image", async (_e, dataUrl) => {
  const match = /^data:image\/png;base64,(.+)$/.exec(String(dataUrl));
  if (!match) throw new Error("Could not read the chart image.");
  const png = Buffer.from(match[1], "base64");
  await clipboard.write([new ClipboardItem({ "image/png": new Blob([png], { type: "image/png" }) })]);
  return true;
});

const TEXT_FILTERS = {
  py: { title: "Save script", filter: { name: "Python script", extensions: ["py"] } },
  svg: { title: "Save chart", filter: { name: "SVG image", extensions: ["svg"] } },
};

ipcMain.handle("save-text", async (_e, text, suggestedName) => {
  const name = suggestedName || "cleaning.py";
  const kind = TEXT_FILTERS[path.extname(name).slice(1).toLowerCase()] || TEXT_FILTERS.py;
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: kind.title,
    defaultPath: name,
    filters: [kind.filter],
  });
  if (canceled || !filePath) return null;
  await fs.promises.writeFile(filePath, String(text), "utf-8");
  return { path: filePath };
});

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("will-quit", () => {
  if (backend) {
    const proc = backend;
    backend = null;
    proc.kill();
  }
});

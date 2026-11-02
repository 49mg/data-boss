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

// Latest request id per tag (e.g. "plot"), so the UI can cancel by tag.
const tagged = new Map();

function callBackend(cmd, args = {}, tag = null) {
  if (!backend) return Promise.reject(new Error("Python backend is not running."));
  const id = nextId++;
  if (tag) tagged.set(tag, id);
  const done = () => {
    if (tag && tagged.get(tag) === id) tagged.delete(tag);
  };
  return new Promise((resolve, reject) => {
    pending.set(id, {
      resolve: (v) => (done(), resolve(v)),
      reject: (e) => (done(), reject(e)),
    });
    backend.stdin.write(JSON.stringify({ id, cmd, args }) + "\n");
  });
}

/** Cancel the in-flight request with this tag. Resolves true if something was cancelled. */
async function cancelTagged(tag) {
  const id = tagged.get(tag);
  if (id === undefined || !backend) return false;
  tagged.delete(tag);
  try {
    const res = await callBackend("cancel", { id });
    return !!res.cancelled;
  } catch {
    return false;
  }
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

ipcMain.handle("backend", (_e, cmd, args, tag) => callBackend(cmd, args, tag || null));
ipcMain.handle("cancel", (_e, tag) => cancelTagged(String(tag)));

const OPEN_FILTERS = [
  { name: "Data files", extensions: ["csv", "tsv", "tab", "txt", "xlsx", "xlsm", "parquet", "pq", "json", "jsonl", "ndjson"] },
  { name: "CSV / TSV", extensions: ["csv", "tsv", "tab", "txt"] },
  { name: "Excel", extensions: ["xlsx", "xlsm"] },
  { name: "Parquet", extensions: ["parquet", "pq"] },
  { name: "JSON", extensions: ["json", "jsonl", "ndjson"] },
];

const EXPORT_FORMATS = {
  csv: { title: "Export CSV", filter: { name: "CSV file", extensions: ["csv"] } },
  xlsx: { title: "Export Excel workbook", filter: { name: "Excel workbook", extensions: ["xlsx"] } },
  parquet: { title: "Export Parquet", filter: { name: "Parquet file", extensions: ["parquet"] } },
};

ipcMain.handle("open-file", async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(win, {
    title: "Open data file",
    properties: ["openFile"],
    filters: OPEN_FILTERS,
  });
  if (canceled || !filePaths.length) return null;
  return callBackend("load", { path: filePaths[0] });
});

ipcMain.handle("export-data", async (_e, suggestedName, format = "csv") => {
  const kind = EXPORT_FORMATS[format] || EXPORT_FORMATS.csv;
  const { canceled, filePath } = await dialog.showSaveDialog(win, {
    title: kind.title,
    defaultPath: suggestedName || `data.${format}`,
    filters: [kind.filter],
  });
  if (canceled || !filePath) return null;
  const ext = `.${kind.filter.extensions[0]}`;
  const target = filePath.toLowerCase().endsWith(ext) ? filePath : filePath + ext;
  return callBackend("export", { path: target });
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

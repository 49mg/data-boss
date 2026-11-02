const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("api", {
  call: (cmd, args, tag) => ipcRenderer.invoke("backend", cmd, args, tag),
  cancel: (tag) => ipcRenderer.invoke("cancel", tag),
  openCsv: () => ipcRenderer.invoke("open-csv"),
  loadPath: (path) => ipcRenderer.invoke("backend", "load", { path }),
  exportCsv: (suggestedName) => ipcRenderer.invoke("export-csv", suggestedName),
  saveImage: (dataUrl, suggestedName) => ipcRenderer.invoke("save-image", dataUrl, suggestedName),
  pathForFile: (file) => webUtils.getPathForFile(file),
  copyText: (text) => ipcRenderer.invoke("copy-text", text),
  copyImage: (dataUrl) => ipcRenderer.invoke("copy-image", dataUrl),
  saveText: (text, suggestedName) => ipcRenderer.invoke("save-text", text, suggestedName),
  onBackendExit: (fn) => ipcRenderer.on("backend-exit", (_e, reason) => fn(reason)),
});

const { contextBridge, ipcRenderer, webUtils } = require("electron");

const locale = ipcRenderer.sendSync("locale-sync");

contextBridge.exposeInMainWorld("locale", locale);
if (locale.collect) contextBridge.exposeInMainWorld("i18nCollect", (strings) => ipcRenderer.send("i18n-collect", strings));

contextBridge.exposeInMainWorld("api", {
  setLanguage: (lang) => ipcRenderer.invoke("set-language", lang),
  call: (cmd, args, tag) => ipcRenderer.invoke("backend", cmd, args, tag),
  cancel: (tag) => ipcRenderer.invoke("cancel", tag),
  openFile: () => ipcRenderer.invoke("open-file"),
  chooseFile: () => ipcRenderer.invoke("choose-file"),
  loadPath: (path, sheet) => ipcRenderer.invoke("backend", "load", sheet ? { path, sheet } : { path }),
  exportData: (suggestedName, format) => ipcRenderer.invoke("export-data", suggestedName, format),
  saveImage: (dataUrl, suggestedName) => ipcRenderer.invoke("save-image", dataUrl, suggestedName),
  pathForFile: (file) => webUtils.getPathForFile(file),
  copyText: (text) => ipcRenderer.invoke("copy-text", text),
  copyImage: (dataUrl) => ipcRenderer.invoke("copy-image", dataUrl),
  saveText: (text, suggestedName) => ipcRenderer.invoke("save-text", text, suggestedName),
  exportReport: (bodyHtml, title, format, testPath) => ipcRenderer.invoke("export-report", bodyHtml, title, format, testPath, locale.lang),
  onBackendExit: (fn) => ipcRenderer.on("backend-exit", (_e, reason) => fn(reason)),
  onUpdateReady: (fn) => ipcRenderer.on("update-ready", (_e, version) => fn(version)),
  installUpdate: () => ipcRenderer.invoke("install-update"),
});

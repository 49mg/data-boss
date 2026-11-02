/* global echarts, tr, i18n */
// Static texts in index.html follow the interface language.
i18n.translateDom(document.body);

"use strict";

const PAGE_SIZE = 100;

const DTYPE_OPTIONS = [
  { value: "int64", label: "Integer (int64)" },
  { value: "float64", label: "Float (float64)" },
  { value: "str", label: "Text (str)" },
  { value: "bool", label: "Boolean (bool)" },
];

const CHART_TYPES = [
  { kind: "HIST", label: "Histogram", icon: "c-hist", hint: "How one numeric column is distributed" },
  { kind: "BOX", label: "Box plot", icon: "c-box", hint: "Compare a numeric column across groups" },
  { kind: "SCAT", label: "Scatter", icon: "c-scatter", hint: "Relationship between two numeric columns" },
  { kind: "BAR", label: "Bar chart", icon: "c-bar", hint: "Sum, mean or median per category" },
  { kind: "COUNT", label: "Count", icon: "c-count", hint: "How often each value appears" },
  { kind: "LINE", label: "Line", icon: "c-line", hint: "Trends over time or an ordered axis" },
  { kind: "HEAT", label: "Correlation", icon: "c-heat", hint: "How every numeric column relates to the others" },
  { kind: "PAIR", label: "Pair plot", icon: "c-pair", hint: "Every pair of numeric columns at once" },
];

const CLEAN_OPS = [
  { group: "Rows", icon: "i-table", items: [
    { key: "REMOVE_DUPLICATES", label: "Remove duplicates", desc: "Drops repeated rows. Match on whole rows, or only on the columns you choose (e.g. the same name)." },
    { key: "DROP_NA_ROWS", label: "Drop rows with gaps", desc: "Removes rows that have missing values, in any column or only in the columns you choose." },
    { key: "FILTER_ROWS", label: "Filter rows", desc: "Keeps or removes rows that match a condition, like score < 10 or name contains “gym”." },
    { key: "SORT_ROWS", label: "Sort rows", desc: "Reorders rows by one column. Missing values go last." },
  ] },
  { group: "Missing values", icon: "i-scan", items: [
    { key: "FILL_NA", label: "Fill missing values", desc: "Fills gaps with the median, mean, most common value, a fixed value, or the neighbouring row's value." },
    { key: "DROP_NA_COLUMNS", label: "Drop empty columns", desc: "Removes columns where every value is missing." },
  ] },
  { group: "Text", icon: "i-file", items: [
    { key: "STRIP_WHITESPACE", label: "Trim spaces", desc: "Removes leading and trailing spaces, so “Basra ” and “Basra” become the same value." },
    { key: "NORMALIZE_TEXT", label: "Normalize text", desc: "Trims, collapses repeated spaces and optionally unifies letter case, so “baghdad” and “Baghdad” group together." },
    { key: "REPLACE_VALUES", label: "Replace values", desc: "Finds an exact value in one column and replaces it. Leave “Replace with” empty to mark those cells as missing." },
  ] },
  { group: "Numbers", icon: "i-chart", items: [
    { key: "CLIP_IQR", label: "Clip outliers (IQR)", desc: "Caps values outside Q1 − 1.5×IQR and Q3 + 1.5×IQR to those limits. Rows are kept." },
    { key: "CLIP_ZSCORE", label: "Clip outliers (z-score)", desc: "Caps values more than 3 standard deviations from the mean. Rows are kept." },
    { key: "ROUND", label: "Round numbers", desc: "Rounds numeric columns to a fixed number of decimal places." },
  ] },
  { group: "Combine", icon: "i-table", items: [
    { key: "JOIN", label: "Join another file", desc: "Adds columns from another file by matching a key, like VLOOKUP in Excel: for example gym_id in both files. The preview shows how many rows match before anything changes." },
  ] },
  { group: "New columns", icon: "i-pivot", items: [
    { key: "ADD_COLUMN", label: "Calculated column", desc: "Computes a new column for every row with an expression, e.g. price / visits, ROUND(price * 1.1, 2), upper(city), or CASE WHEN totalScore >= 4.5 THEN 'top' ELSE 'other' END. Using an existing name replaces that column." },
    { key: "DATE_PARTS", label: "Date parts", desc: "Adds columns such as year, month, weekday or hour from a date column, ready for grouping and charts." },
  ] },
  { group: "Features for modeling", icon: "i-chart", items: [
    { key: "ONE_HOT", label: "One-hot encode", desc: "Turns a category column into 0/1 indicator columns, one per value (plan → plan_basic, plan_pro…), so models that need numbers can use it." },
    { key: "SCALE", label: "Scale numbers", desc: "Puts numeric columns on a common scale: standard (mean 0, standard deviation 1, like scikit-learn's StandardScaler) or min-max (0 to 1)." },
    { key: "BIN", label: "Bin into ranges", desc: "Turns a number into ordered ranges such as 18–30, 30–45: equal width, equal count (quantiles) or your own edges. Each range includes its upper edge." },
    { key: "LOG_TRANSFORM", label: "Log transform", desc: "Compresses long right tails (prices, counts, income) so a few huge values don't dominate charts and models. log(1 + x) also accepts zeros." },
    { key: "GROUP_RARE", label: "Group rare categories", desc: "Merges infrequent values into one label such as “Other”: keep the N most common, or values that make up at least a given share of rows." },
  ] },
  { group: "Types & columns", icon: "i-columns", items: [
    { key: "TO_NUMERIC", label: "Convert to number", desc: "Turns text like “1,200”, “$80” or “15%” into numbers so you can compute and chart them." },
    { key: "TO_DATETIME", label: "Convert to date", desc: "Parses text into real dates for sorting, filtering and time charts." },
    { key: "CHANGE_DTYPE", label: "Change type", desc: "Strict conversion to int, float, text or bool. Fails without changes if any value doesn't fit." },
    { key: "RENAME_COLUMN", label: "Rename column", desc: "Gives a column a new name." },
    { key: "DROP_COLUMNS", label: "Drop columns", desc: "Removes the selected columns." },
  ] },
];
// Older operations that can still appear in history.
const LEGACY_OPS = { FILL_NA_MEAN: "Fill with mean", FILL_NA_MEDIAN: "Fill with median" };

const SECTION_TITLES = {
  data: "Data",
  profile: "Column profile",
  inspect: "Inspect",
  clean: "Clean",
  query: "Query",
  analyze: "Analyze",
  visualize: "Visualize",
  model: "Model",
  dashboard: "Dashboard",
  report: "Report",
};

const app = {
  state: null, // latest snapshot from the backend
  section: "data",
  page: 0,
  inspectKind: "QUALITY",
  cleanMethod: "",
  query: { sql: "", lastSql: "", info: null, infoStale: true, result: null, chart: null },
  script: null,
  inspectParams: {}, // per-view options, e.g. duplicate key columns, correlation method
  inspectStale: true,
  chartKind: "",
  chartImage: null,
  chartCode: "",
  chartParams: {},
  chartStale: false,
  recent: [],
  forms: { clean: {}, chart: {} }, // remembered field values per form
};

const fmt = (n) => Number(n).toLocaleString("en-US");
const pct = (part, whole) => (whole ? (part / whole) * 100 : 0);
const fmtPct = (p) =>
  p === 0 ? "0%" : p < 0.1 ? "<0.1%" : `${p.toFixed(p < 10 ? 1 : 0).replace(/\.0$/, "")}%`;
const plural = (n, word) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;

const $ = (id) => document.getElementById(id);

/* ------------------------------------------------------------------ */
/* backend calls with busy indicator                                    */
/* ------------------------------------------------------------------ */

let busyCount = 0;
let busyTimer = null;

async function withBusy(promise) {
  busyCount++;
  $("busy").hidden = false;
  if (!busyTimer) busyTimer = setTimeout(() => ($("progress").hidden = false), 120);
  try {
    return await promise;
  } finally {
    busyCount--;
    if (busyCount === 0) {
      clearTimeout(busyTimer);
      busyTimer = null;
      $("busy").hidden = true;
      $("progress").hidden = true;
    }
  }
}

const call = (cmd, args) => withBusy(window.api.call(cmd, args));

/**
 * Cancellable background request: cancels the previous in-flight request with
 * the same tag first, then starts a new one. Not wrapped in the busy overlay,
 * so the window stays usable while the backend works.
 */
async function callLatest(tag, cmd, args) {
  await window.api.cancel(tag);
  return window.api.call(cmd, args, tag);
}

const isCancelled = (err) => cleanError(err) === "Cancelled";

/** Shows a Cancel button after a short delay; returns a function that hides it. */
function delayedCancel(container, tag, onCancel, delay = 700) {
  const btn = el("button", { class: "btn btn-sm cancel-btn", type: "button" }, icon("i-x"), "Cancel");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    await window.api.cancel(tag);
    onCancel();
  });
  const timer = setTimeout(() => container.append(btn), delay);
  return () => {
    clearTimeout(timer);
    btn.remove();
  };
}

function cleanError(err) {
  // ipcRenderer.invoke wraps errors as "Error invoking remote method 'x': Error: msg"
  return String(err && err.message ? err.message : err).replace(
    /^Error invoking remote method '[^']+': (Error: )?/,
    ""
  );
}

/* ------------------------------------------------------------------ */
/* small DOM helpers                                                    */
/* ------------------------------------------------------------------ */

/** Create an element. Text, string children and title/placeholder/aria-label go through tr()
 *  (interface language) unless `raw: true` marks the content as data (cells, column names). */
const TRANSLATED_ATTRS = new Set(["title", "placeholder", "aria-label"]);
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  const raw = attrs.raw === true;
  const t = raw ? (v) => v : tr;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false || k === "raw") continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = t(typeof v === "string" ? v : String(v));
    else if (k === "style") node.style.cssText = v; // CSSOM is allowed by the CSP; style="" attributes are not
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : TRANSLATED_ATTRS.has(k) && typeof v === "string" ? t(v) : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    node.append(c instanceof Node ? c : document.createTextNode(t(String(c))));
  }
  return node;
}

function note(kind, text) {
  return el("div", { class: `note ${kind}`, text });
}

function icon(id, cls = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#${id}`);
  svg.append(use);
  return svg;
}

function toast(kind, text) {
  const box = $("toasts");
  const dismiss = () => {
    if (node.classList.contains("leaving")) return;
    node.classList.add("leaving");
    setTimeout(() => node.remove(), 180);
  };
  const node = el(
    "div",
    { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status" },
    el("span", { class: "toast-dot" }),
    el("div", { class: "toast-text", text }),
    el("button", { class: "toast-close", "aria-label": "Dismiss", onclick: dismiss }, icon("i-x"))
  );
  box.append(node);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(dismiss, kind === "error" ? 9000 : 4500);
}

function formatCell(v) {
  if (v === null || v === undefined) return { text: "NaN", cls: "null" };
  if (typeof v === "number") {
    const text = Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(6)));
    return { text, cls: "num" };
  }
  if (typeof v === "boolean") return { text: String(v), cls: "" };
  return { text: String(v), cls: "" };
}

/** Render {columns, index, data} as a table. `types` adds a dtype line under each header. */
function renderTable(container, payload, { showIndex = true, indexLabel = "", types = false, meta: givenMeta = null } = {}) {
  container.replaceChildren();
  if (!payload) return;
  const meta = givenMeta || (types && app.state ? new Map(app.state.columns.map((c) => [c.name, c])) : null);
  const head = el(
    "tr",
    {},
    showIndex ? el("th", { class: "idx", text: indexLabel }) : null,
    payload.columns.map((c) => {
      const m = meta && meta.get(c);
      return el(
        "th",
        { title: c, class: m && m.kind === "numeric" ? "num" : null, raw: true },
        c,
        m ? el("span", { class: "th-type", text: m.dtype, raw: true }) : null
      );
    })
  );
  const body = payload.data.map((row, i) =>
    el(
      "tr",
      {},
      showIndex ? el("td", { class: "idx", text: payload.index[i], raw: true }) : null,
      row.map((v) => {
        const { text, cls } = formatCell(v);
        return el("td", { class: cls, text, title: text, raw: true });
      })
    )
  );
  container.append(el("table", {}, el("thead", {}, head), el("tbody", {}, body)));
}

/* ------------------------------------------------------------------ */
/* generic form builder                                                 */
/* ------------------------------------------------------------------ */

/**
 * specs: [{ key, label, type: "select" | "multi" | "text", options, default }]
 * options: array of strings or {value, label}
 * memory:  object that keeps the user's values across rebuilds
 */
const hint = (spec) => (spec.hint ? el("small", { class: "field-hint", text: spec.hint }) : null);

function buildForm(container, specs, memory, onChange) {
  container.replaceChildren();
  const values = {};

  for (const spec of specs) {
    const options = (spec.options || []).map((o) =>
      typeof o === "string" ? { value: o, label: o } : o
    );
    const valid = new Set(options.map((o) => o.value));
    const remembered = memory[spec.key];

    if (spec.type === "select") {
      let value = remembered !== undefined && valid.has(remembered) ? remembered : spec.default;
      if (!valid.has(value)) value = options.length ? options[0].value : "";
      values[spec.key] = value;
      const select = el(
        "select",
        {
          onchange: (e) => {
            values[spec.key] = memory[spec.key] = e.target.value;
            onChange(values, spec.key);
          },
        },
        options.map((o) => el("option", { value: o.value, text: o.label }))
      );
      select.value = value;
      container.append(el("label", { class: "field" }, el("span", { text: spec.label }), select, hint(spec)));
    } else if (spec.type === "multi") {
      const initial = Array.isArray(remembered) ? remembered : spec.default || [];
      const selected = new Set(initial.filter((v) => valid.has(v)));
      values[spec.key] = options.map((o) => o.value).filter((v) => selected.has(v));
      const update = () => {
        values[spec.key] = memory[spec.key] = options
          .map((o) => o.value)
          .filter((v) => selected.has(v));
        onChange(values, spec.key);
      };
      const list = el(
        "div",
        { class: "checklist" },
        options.map((o) => {
          const box = el("input", {
            type: "checkbox",
            checked: selected.has(o.value),
            onchange: (e) => {
              if (e.target.checked) selected.add(o.value);
              else selected.delete(o.value);
              update();
            },
          });
          return el("label", {}, box, o.label);
        })
      );
      if (!options.length) list.replaceChildren(el("div", { class: "checklist-empty", text: "No matching columns." }));
      container.append(el("div", { class: "field" }, el("span", { text: spec.label }), list, hint(spec)));
      // Bring the first pre-ticked option into view (e.g. a column chosen from Inspect).
      requestAnimationFrame(() => {
        const first = list.querySelector("input:checked");
        if (first) list.scrollTop = first.parentElement.offsetTop - list.clientHeight / 2;
      });
    } else if (spec.type === "toggle") {
      const value = typeof remembered === "boolean" ? remembered : !!spec.default;
      values[spec.key] = value;
      const input = el("input", {
        type: "checkbox",
        role: "switch",
        checked: value,
        onchange: (e) => {
          values[spec.key] = memory[spec.key] = e.target.checked;
          onChange(values, spec.key);
        },
      });
      container.append(el("label", { class: "field field-toggle" }, input, el("span", { class: "switch", "aria-hidden": "true" }),
        el("span", { class: "toggle-label", text: spec.label }), hint(spec)));
    } else {
      const value = typeof remembered === "string" ? remembered : spec.default || "";
      values[spec.key] = value;
      const input = el("input", {
        type: "text",
        "data-key": spec.key,
        value,
        oninput: (e) => {
          values[spec.key] = memory[spec.key] = e.target.value;
          onChange(values, spec.key);
        },
      });
      container.append(el("label", { class: "field" }, el("span", { text: spec.label }), input, hint(spec)));
    }
  }
  return values;
}

/* ------------------------------------------------------------------ */
/* column helpers                                                       */
/* ------------------------------------------------------------------ */

const allCols = () => app.state.columns.map((c) => c.name);
const numericCols = () => app.state.columns.filter((c) => c.kind === "numeric").map((c) => c.name);
const categoricalCols = () =>
  app.state.columns.filter((c) => c.kind === "categorical").map((c) => c.name);
const missingOf = (name) => {
  const col = app.state.columns.find((c) => c.name === name);
  return col ? col.missing : 0;
};

/* ------------------------------------------------------------------ */
/* state + navigation                                                   */
/* ------------------------------------------------------------------ */

function setState(snapshot) {
  app.state = snapshot;
  const [rows, cols] = snapshot.shape;
  $("file-chip").hidden = false;
  $("topbar-title").hidden = true;
  $("file-name").textContent = snapshot.fileName;
  $("file-name").title = snapshot.path || "";
  $("file-meta").textContent = tr(`${plural(rows, "row")} · ${plural(cols, "column")}`);
  const ops = snapshot.log.length;
  $("nav-clean-badge").hidden = ops === 0;
  $("nav-clean-badge").textContent = ops;
  $("btn-export").disabled = false;
  $("btn-undo").disabled = !snapshot.canUndo;
  $("btn-undo-2").disabled = !snapshot.canUndo;
  $("empty").hidden = true;
  for (const btn of document.querySelectorAll("#nav .nav-item")) btn.disabled = false;

  const maxPage = Math.max(0, Math.ceil(rows / PAGE_SIZE) - 1);
  if (app.page > maxPage) app.page = maxPage;

  renderStats();
  renderSourceInfo();
  renderProfile();
  renderCleanFields();
  renderHistory();
  renderPreview();
  renderChartFields();
  app.inspectStale = true; // refreshed when the Inspect screen is shown
  app.query.infoStale = true;
  testGroupCache.clear();
  app.dashStale = true; // redrawn now if visible, otherwise when the Dashboard is opened
  const tab = app.section === "analyze" ? app.analyzeTab || "pivot" : null;
  if (tab === "pivot") renderPivotFields();
  else app.pivotStale = true;
  if (tab === "tests") renderTestFields(true);
  else app.testStale = true;
  if (tab === "trends") renderTrendFields(true);
  else app.trendStale = true;
  if (tab === "segment") renderSegmentFields(true);
  else app.segmentStale = true;
  showSection(app.section);
}

function stat(label, value, sub, subCls, meter) {
  return el(
    "div",
    { class: "stat" },
    el("div", { class: "stat-label", text: label }),
    el("div", { class: "stat-value", text: value }),
    sub ? el("div", { class: `stat-sub ${subCls || ""}`, text: sub }) : null,
    meter !== undefined
      ? el("div", { class: "stat-meter" }, el("span", { style: `width:${Math.min(100, meter)}%` }))
      : null
  );
}

function renderStats() {
  const s = app.state;
  const [rows, cols] = s.shape;
  const cells = rows * cols;
  const missingPct = pct(s.missingCells, cells);
  const dupPct = pct(s.duplicateRows, rows);
  const num = s.columns.filter((c) => c.kind === "numeric").length;
  const cat = s.columns.filter((c) => c.kind === "categorical").length;
  const gappy = s.columns.filter((c) => c.missing > 0).length;
  $("stats").replaceChildren(
    stat("Rows", fmt(rows), plural(cells, "cell")),
    stat("Columns", fmt(cols), `${num} numeric · ${cat} text`),
    stat(
      "Missing cells",
      fmt(s.missingCells),
      s.missingCells ? `${fmtPct(missingPct)} of cells · ${gappy} column${gappy === 1 ? "" : "s"}` : "Complete",
      s.missingCells ? "warn" : "good",
      s.missingCells ? missingPct : undefined
    ),
    stat(
      "Duplicate rows",
      fmt(s.duplicateRows),
      s.duplicateRows ? `${fmtPct(dupPct)} of rows` : "None found",
      s.duplicateRows ? "warn" : "good"
    ),
    stat("Cleaning steps", fmt(s.log.length), s.log.length ? "Undo available" : "Original data")
  );
}

function showSection(name) {
  app.section = name;
  for (const btn of document.querySelectorAll("#nav .nav-item")) {
    btn.classList.toggle("active", btn.dataset.section === name);
  }
  for (const sec of document.querySelectorAll(".section")) {
    sec.hidden = !app.state || sec.id !== `section-${name}`;
  }
  document.title = app.state ? `${SECTION_TITLES[name]} · ${app.state.fileName} — Data Boss` : "Data Boss";
  if (app.state && name === "data") loadPage();
  if (app.state && name === "inspect" && app.inspectStale) renderInspect();
  if (app.state && name === "visualize" && app.chartKind && app.chartStale) scheduleRender(0);
  if (app.state && name === "report") renderReport();
  if (app.state && name === "dashboard" && app.dashStale !== false) renderDashboard();
  if (app.state && name === "model") selectModelTab(app.modelTab || "predict");
  if (app.state && name === "query" && app.query.infoStale) loadQueryInfo();
  if (app.state && name === "analyze") {
    if (app.analyzeTab === "tests") app.testStale !== false && renderTestFields(true);
    else if (app.analyzeTab === "trends") app.trendStale !== false && renderTrendFields(true);
    else if (app.analyzeTab === "segment") app.segmentStale !== false && renderSegmentFields(true);
    else if (app.pivotStale) renderPivotFields(true);
  }
}

async function loadPage() {
  try {
    const res = await call("rows", { offset: app.page * PAGE_SIZE, limit: PAGE_SIZE });
    renderTable($("data-table"), res.table, { types: true });
    const start = res.total === 0 ? 0 : res.offset + 1;
    const end = Math.min(res.offset + PAGE_SIZE, res.total);
    $("page-label").textContent = trf("{0}–{1} of {2}", fmt(start), fmt(end), fmt(res.total));
    $("page-prev").disabled = app.page === 0;
    $("page-next").disabled = end >= res.total;
  } catch (err) {
    toast("error", cleanError(err));
  }
}

/* ------------------------------------------------------------------ */
/* file handling                                                        */
/* ------------------------------------------------------------------ */

function onLoaded(snapshot) {
  if (!snapshot) return; // dialog cancelled
  app.page = 0;
  app.forms = { clean: {}, chart: {} };
  app.chartImage = null;
  if (typeof disposeEchart === "function") disposeEchart();
  app.recent = [];
  app.pivot = null;
  app.pivotStale = true;
  app.test = null;
  app.testStale = true;
  app.trend = null;
  app.trendStale = true;
  app.segment = null;
  app.segmentStale = true;
  app.model = null;
  $("model-output").replaceChildren();
  $("model-actions").hidden = true;
  app.clusters = null;
  $("cluster-output").replaceChildren();
  $("cluster-actions").hidden = true;
  app.forecast = null;
  $("forecast-output").replaceChildren();
  $("forecast-actions").hidden = true;
  $("segment-output").replaceChildren();
  $("trend-output").replaceChildren();
  $("test-output").replaceChildren();
  $("pivot-chart-card").hidden = true;
  app.query = { sql: $("sql-editor").value, lastSql: "", info: null, infoStale: true, result: null, chart: null };
  $("query-result-card").hidden = true;
  $("query-chart-card").hidden = true;
  renderRecent();
  app.cleanMethod = "";
  renderOpList();
  app.chartKind = "";
  app.inspectKind = "QUALITY";
  app.inspectParams = {};
  app.forms.dupes = {};
  $("inspect-output").replaceChildren();
  syncInspectTabs();
  renderChartTiles();
  setState(snapshot);
  toast("success", `Loaded ${snapshot.fileName}`);
}

const OPENABLE = [".csv", ".tsv", ".tab", ".txt", ".xlsx", ".xlsm", ".parquet", ".pq", ".json", ".jsonl", ".ndjson"];

/** Ask which sheet to open; resolves to the sheet name or null if cancelled. */
function pickSheet(sheets, fileName) {
  return new Promise((resolve) => {
    const dlg = $("sheet-dialog");
    $("sheet-sub").textContent = tr(`${fileName} has ${sheets.length} sheets. Which one do you want to open?`);
    let chosen = null;
    $("sheet-list").replaceChildren(
      ...sheets.map((name) =>
        el("button", { onclick: () => { chosen = name; dlg.close(); } }, icon("i-table"), el("span", { text: name })))
    );
    dlg.addEventListener("close", () => resolve(chosen), { once: true });
    dlg.showModal();
  });
}

/** Handle a load result, asking for a sheet when an Excel file has several. */
async function handleLoadResult(res) {
  if (!res) return; // dialog cancelled
  if (res.needsSheet) {
    const sheet = await pickSheet(res.sheets, res.path.split(/[\\/]/).pop());
    if (!sheet) return;
    res = await withBusy(window.api.loadPath(res.path, sheet));
  }
  onLoaded(res);
}

async function openFile() {
  try {
    await handleLoadResult(await withBusy(window.api.openFile()));
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function loadDroppedFile(file) {
  const name = file.name.toLowerCase();
  if (!OPENABLE.some((ext) => name.endsWith(ext))) {
    toast("error", name.endsWith(".xls")
      ? "Old Excel .xls files are not supported. Save it as .xlsx and drop that."
      : "Drop a CSV, Excel (.xlsx), Parquet or JSON file.");
    return;
  }
  try {
    await handleLoadResult(await withBusy(window.api.loadPath(window.api.pathForFile(file))));
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function exportData(format = "csv") {
  $("export-menu").hidden = true;
  $("btn-export").setAttribute("aria-expanded", "false");
  try {
    const base = (app.state.fileName || "data").replace(/\.[^.]+$/, "");
    const res = await withBusy(window.api.exportData(`${base}_cleaned.${format}`, format));
    if (res) toast("success", `Saved ${res.path}`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function toggleExportMenu(force) {
  const menu = $("export-menu");
  const open = force ?? menu.hidden;
  menu.hidden = !open;
  $("btn-export").setAttribute("aria-expanded", String(open));
  if (open) menu.querySelector("button").focus();
}

/* ---- import details and settings ---------------------------------------- */

const SEPARATOR_LABELS = { ",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe" };
const ENCODING_LABELS = { "utf-8-sig": "UTF-8", "utf-8": "UTF-8", cp1256: "Arabic (Windows-1256)", "latin-1": "Western (Latin-1)" };
const FORMAT_LABELS = { csv: "CSV", excel: "Excel", parquet: "Parquet", json: "JSON", jsonl: "JSON Lines" };

function renderSourceInfo() {
  const src = app.state.source || {};
  const box = $("source-info");
  if (!src.format) return box.replaceChildren();
  const chipsList = [FORMAT_LABELS[src.format] || src.format];
  if (src.format === "csv") {
    chipsList.push(`${SEPARATOR_LABELS[src.sep] || src.sep} separated`, ENCODING_LABELS[src.encoding] || src.encoding);
    if (src.header === false) chipsList.push("no header row");
  }
  if (src.format === "excel" && src.sheet) chipsList.push(`sheet “${src.sheet}”`);
  const canConfigure = src.format === "csv" || (src.format === "excel" && (src.sheets || []).length > 1);
  box.replaceChildren(
    ...[
      ...chipsList.map((t) => el("span", { class: "chip", text: t })),
      canConfigure ? el("button", { class: "btn btn-sm btn-ghost", onclick: openImportSettings }, "Import settings…") : null,
      src.notes && src.notes.length ? el("div", { class: "source-notes" }, src.notes.map((n) => el("p", { text: n }))) : null,
    ].filter(Boolean)
  );
}

let importValues = {};

function openImportSettings() {
  const src = app.state.source || {};
  const memory = {};
  let specs;
  if (src.format === "excel") {
    memory.sheet = src.sheet || (src.sheets || [])[0];
    specs = [{ key: "sheet", label: "Sheet", type: "select", options: src.sheets || [] }];
  } else {
    memory.sep = src.sep;
    memory.encoding = src.encoding === "utf-8" ? "utf-8-sig" : src.encoding;
    memory.header = src.header !== false;
    specs = [
      { key: "sep", label: "Column separator", type: "select", options: toOptions([[",", "Comma ( , )"], [";", "Semicolon ( ; )"], ["\t", "Tab"], ["|", "Pipe ( | )"]]) },
      { key: "encoding", label: "Text encoding", type: "select",
        options: toOptions([["utf-8-sig", "UTF-8 (most files)"], ["cp1256", "Arabic (Windows-1256)"], ["latin-1", "Western (Latin-1)"]]),
        hint: "If Arabic text looks garbled, try Windows-1256." },
      TOGGLE("header", "First row has column names", true),
    ];
  }
  importValues = buildForm($("import-fields"), specs, memory, (v) => (importValues = v));
  $("import-dialog").showModal();
}

async function applyImportSettings() {
  const src = app.state.source || {};
  const args = src.format === "excel" ? { sheet: importValues.sheet } : { options: { ...importValues } };
  try {
    const res = await withBusy(window.api.call("reload", args));
    $("import-dialog").close();
    onLoaded(res);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

/* ------------------------------------------------------------------ */
/* profile                                                              */
/* ------------------------------------------------------------------ */

function renderProfile() {
  const profile = app.state.profile;
  const idx = (name) => profile.columns.indexOf(name);
  const [iCol, iNonNull, iUnique, iRange] = ["Column", "Non-null", "Unique", "Top values / Range"].map(idx);
  const rows = app.state.shape[0];
  const meta = new Map(app.state.columns.map((c) => [c.name, c]));

  const head = el(
    "tr",
    {},
    ["Column", "Type", "Missing", "Non-null", "Unique", "Top values / range"].map((h, i) =>
      el("th", { text: h, class: i === 3 || i === 4 ? "num" : null })
    )
  );
  const body = profile.data.map((r) => {
    const name = String(r[iCol]);
    const m = meta.get(name) || { dtype: "", kind: "other", missing: 0 };
    const p = pct(m.missing, rows);
    return el(
      "tr",
      {},
      el("td", { class: "col-name", text: name, title: name }),
      el("td", {}, el("span", { class: `type-badge ${m.kind}`, text: m.dtype })),
      el(
        "td",
        {},
        el(
          "div",
          { class: `miss ${m.missing ? "" : "none"}` },
          el("div", { class: "miss-bar" }, el("span", { style: m.missing ? `width:${Math.max(2, p)}%` : null })),
          m.missing ? `${fmt(m.missing)} · ${fmtPct(p)}` : "None"
        )
      ),
      el("td", { class: "num", text: fmt(r[iNonNull]) }),
      el("td", { class: "num", text: fmt(r[iUnique]) }),
      el("td", { class: "range", text: r[iRange], title: r[iRange] })
    );
  });
  $("profile-table").replaceChildren(el("table", {}, el("thead", {}, head), el("tbody", {}, body)));

  const select = $("vc-column");
  const prev = select.value;
  select.replaceChildren(...allCols().map((c) => el("option", { value: c, text: c })));
  if (allCols().includes(prev)) select.value = prev;
  renderValueCounts();
}

async function renderValueCounts() {
  const column = $("vc-column").value;
  const box = $("vc-table");
  if (!column) return box.replaceChildren();
  try {
    const res = await call("value_counts", { column });
    const data = res.table.data;
    const max = Math.max(1, ...data.map((r) => r[1]));
    box.replaceChildren(
      ...data.map(([value, count]) => {
        const isNull = value === null || value === undefined;
        const text = isNull ? "NaN" : String(value);
        return el(
          "div",
          { class: "vc-row", title: `${text}: ${fmt(count)}` },
          el("div", { class: "vc-fill", style: `width:${(count / max) * 100}%` }),
          el("span", { class: `vc-value ${isNull ? "null" : ""}`, text }),
          el("span", { class: "vc-count", text: fmt(count) })
        );
      })
    );
  } catch (err) {
    toast("error", cleanError(err));
  }
}

/* ------------------------------------------------------------------ */
/* inspect                                                              */
/* ------------------------------------------------------------------ */

function syncInspectTabs() {
  for (const tab of document.querySelectorAll("#inspect-tabs button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.kind === app.inspectKind));
  }
}

/* formatting helpers for inspect views */
const fnum = (v) => {
  if (v === null || v === undefined) return "—";
  if (v !== 0 && (Math.abs(v) >= 1e9 || Math.abs(v) < 1e-4)) return v.toExponential(2);
  return Number(v.toPrecision(4)).toLocaleString("en-US", { maximumFractionDigits: 4 });
};
const fbytes = (b) =>
  b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`;
const sevLabel = { critical: "Critical", warning: "Warning", info: "Note" };

function card(title, ...children) {
  return el("div", { class: "card" }, title ? el("h2", { text: title }) : null, ...children);
}
function chips(cols, cls = "chip") {
  return el("div", { class: "chips" }, cols.map((c) => el("span", { class: cls, text: c })));
}
function bar(fraction, cls = "") {
  return el(
    "div",
    { class: `bar ${cls}` },
    el("span", { style: `width:${Math.max(fraction > 0 ? 2 : 0, Math.min(100, fraction * 100))}%` })
  );
}
function fixButton(action, extraCls = "") {
  if (!action) return null;
  return el(
    "button",
    { class: `btn btn-sm ${extraCls}`, onclick: () => openFix(action) },
    icon("i-clean"),
    action.label || "Fix in Clean"
  );
}

/** Jump to Clean with an operation and its inputs filled in, ready to Apply. */
function openFix(action) {
  app.forms.clean[action.method] = { ...(action.params || {}) };
  app.cleanMethod = action.method;
  showSection("clean");
  renderOpList();
  renderCleanFields();
  $("content").scrollTop = 0;
  toast("success", "Operation prepared. Review it, then click Apply.");
}

/* ---- Overview ---------------------------------------------------------- */
function viewQuality(res) {
  const s = res.summary;
  const tiles = el(
    "div",
    { class: "stats" },
    stat("Completeness", s.completeness == null ? "—" : fmtPct(s.completeness * 100), "Share of filled cells",
      s.completeness < 0.95 ? "warn" : "good", s.completeness * 100),
    stat("Row uniqueness", s.uniqueness == null ? "—" : fmtPct(s.uniqueness * 100), "Rows that are not exact copies",
      s.uniqueness < 1 ? "warn" : "good"),
    el(
      "div",
      { class: "stat" },
      el("div", { class: "stat-label", text: "Checks flagged" }),
      el("div", { class: "stat-value", text: fmt(res.issues.length) }),
      el(
        "div",
        { class: "sev-counts" },
        ["critical", "warning", "info"].map((k) =>
          el("span", { class: `sev-count ${k}` }, el("i"), `${s[k]} ${sevLabel[k].toLowerCase()}`)
        )
      )
    )
  );
  if (!res.issues.length) {
    return el("div", {}, tiles, el("div", { class: "note success", text: "No problems found. This dataset passed every check." }));
  }
  const list = el(
    "div",
    { class: "issues" },
    res.issues.map((i) =>
      el(
        "div",
        { class: `issue ${i.severity}` },
        el("span", { class: `sev-pill ${i.severity}`, text: sevLabel[i.severity] }),
        el(
          "div",
          { class: "issue-body" },
          el("div", { class: "issue-title", text: i.title }),
          el("p", { class: "issue-detail", text: i.detail }),
          i.columns.length > 1 ? chips(i.columns) : null
        ),
        fixButton(i.action)
      )
    )
  );
  return el("div", {}, tiles, list);
}

/* ---- Structure --------------------------------------------------------- */
function viewStructure(res) {
  const head = el(
    "div",
    { class: "chips summary-chips" },
    el("span", { class: "chip", text: `${plural(res.rows, "row")}` }),
    el("span", { class: "chip", text: `${plural(res.columns.length, "column")}` }),
    el("span", { class: "chip", text: `${fbytes(res.memory)} in memory` }),
    res.dtypes.map((d) => el("span", { class: "chip mono", text: `${d.dtype} × ${d.count}` }))
  );
  const rows = res.columns.map((c) =>
    el(
      "tr",
      {},
      el("td", { class: "idx", text: c.position }),
      el("td", { class: "col-name", text: c.name, title: c.name }),
      el("td", {}, el("span", { class: `type-badge ${c.kind}`, text: c.dtype })),
      el("td", { class: "num", text: fmt(c.nonNull) }),
      el("td", { class: `num ${c.missing ? "warn-text" : "muted"}`, text: fmt(c.missing) }),
      el("td", { class: "num", text: fmt(c.unique) }),
      el("td", { class: "num muted", text: fbytes(c.memory) }),
      el("td", { class: "samples" }, c.samples.map((v) => el("span", { class: "sample", text: v, title: v })))
    )
  );
  const tbl = el(
    "div",
    { class: "card card-flush" },
    el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        {},
        el("thead", {}, el("tr", {},
          ["#", "Column", "Type", "Non-null", "Missing", "Unique", "Memory", "Sample values"].map((h, i) =>
            el("th", { text: h, class: i === 0 ? "idx" : i >= 3 && i <= 6 ? "num" : null })))),
        el("tbody", {}, rows)
      )
    )
  );
  const raw = el(
    "details",
    { class: "card raw" },
    el("summary", { text: "Raw pandas info() output" }),
    el("pre", { class: "info", text: res.raw })
  );
  return el("div", {}, head, tbl, raw);
}

/* ---- Statistics -------------------------------------------------------- */
function histogram(h) {
  const max = Math.max(1, ...h.counts);
  return el(
    "div",
    { class: "hist-wrap" },
    el("div", { class: "hist" },
      h.counts.map((c) => el("span", { style: `height:${c ? Math.max(4, (c / max) * 100) : 0}%`, title: fmt(c) }))),
    el("div", { class: "hist-axis" }, el("span", { text: fnum(h.min) }), el("span", { text: fnum(h.max) }))
  );
}
function kv(pairs) {
  return el("dl", { class: "kv" }, pairs.flatMap(([k, v, cls]) => [el("dt", { text: k }), el("dd", { class: cls || "", text: v })]));
}
function viewStats(res) {
  const out = el("div", {});
  if (res.numeric.length) {
    out.append(el("h3", { class: "group-title", text: `Numeric columns · ${res.numeric.length}` }));
    out.append(
      el("div", { class: "stat-cards" },
        res.numeric.map((c) =>
          el(
            "div",
            { class: "col-card" },
            el("div", { class: "col-card-head" },
              el("span", { class: "col-name", text: c.name, title: c.name }),
              el("span", { class: "type-badge numeric", text: c.dtype })),
            c.hist ? histogram(c.hist) : el("div", { class: "hist-empty", text: "No values" }),
            kv([
              ["Mean", fnum(c.mean)], ["Median", fnum(c.median)],
              ["Std dev", fnum(c.std)], ["Skew", fnum(c.skew), c.skew != null && Math.abs(c.skew) >= 2 ? "warn-text" : ""],
              ["Min", fnum(c.min)], ["Max", fnum(c.max)],
              ["Zeros", fmt(c.zeros ?? 0)], ["Missing", fmt(c.missing), c.missing ? "warn-text" : ""],
            ])
          )
        ))
    );
  }
  if (res.categorical.length) {
    out.append(el("h3", { class: "group-title", text: `Text & category columns · ${res.categorical.length}` }));
    out.append(
      el("div", { class: "stat-cards" },
        res.categorical.map((c) => {
          const max = Math.max(1, ...c.top.map((t) => t.count));
          return el(
            "div",
            { class: "col-card" },
            el("div", { class: "col-card-head" },
              el("span", { class: "col-name", text: c.name, title: c.name }),
              el("span", { class: "type-badge categorical", text: c.dtype })),
            el("div", { class: "top-list" },
              c.top.length
                ? c.top.map((t) =>
                    el("div", { class: "vc-row", title: `${t.value}: ${fmt(t.count)}` },
                      el("div", { class: "vc-fill", style: `width:${(t.count / max) * 100}%` }),
                      el("span", { class: "vc-value", text: t.value }),
                      el("span", { class: "vc-count", text: fmt(t.count) })))
                : el("div", { class: "hist-empty", text: "No values" })),
            kv([
              ["Unique", fmt(c.unique)], ["Missing", fmt(c.missing), c.missing ? "warn-text" : ""],
              ["Filled", fmt(c.count)], ["Avg length", c.avgLength == null ? "—" : c.avgLength.toFixed(1)],
            ])
          );
        }))
    );
  }
  return out;
}

/* ---- Missing ----------------------------------------------------------- */
function viewMissing(res) {
  const cells = res.rows * res.columns.length;
  const gappy = res.columns.filter((c) => c.missing > 0);
  const tiles = el(
    "div",
    { class: "stats" },
    stat("Missing cells", fmt(res.cells), `${fmtPct(pct(res.cells, cells))} of all cells`, res.cells ? "warn" : "good"),
    stat("Complete rows", fmt(res.completeRows), `${fmtPct(pct(res.completeRows, res.rows))} have no gaps`,
      res.completeRows === res.rows ? "good" : "", pct(res.completeRows, res.rows)),
    stat("Columns with gaps", `${gappy.length} / ${res.columns.length}`,
      gappy.length ? `${res.columns.length - gappy.length} complete` : "All complete", gappy.length ? "warn" : "good")
  );
  if (!gappy.length) return el("div", {}, tiles, el("div", { class: "note success", text: "No missing values in this dataset." }));

  const byCol = card(
    "By column",
    el("div", { class: "bar-list" },
      gappy.map((c) =>
        el("div", { class: "bar-row" },
          el("span", { class: "bar-label", text: c.name, title: c.name }),
          bar(c.pct, c.pct >= 0.5 ? "danger" : "warn"),
          el("span", { class: "bar-value", text: `${fmt(c.missing)} · ${fmtPct(c.pct * 100)}` }))))
  );
  const maxRows = Math.max(1, ...res.patterns.map((p) => p.rows));
  const patterns = card(
    "Common patterns",
    el("p", { class: "card-hint", text: "Which columns tend to be missing together, by number of rows." }),
    el("div", { class: "patterns" },
      res.patterns.map((p) =>
        el("div", { class: "pattern" },
          el("div", { class: "pattern-head" },
            chips(p.columns),
            el("span", { class: "bar-value", text: plural(p.rows, "row") })),
          bar(p.rows / maxRows))))
  );
  return el("div", {}, tiles, el("div", { class: "grid-2" }, byCol, patterns));
}

/* ---- Duplicates -------------------------------------------------------- */
function viewDupes(res) {
  const memory = (app.forms.dupes ||= {});
  const controls = el("div", { class: "card" });
  const fields = el("div", { class: "fields" });
  let picked = [];
  const values = buildForm(
    fields,
    [{ key: "columns", label: "Compare rows on these columns", type: "multi", options: allCols(), default: res.subset || [] }],
    memory,
    (v) => (picked = v.columns)
  );
  picked = values.columns;
  controls.append(
    el("h2", { text: "Match on" }),
    el("p", { class: "card-hint", text: "Leave everything unticked to find whole-row copies. Tick columns (e.g. a name) to find rows that repeat those values." }),
    fields,
    el("div", { class: "row" },
      el("button", { class: "btn btn-primary", onclick: () => { app.inspectParams.DUPES = { columns: picked }; renderInspect(); } },
        icon("i-scan"), "Check duplicates"),
      res.subset ? el("button", { class: "btn", onclick: () => { memory.columns = []; app.inspectParams.DUPES = {}; renderInspect(); } }, "Whole rows") : null)
  );
  const scope = res.subset ? `matching on ${res.subset.join(", ")}` : "whole-row copies";
  const tiles = el(
    "div",
    { class: "stats" },
    stat("Duplicate rows", fmt(res.extraRows), `Extra copies (${scope})`, res.extraRows ? "warn" : "good"),
    stat("Rows involved", fmt(res.involvedRows), "Originals plus copies"),
    stat("Duplicate groups", fmt(res.groups), "Distinct repeated values")
  );
  const out = el("div", {}, controls, tiles);
  if (!res.extraRows) {
    out.append(el("div", { class: "note success", text: `No duplicates found (${scope}).` }));
    return out;
  }
  const wrap = el("div", { class: "table-wrap" });
  renderTable(wrap, res.table, { types: true, indexLabel: "Row" });
  out.append(
    el("div", { class: "card card-flush" },
      el("div", { class: "card-head" },
        el("h2", { text: res.truncated ? "Duplicated rows (first 200)" : "Duplicated rows" }),
        res.subset ? null : fixButton({ method: "REMOVE_DUPLICATES", label: "Remove duplicates" })),
      wrap)
  );
  return out;
}

/* ---- Outliers ---------------------------------------------------------- */
function viewOutliers(res) {
  if (!res.columns.length) return el("div", { class: "note info", text: "No numeric columns with enough values to check." });
  const flagged = res.columns.filter((c) => c.below + c.above > 0);
  const rows = res.columns.map((c) =>
    el(
      "tr",
      {},
      el("td", { class: "col-name", text: c.name }),
      el("td", { class: "num mono", text: `${fnum(c.lower)} … ${fnum(c.upper)}` }),
      el("td", { class: "num mono muted", text: `${fnum(c.min)} … ${fnum(c.max)}` }),
      el("td", { class: `num ${c.below ? "warn-text" : "muted"}`, text: fmt(c.below) }),
      el("td", { class: `num ${c.above ? "warn-text" : "muted"}`, text: fmt(c.above) }),
      el("td", {}, el("div", { class: "bar-cell" }, bar(c.pct, "warn"), el("span", { text: fmtPct(c.pct * 100) }))),
      el("td", { class: "num", text: fmt(c.zscore) }),
      el("td", { class: "mono muted", text: c.examples.map(fnum).join(", ") || "—" })
    )
  );
  const headers = ["Column", "Normal range (IQR)", "Actual range", "Below", "Above", "Share", "|z| > 3", "Most extreme"];
  return el(
    "div",
    {},
    el("div", { class: "note info",
      text: "IQR rule: values below Q1 − 1.5×IQR or above Q3 + 1.5×IQR. The z-score column counts values more than 3 standard deviations from the mean. Outliers are not always errors; check them before clipping." }),
    el("div", { class: "card card-flush" },
      el("div", { class: "card-head" },
        el("h2", { text: flagged.length ? `${flagged.length} of ${res.columns.length} columns have outliers` : "No outliers found" }),
        flagged.length ? fixButton({ method: "CLIP_IQR", label: "Clip with IQR" }) : null),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {}, headers.map((h, i) => el("th", { text: h, class: [1, 2, 3, 4, 6].includes(i) ? "num" : null })))),
          el("tbody", {}, rows))))
  );
}

/* ---- Correlations ------------------------------------------------------ */
function strength(r) {
  const a = Math.abs(r);
  return a >= 0.8 ? "Very strong" : a >= 0.6 ? "Strong" : a >= 0.4 ? "Moderate" : a >= 0.2 ? "Weak" : "Negligible";
}
function viewCorr(res) {
  const method = res.method;
  const switcher = el(
    "div",
    { class: "segmented segmented-sm" },
    [["pearson", "Pearson (linear)"], ["spearman", "Spearman (rank)"]].map(([m, label]) =>
      el("button", {
        "aria-selected": String(m === method),
        onclick: () => { app.inspectParams.CORR = { method: m }; renderInspect(); },
      }, label))
  );
  const toolbar = el(
    "div",
    { class: "toolbar" },
    switcher,
    el("button", { class: "btn btn-sm", onclick: () => { showSection("visualize"); selectChart("HEAT"); } },
      icon("c-heat"), "Open heatmap")
  );
  if (res.columns < 2) return el("div", {}, toolbar, el("div", { class: "note info", text: "Need at least two numeric columns." }));
  const rows = res.pairs.map((p) =>
    el(
      "div",
      { class: "corr-row" },
      el("div", { class: "corr-pair" },
        el("span", { text: p.a, title: p.a }), el("span", { class: "muted", text: "↔" }), el("span", { text: p.b, title: p.b })),
      el("div", { class: "corr-bar" },
        el("span", { class: p.r < 0 ? "neg" : "pos", style: `width:${Math.abs(p.r) * 50}%` })),
      el("span", { class: `corr-r ${p.r < 0 ? "neg" : "pos"}`, text: (p.r > 0 ? "+" : "") + p.r.toFixed(2) }),
      el("span", { class: "corr-strength", text: strength(p.r) }),
      el("span", { class: "corr-n muted", text: `n=${fmt(p.n)}` })
    )
  );
  return el(
    "div",
    {},
    toolbar,
    el("div", { class: "card" },
      el("h2", { text: `Strongest relationships${res.total > res.pairs.length ? ` (top ${res.pairs.length} of ${res.total})` : ""}` }),
      el("p", { class: "card-hint", text: "−1 = move in opposite directions, +1 = move together, 0 = no relationship. Correlation is not causation." }),
      el("div", { class: "corr-list" }, rows))
  );
}

/* ---- Target ------------------------------------------------------------ */
function targetChart(item) {
  if (!item.chart || !item.chart.length) return null;
  const values = item.chart.map((c) => c.value ?? 0);
  const lo = Math.min(0, ...values);
  const span = Math.max(...values) - lo || 1;
  const percent = item.chartMetric.startsWith("%");
  return el(
    "div",
    { class: "tgt-chart" },
    el("div", { class: "tgt-chart-title muted", text: `${item.chartMetric} by ${item.chartBy}` }),
    item.chart.map((c) =>
      el("div", { class: "tgt-chart-row", title: `${c.label}: ${fnum(c.value)}${percent ? "%" : ""} (n=${fmt(c.n)})` },
        el("span", { class: "tgt-chart-label", text: c.label }),
        el("div", { class: "tgt-chart-track" },
          el("span", { style: `width:${Math.max(1, (((c.value ?? 0) - lo) / span) * 100)}%` })),
        el("span", { class: "tgt-chart-value", text: percent ? fmtPct(c.value) : fnum(c.value) })))
  );
}

function viewTarget(res) {
  const current = (app.inspectParams.TARGET || {}).column || "";
  const options = app.state.columns.filter((c) => c.kind !== "other").map((c) => c.name);
  const select = el(
    "select",
    { class: "select-sm", "aria-label": "Target column",
      onchange: (e) => { app.inspectParams.TARGET = { column: e.target.value }; renderInspect(); } },
    el("option", { value: "", text: "Choose a column…" }),
    options.map((c) => el("option", { value: c, text: c }))
  );
  select.value = current;
  const picker = el(
    "div",
    { class: "card" },
    el("h2", { text: "What do you want to explain?" }),
    el("p", { class: "card-hint",
      text: "Pick the column you care about (sales, rating, churned…). Every other column is ranked by how strongly it is related to it." }),
    el("div", { class: "toolbar" }, el("label", { class: "field-inline" }, el("span", { text: "Target" }), select))
  );
  const s = res.summary;
  if (!s) return el("div", {}, picker);

  const tiles = el(
    "div",
    { class: "stats" },
    stat("Rows with a target", fmt(s.rows), s.missingTarget ? `${fmt(s.missingTarget)} missing, left out` : "None missing",
      s.missingTarget ? "warn" : "good"),
    s.kind === "numeric"
      ? stat("Average", fnum(s.mean), `median ${fnum(s.median)} · range ${fnum(s.min)} … ${fnum(s.max)}`)
      : stat("Classes", fmt(s.classCount), s.classes.slice(0, 3).map((c) => `${c.label} (${fmt(c.count)})`).join(" · ")),
    stat("Columns compared", fmt(res.columns.length), res.skipped.length ? `${res.skipped.length} skipped` : "All columns")
  );

  const rows = res.columns.map((c, i) =>
    el(
      "div",
      { class: "tgt-row" },
      el("div", { class: "tgt-main" },
        el("div", { class: "tgt-head" },
          el("span", { class: "tgt-rank muted", text: `${i + 1}` }),
          el("span", { class: "tgt-name", text: c.column, title: c.column }),
          el("span", { class: "chip", text: c.kind === "numeric" ? "number" : "category" }),
          el("span", { class: "tgt-strength", text: c.strength })),
        el("div", { class: "tgt-score" },
          bar(c.score, c.p != null && c.p >= 0.05 ? "muted-bar" : ""),
          el("span", { class: "mono", text: `${c.measure} = ${c.value.toFixed(2)}` })),
        el("p", { class: "tgt-sentence", text: c.sentence }),
        el("div", { class: "tgt-meta muted" },
          `n = ${fmt(c.n)}`, " · ", c.p == null ? "p = —" : `p ${c.p < 0.001 ? "< 0.001" : `= ${c.p.toPrecision(2)}`}`)),
      targetChart(c)
    )
  );
  const ranked = el(
    "div",
    { class: "card" },
    el("h2", { text: `Related to ${s.target}` }),
    el("p", { class: "card-hint",
      text: "Scores run from 0 (no relationship) to 1. Number vs number uses |Pearson r|, number vs category the correlation ratio η, category vs category Cramér's V. Grey bars could be chance (p ≥ 0.05). Related does not mean one causes the other." }),
    rows.length ? el("div", { class: "tgt-list" }, rows) : note("info", "No other column could be compared.")
  );
  const skipped = res.skipped.length
    ? el("details", { class: "card tgt-skipped" },
      el("summary", { text: `Skipped columns (${res.skipped.length})` }),
      el("ul", {}, res.skipped.map((k) => el("li", {}, el("strong", { text: k.column }), ` — ${k.skipped}`))))
    : null;
  return el("div", {}, picker, tiles, ranked, skipped);
}

const INSPECT_VIEWS = {
  QUALITY: viewQuality,
  STRUCTURE: viewStructure,
  STATS: viewStats,
  MISSING: viewMissing,
  DUPES: viewDupes,
  OUTLIERS: viewOutliers,
  CORR: viewCorr,
  TARGET: viewTarget,
};

async function renderInspect() {
  if (!app.state) return;
  const kind = app.inspectKind;
  const out = $("inspect-output");
  syncInspectTabs();
  app.inspectStale = false;
  const seq = ++inspectSeq;
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Calculating…");
  const showLoading = setTimeout(() => {
    if (seq === inspectSeq) out.replaceChildren(loading);
  }, 150);
  const hideCancel = delayedCancel(loading, "inspect", () => {
    if (seq !== inspectSeq) return;
    app.inspectStale = true;
    out.replaceChildren(note("info", "Cancelled. Pick a tab to run it again."));
  });
  try {
    const res = await callLatest("inspect", "inspect", { kind, params: app.inspectParams[kind] || {} });
    if (seq !== inspectSeq) return; // user switched tabs meanwhile
    out.replaceChildren(INSPECT_VIEWS[kind](res));
  } catch (err) {
    if (seq !== inspectSeq || isCancelled(err)) return;
    out.replaceChildren(note("error", cleanError(err)));
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}
let inspectSeq = 0;

/* ------------------------------------------------------------------ */
/* clean                                                                */
/* ------------------------------------------------------------------ */

let cleanValues = {};

const opInfo = (key) => {
  for (const g of CLEAN_OPS) {
    const item = g.items.find((i) => i.key === key);
    if (item) return { ...item, group: g.group };
  }
  return { key, label: LEGACY_OPS[key] || key, desc: "", group: "" };
};

/* column option helpers (labels carry useful hints) */
const colsWithMissing = () =>
  app.state.columns.filter((c) => c.missing > 0).map((c) => ({ value: c.name, label: `${c.name} · ${fmt(c.missing)} missing` }));
const textColOptions = () => categoricalCols();
const numericColOptions = () => numericCols();

const FILTER_OPS_NUMERIC = [
  ["==", "equals"], ["!=", "does not equal"], [">", "greater than"], [">=", "at least"],
  ["<", "less than"], ["<=", "at most"], ["is_missing", "is missing"], ["not_missing", "is not missing"],
];
const FILTER_OPS_TEXT = [
  ["contains", "contains"], ["not_contains", "does not contain"], ["==", "equals"], ["!=", "does not equal"],
  ["is_missing", "is missing"], ["not_missing", "is not missing"],
];
const toOptions = (pairs) => pairs.map(([value, label]) => ({ value, label }));

function cleanSpecs(method, memory) {
  const cols = allCols();
  switch (method) {
    case "REMOVE_DUPLICATES":
      return [
        { key: "columns", label: "Match on columns", type: "multi", options: cols, hint: "Leave empty to compare whole rows." },
        { key: "keep", label: "Which copy to keep", type: "select",
          options: toOptions([["first", "Keep the first occurrence"], ["last", "Keep the last occurrence"]]) },
      ];
    case "DROP_NA_ROWS":
      return [{ key: "columns", label: "Only check these columns", type: "multi", options: colsWithMissing(),
        hint: "Leave empty to drop rows missing any value." }];
    case "FILTER_ROWS": {
      const column = cols.includes(memory.column) ? memory.column : cols[0];
      const numeric = numericCols().includes(column);
      const ops = numeric ? FILTER_OPS_NUMERIC : FILTER_OPS_TEXT;
      const op = ops.some(([v]) => v === memory.operator) ? memory.operator : ops[0][0];
      const specs = [
        { key: "mode", label: "Action", type: "select",
          options: toOptions([["keep", "Keep rows where…"], ["remove", "Remove rows where…"]]) },
        { key: "column", label: "Column", type: "select", options: cols, rerender: true },
        { key: "operator", label: "Condition", type: "select", options: toOptions(ops), rerender: true },
      ];
      if (op !== "is_missing" && op !== "not_missing") {
        specs.push({ key: "value", label: numeric ? "Number" : "Text", type: "text",
          hint: numeric ? null : "Not case-sensitive for contains." });
      }
      return specs;
    }
    case "SORT_ROWS":
      return [
        { key: "column", label: "Sort by", type: "select", options: cols },
        { key: "ascending", label: "Order", type: "select",
          options: toOptions([["true", "Ascending (A→Z, 0→9)"], ["false", "Descending (Z→A, 9→0)"]]) },
      ];
    case "FILL_NA": {
      const specs = [
        { key: "columns", label: "Columns to fill", type: "multi", options: colsWithMissing(),
          default: colsWithMissing().map((o) => o.value) },
        { key: "strategy", label: "Fill with", type: "select", rerender: true,
          options: toOptions([
            ["median", "Median (numbers, robust to outliers)"], ["mean", "Mean (numbers)"],
            ["mode", "Most common value"], ["constant", "A fixed value…"],
            ["ffill", "Previous row's value"], ["bfill", "Next row's value"],
          ]) },
      ];
      if (memory.strategy === "constant") specs.push({ key: "value", label: "Value", type: "text" });
      return specs;
    }
    case "STRIP_WHITESPACE":
      return [{ key: "columns", label: "Text columns", type: "multi", options: textColOptions(),
        hint: "Leave empty for all text columns." }];
    case "NORMALIZE_TEXT":
      return [
        { key: "columns", label: "Text columns", type: "multi", options: textColOptions() },
        { key: "case", label: "Letter case", type: "select",
          options: toOptions([["none", "Keep as is"], ["title", "Title Case"], ["lower", "lowercase"], ["upper", "UPPERCASE"]]) },
      ];
    case "CLIP_IQR":
    case "CLIP_ZSCORE":
      return [{ key: "columns", label: "Numeric columns", type: "multi", options: numericColOptions(),
        hint: "Leave empty for all numeric columns." }];
    case "ROUND":
      return [
        { key: "columns", label: "Numeric columns", type: "multi", options: numericColOptions() },
        { key: "decimals", label: "Decimal places", type: "text", default: "2" },
      ];
    case "TO_NUMERIC":
      return [{ key: "columns", label: "Columns", type: "multi", options: textColOptions(),
        hint: "Commas, spaces, currency and % signs are removed first. Values that still aren't numbers become missing." }];
    case "TO_DATETIME":
      return [
        { key: "columns", label: "Columns", type: "multi", options: textColOptions(),
          hint: "Values that aren't dates become missing." },
        { key: "dayfirst", label: "Ambiguous dates like 03/04", type: "select",
          options: toOptions([["false", "Month first (March 4)"], ["true", "Day first (3 April)"]]) },
      ];
    case "JOIN": {
      const others = app.state.secondary || [];
      if (!others.length) return [];
      const name = others.some((o) => o.name === memory.dataset) ? memory.dataset : others[0].name;
      const other = others.find((o) => o.name === name);
      const otherCols = other.columns.map((c) => c.name);
      const left = cols.includes(memory.left_on) ? memory.left_on : cols.find((c) => otherCols.includes(c)) || cols[0];
      return [
        { key: "dataset", label: "Other file", type: "select", rerender: true,
          options: others.map((o) => ({ value: o.name, label: `${o.name} · ${fmt(o.shape[0])} rows` })), default: name },
        { key: "left_on", label: "Key in this data", type: "select", options: cols, default: left, rerender: true },
        { key: "right_on", label: `Key in ${name}`, type: "select", options: otherCols,
          default: otherCols.includes(left) ? left : otherCols[0] },
        { key: "how", label: "Which rows to keep", type: "select",
          options: toOptions([["left", "All rows of this data (left join)"], ["inner", "Only rows that match (inner join)"],
            ["outer", "All rows of both (outer join)"], ["right", "All rows of the other file (right join)"]]) },
        { key: "suffix", label: "Suffix for clashing column names", type: "text", default: "_right" },
      ];
    }
    case "ADD_COLUMN":
      return [
        { key: "name", label: "New column name", type: "text" },
        { key: "expression", label: "Expression (SQL syntax)", type: "text",
          hint: "Click a column below to insert it. Text goes in single quotes: 'top'." },
      ];
    case "DATE_PARTS": {
      const dates = datetimeCols();
      if (!dates.length) return [];
      return [
        { key: "column", label: "Date column", type: "select", options: dates },
        { key: "parts", label: "Parts to add", type: "multi", default: ["year", "month"],
          options: toOptions([["year", "Year"], ["quarter", "Quarter"], ["month", "Month (number)"], ["month_name", "Month name"],
            ["week", "Week of year"], ["day", "Day of month"], ["weekday", "Weekday name"], ["weekday_num", "Weekday (0 = Monday)"], ["hour", "Hour"]]) },
      ];
    }
    case "ONE_HOT":
      return [
        { key: "columns", label: "Category columns", type: "multi", options: categoricalCols().filter((c) => uniqueOf(c) <= 50),
          hint: "Columns with up to 50 different values. Group rare categories first if there are more." },
        TOGGLE("drop_first", "Drop the first category", false, "Avoids one redundant column, as linear models usually want."),
        TOGGLE("keep_original", "Keep the original columns", false),
      ];
    case "SCALE":
      return [
        { key: "columns", label: "Numeric columns", type: "multi", options: numericColOptions() },
        { key: "method", label: "Method", type: "select",
          options: toOptions([["standard", "Standard (z-score): mean 0, std 1"], ["minmax", "Min-max: 0 to 1"]]) },
        TOGGLE("keep_original", "Keep the original columns", false, "Writes the scaled values to new <column>_scaled columns."),
      ];
    case "BIN": {
      const specs = [
        { key: "column", label: "Numeric column", type: "select", options: numericColOptions() },
        { key: "method", label: "Ranges", type: "select", rerender: true,
          options: toOptions([["width", "Equal width"], ["quantile", "Equal count (quantiles)"], ["edges", "My own edges…"]]) },
      ];
      if (memory.method === "edges") {
        specs.push({ key: "edges", label: "Edges", type: "text", hint: "Numbers in increasing order, e.g. 0, 18, 30, 65, inf" });
      } else {
        specs.push({ key: "bins", label: "Number of ranges", type: "text", default: "5" });
      }
      specs.push({ key: "name", label: "New column name (optional)", type: "text", hint: "Default: <column>_bin" });
      return specs;
    }
    case "LOG_TRANSFORM":
      return [
        { key: "columns", label: "Numeric columns", type: "multi", options: numericColOptions() },
        { key: "method", label: "Function", type: "select",
          options: toOptions([["log1p", "log(1 + x): accepts zeros"], ["log", "Natural log: values must be > 0"], ["log10", "log10: values must be > 0"]]) },
        TOGGLE("keep_original", "Keep the original columns", false, "Writes the result to new <column>_log columns."),
      ];
    case "GROUP_RARE": {
      const specs = [
        { key: "columns", label: "Category columns", type: "multi", options: textColOptions() },
        { key: "mode", label: "Keep", type: "select", rerender: true,
          options: toOptions([["top", "The N most common values"], ["share", "Values with at least a share of rows"]]) },
      ];
      if (memory.mode === "share") specs.push({ key: "min_share", label: "Minimum share (%)", type: "text", default: "1" });
      else specs.push({ key: "top_n", label: "Values to keep", type: "text", default: "10" });
      specs.push({ key: "label", label: "Label for the rest", type: "text", default: "Other" });
      return specs;
    }
    case "RENAME_COLUMN":
      return [
        { key: "old_name", label: "Column to rename", type: "select", options: cols },
        { key: "new_name", label: "New name", type: "text" },
      ];
    case "CHANGE_DTYPE":
      return [
        { key: "column", label: "Column", type: "select", options: cols },
        { key: "dtype", label: "Target type", type: "select", options: DTYPE_OPTIONS },
      ];
    case "DROP_COLUMNS":
      return [{ key: "columns", label: "Columns to drop", type: "multi", options: cols }];
    case "REPLACE_VALUES":
      return [
        { key: "column", label: "Column", type: "select", options: cols },
        { key: "find", label: "Find value", type: "text" },
        { key: "replace", label: "Replace with", type: "text", hint: "Leave empty to mark as missing." },
      ];
    default:
      return [];
  }
}

const OPTIONAL_COLUMNS = new Set(["REMOVE_DUPLICATES", "DROP_NA_ROWS", "STRIP_WHITESPACE", "CLIP_IQR", "CLIP_ZSCORE"]);

function cleanParams(method, v) {
  const p = { ...v };
  if (Array.isArray(p.columns) && p.columns.length === 0 && OPTIONAL_COLUMNS.has(method)) delete p.columns;
  if (method === "RENAME_COLUMN") p.new_name = (p.new_name || "").trim();
  if (method === "FILTER_ROWS" && (p.operator === "is_missing" || p.operator === "not_missing")) p.value = "";
  if (method === "FILL_NA" && p.strategy !== "constant") delete p.value;
  for (const k of ["find", "replace", "value"]) if (k in p && p[k] == null) p[k] = "";
  return p;
}

/** Returns a reason string when the form is incomplete, otherwise "". */
function cleanInvalid(method, v) {
  if (!method) return "Choose an operation.";
  const needCols = ["NORMALIZE_TEXT", "ROUND", "TO_NUMERIC", "TO_DATETIME", "DROP_COLUMNS", "FILL_NA",
    "ONE_HOT", "SCALE", "LOG_TRANSFORM", "GROUP_RARE"];
  if (needCols.includes(method) && !(v.columns && v.columns.length)) return "Select at least one column.";
  if (method === "FILL_NA" && v.strategy === "constant" && !v.value) return "Enter the value to fill with.";
  if (method === "FILTER_ROWS" && !["is_missing", "not_missing"].includes(v.operator) && !v.value)
    return "Enter a value for the condition.";
  if (method === "RENAME_COLUMN") {
    const name = (v.new_name || "").trim();
    if (!name) return "Enter a new name.";
    if (name === v.old_name) return "The new name is the same as the old one.";
  }
  if (method === "REPLACE_VALUES" && !v.find) return "Enter the value to find.";
  if (method === "JOIN") {
    if (!(app.state.secondary || []).length) return "Add the other file to join with.";
    if (!v.left_on || !v.right_on) return "Choose a key column on each side.";
  }
  if (method === "ADD_COLUMN") {
    if (!(v.name || "").trim()) return "Enter a name for the new column.";
    if (!(v.expression || "").trim()) return "Write an expression, e.g. price / visits.";
  }
  if (method === "BIN") {
    if (!v.column) return "Choose a numeric column.";
    if (v.method === "edges" && !(v.edges || "").trim()) return "Enter the range edges, e.g. 0, 18, 30, 65, inf.";
    if (v.method !== "edges" && !(v.bins || "").trim()) return "Enter the number of ranges.";
  }
  if (method === "DATE_PARTS") {
    if (!datetimeCols().length) return "No date columns yet. Use Convert to date on a text column first.";
    if (!(v.parts && v.parts.length)) return "Choose at least one date part.";
  }
  return "";
}

function renderOpList() {
  $("op-list").replaceChildren(
    ...CLEAN_OPS.map((g) =>
      el(
        "div",
        { class: "op-group-block" },
        el("div", { class: "op-group-title" }, icon(g.icon), g.group),
        g.items.map((i) =>
          el("button", {
            class: `op-item ${i.key === app.cleanMethod ? "active" : ""}`,
            "aria-current": i.key === app.cleanMethod ? "true" : null,
            onclick: () => selectCleanMethod(i.key),
            text: i.label,
          })
        )
      )
    )
  );
}

function selectCleanMethod(method) {
  app.cleanMethod = method;
  renderOpList();
  renderCleanFields();
}

function renderCleanFields() {
  const method = app.cleanMethod;
  $("op-empty").hidden = !!method;
  $("op-body").hidden = !method;
  if (!method) return;
  const info = opInfo(method);
  $("op-group").textContent = tr(info.group);
  $("op-title").textContent = tr(info.label);
  $("clean-desc").textContent = tr(info.desc);

  const memory = (app.forms.clean[method] ||= {});
  const specs = cleanSpecs(method, memory);
  const rerenderKeys = new Set(specs.filter((s) => s.rerender).map((s) => s.key));
  const update = (values, changedKey) => {
    cleanValues = values;
    if (changedKey && rerenderKeys.has(changedKey)) {
      renderCleanFields(); // fields depend on this choice
      return;
    }
    schedulePreview();
  };
  cleanValues = buildForm($("clean-fields"), specs, memory, update);
  if (!specs.length) {
    const msg = {
      DATE_PARTS: "No date columns yet. Use Convert to date on a text column first.",
      JOIN: "First choose the other file. Its rows are matched to this data by a key column.",
    }[method] || "No settings needed.";
    $("clean-fields").replaceChildren(el("p", { class: "muted no-inputs", text: msg }));
  }
  if (method === "JOIN") {
    const hasOthers = (app.state.secondary || []).length > 0;
    $("clean-fields").append(el("div", { class: "join-add" },
      el("button", { class: "btn btn-sm", type: "button", onclick: addJoinFile }, icon("i-folder"),
        hasOthers ? "Add another file…" : "Choose the file to join…"),
      hasOthers ? null : el("span", { class: "field-hint", text: "CSV, Excel, Parquet or JSON. It is only read, never changed." })));
  }
  if (method === "ADD_COLUMN") {
    const input = $("clean-fields").querySelector('input[data-key="expression"]');
    const chips = el("div", { class: "query-columns expr-columns" },
      app.state.columns.map((c) => el("button", {
        class: "col-chip", type: "button", title: `Insert ${sqlName(c.name)}`,
        onclick: () => {
          insertAtCursor(input, sqlName(c.name));
          input.dispatchEvent(new Event("input", { bubbles: true }));
        },
      }, el("span", { class: "col-chip-name", text: c.name }), el("span", { class: "col-chip-type", text: c.dtype }))));
    $("clean-fields").append(chips);
  }
  schedulePreview(0);
}

/* ---- live impact preview -------------------------------------------- */

let previewTimer = null;
let previewSeq = 0;

function schedulePreview(delay = 280) {
  clearTimeout(previewTimer);
  const method = app.cleanMethod;
  const reason = cleanInvalid(method, cleanValues);
  $("btn-do").disabled = true;
  if (reason) {
    renderImpact({ state: "idle", text: reason });
    return;
  }
  renderImpact({ state: "loading" });
  previewTimer = setTimeout(runPreview, delay);
}

async function runPreview() {
  const seq = ++previewSeq;
  const method = app.cleanMethod;
  try {
    // Background request; a newer preview cancels this one.
    const res = await callLatest("preview", "preview", { method, params: cleanParams(method, cleanValues) });
    if (seq !== previewSeq) return;
    const noChange =
      res.removedRows === 0 && res.changedCells === 0 && !res.removedColumns.length && !res.addedColumns.length &&
      !res.dtypeChanges.length && !res.orderSample;
    renderImpact({ state: "ready", res, noChange });
    $("btn-do").disabled = noChange;
  } catch (err) {
    if (seq !== previewSeq || isCancelled(err)) return;
    renderImpact({ state: "error", text: cleanError(err) });
    $("btn-do").disabled = true;
  }
}

function changeTable(changes) {
  const head = el("tr", {}, el("th", { class: "idx", text: "Row" }), changes.columns.map((c) => el("th", { text: c, raw: true })));
  const body = changes.rows.map((r) =>
    el(
      "tr",
      {},
      el("td", { class: "idx", text: r.row, raw: true }),
      r.cells.map((cell) => {
        const show = (v) => (v == null ? "NaN" : v);
        if (!cell.changed) return el("td", { class: "muted", text: show(cell.before), raw: true });
        return el(
          "td",
          { class: "diff-cell", title: `${show(cell.before)} → ${show(cell.after)}`, raw: true },
          el("span", { class: `diff-before ${cell.before == null ? "null" : ""}`, text: show(cell.before), raw: true }),
          el("span", { class: "diff-arrow", text: "→", raw: true }),
          el("span", { class: `diff-after ${cell.after == null ? "null" : ""}`, text: show(cell.after), raw: true })
        );
      })
    )
  );
  return el("div", { class: "table-wrap impact-table" }, el("table", {}, el("thead", {}, head), el("tbody", {}, body)));
}

function renderImpact({ state, res, text, noChange }) {
  const box = $("impact");
  box.className = `impact ${state}`;
  if (state === "idle") {
    box.replaceChildren(el("div", { class: "impact-idle" }, el("span", { class: "impact-dot" }), text));
    return;
  }
  if (state === "loading") {
    box.replaceChildren(el("div", { class: "impact-idle" }, el("span", { class: "impact-dot pulse" }), "Calculating impact…"));
    return;
  }
  if (state === "error") {
    box.replaceChildren(note("error", text));
    return;
  }
  if (noChange) {
    box.replaceChildren(note("info", "Nothing would change. The data already meets this condition."));
    return;
  }

  const [rb, ra] = res.rows;
  const [cb, ca] = res.cols;
  const nCols = Object.keys(res.changedByColumn).length;
  const pills = [];
  if (res.removedRows) pills.push(el("span", { class: "impact-pill bad", text: `−${fmt(res.removedRows)} rows` }));
  if (res.removedColumns.length) pills.push(el("span", { class: "impact-pill bad", text: `−${res.removedColumns.length} col` }));
  if (res.addedColumns.length) pills.push(el("span", { class: "impact-pill good", text: `+${res.addedColumns.length} col` }));
  if (res.changedCells) pills.push(el("span", { class: "impact-pill", text: `${fmt(res.changedCells)} cells changed in ${plural(nCols, "column")}` }));
  for (const d of res.dtypeChanges) pills.push(el("span", { class: "impact-pill mono", text: `${d.column}: ${d.before} → ${d.after}` }));
  if (res.orderSample) pills.push(el("span", { class: "impact-pill", text: "Row order changes" }));

  const parts = [
    el(
      "div",
      { class: "impact-head" },
      el("div", { class: "impact-label", text: "Preview" }),
      el("div", { class: "impact-msg", text: res.message }),
      el("div", { class: "impact-shape mono", text: `${fmt(rb)} × ${cb}  →  ${fmt(ra)} × ${ca}` })
    ),
    el("div", { class: "impact-pills" }, pills),
  ];
  if (res.changes.rows.length) {
    parts.push(el("div", { class: "impact-sub", text: `Changed cells (first ${res.changes.rows.length} rows)` }), changeTable(res.changes));
  }
  if (res.join) {
    const j = res.join;
    const pctMatched = j.leftRows ? Math.round((j.matchedLeft / j.leftRows) * 100) : 0;
    parts.splice(1, 1, el("div", { class: "join-stats" },
      el("div", { class: "join-stat" }, el("strong", { text: `${fmt(j.matchedLeft)} / ${fmt(j.leftRows)}` }), el("span", { text: `rows here matched (${pctMatched}%)` })),
      el("div", { class: "join-stat" }, el("strong", { text: fmt(j.unmatchedLeft) }), el("span", { text: "rows here without a match" })),
      el("div", { class: "join-stat" }, el("strong", { text: fmt(j.unmatchedRight) }), el("span", { text: `rows in ${j.otherName} without a match` })),
      el("div", { class: "join-stat" }, el("strong", { text: `${fmt(j.leftRows)} → ${fmt(j.resultRows)}` }), el("span", { text: "rows before → after" }))));
    if (j.duplicateRightKeys) {
      parts.push(note("warn", `${fmt(j.duplicateRightKeys)} rows in ${j.otherName} share a key with another row, so matching rows here will be repeated. Remove duplicates in that file first if each key should appear once.`));
    }
    if (!j.matchedLeft) parts.push(note("warn", "No rows match. Check that the key columns hold the same values (for example, same spelling and no extra spaces)."));
    const wrap = el("div", { class: "table-wrap impact-table" });
    renderTable(wrap, res.resultSample, { indexLabel: "Row" });
    parts.push(el("div", { class: "impact-sub", text: "Result (first rows)" }), wrap);
  } else if (res.addedSample) {
    const wrap = el("div", { class: "table-wrap impact-table" });
    renderTable(wrap, res.addedSample, { indexLabel: "Row" });
    parts.push(el("div", { class: "impact-sub", text: "New column values (first rows)" }), wrap);
  }
  if (res.removedSample) {
    const wrap = el("div", { class: "table-wrap impact-table" });
    renderTable(wrap, res.removedSample, { indexLabel: "Row" });
    parts.push(el("div", { class: "impact-sub", text: `Rows that will be removed (first ${res.removedSample.data.length})` }), wrap);
  }
  if (res.orderSample) {
    const wrap = el("div", { class: "table-wrap impact-table" });
    renderTable(wrap, res.orderSample, { indexLabel: "Row" });
    parts.push(el("div", { class: "impact-sub", text: "New order (first rows)" }), wrap);
  }
  if (res.code) {
    parts.push(el("details", { class: "impact-code" }, el("summary", { text: "pandas code for this step" }), el("pre", { class: "code-block", text: res.code })));
  }
  box.replaceChildren(...parts);
}

async function addJoinFile() {
  try {
    const path = await window.api.chooseFile();
    if (!path) return;
    let res = await withBusy(window.api.call("load_secondary", { path }));
    if (res.needsSheet) {
      const sheet = await pickSheet(res.sheets, path.split(/[\\/]/).pop());
      if (!sheet) return;
      res = await withBusy(window.api.call("load_secondary", { path, sheet }));
    }
    app.state = res.state;
    app.forms.clean.JOIN = { ...(app.forms.clean.JOIN || {}), dataset: res.name };
    renderCleanFields();
    toast("success", `Added ${res.name} (${fmt(res.shape[0])} rows) for joining.`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function doClean() {
  const method = app.cleanMethod;
  if (!method || $("btn-do").disabled) return;
  try {
    const res = await call("clean", { method, params: cleanParams(method, cleanValues) });
    // Clear free-text inputs after a successful operation.
    const mem = app.forms.clean[method] || {};
    for (const k of ["new_name", "find", "replace", "value"]) delete mem[k];
    setState(res.state);
    toast("success", res.message);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function undo() {
  try {
    const res = await call("undo");
    setState(res.state);
    toast("success", res.message);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function revertTo(keep) {
  try {
    const res = await call("revert", { keep });
    setState(res.state);
    toast("success", res.message);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

/** Button that needs a second click within 3 s to run (no blocking confirm dialogs). */
function confirmButton(label, confirmLabel, onConfirm) {
  let armed = null;
  const btn = el("button", { class: "btn btn-sm btn-ghost tl-revert" }, icon("i-revert"), el("span", { text: label }));
  btn.addEventListener("click", () => {
    if (armed) {
      clearTimeout(armed);
      onConfirm();
      return;
    }
    btn.classList.add("armed");
    btn.querySelector("span").textContent = tr(confirmLabel);
    armed = setTimeout(() => {
      armed = null;
      btn.classList.remove("armed");
      btn.querySelector("span").textContent = tr(label);
    }, 3000);
  });
  return btn;
}

function renderHistory() {
  const log = app.state.log;
  $("history-summary").textContent = tr(log.length ? `History · ${plural(log.length, "step")}` : "History");
  $("btn-code").disabled = !log.length;
  const list = $("history-list");
  list.replaceChildren();
  const chip = (label, n) =>
    el("span", { class: `delta-chip ${n > 0 ? "up" : ""}`, text: `${n > 0 ? "+" : "−"}${fmt(Math.abs(n))} ${label}` });

  [...log].reverse().forEach((entry, i) => {
    const dRows = entry.shape_after[0] - entry.shape_before[0];
    const dCols = entry.shape_after[1] - entry.shape_before[1];
    const chips = [];
    if (dRows) chips.push(chip("rows", dRows));
    if (dCols) chips.push(chip("cols", dCols));
    const current = i === 0;
    list.append(
      el(
        "li",
        { class: current ? "current" : null },
        el("div", { class: "tl-top" },
          el("span", { class: "tl-step", text: `Step ${entry.step} · ${opInfo(entry.method).label}` }),
          current
            ? el("span", { class: "tl-now", text: "Current" })
            : confirmButton("Revert here", "Click to confirm", () => revertTo(entry.step))),
        el("div", { class: "tl-msg", text: entry.msg }),
        chips.length ? el("div", { class: "tl-delta" }, chips) : null
      )
    );
  });

  const [r0, c0] = log.length ? log[0].shape_before : app.state.shape;
  list.append(
    el(
      "li",
      { class: `origin ${log.length ? "" : "current"}` },
      el("div", { class: "tl-top" },
        el("span", { class: "tl-step", text: "Original data" }),
        log.length ? confirmButton("Reset", "Click to confirm", () => revertTo(0)) : el("span", { class: "tl-now", text: "Current" })),
      el("div", { class: "tl-msg muted", text: `${app.state.fileName} · ${plural(r0, "row")} × ${plural(c0, "column")}` })
    )
  );
}

function openCodeDialog(title, sub, code, fileName) {
  app.script = { code, fileName };
  $("code-title").textContent = tr(title);
  $("code-sub").textContent = tr(sub);
  $("code-text").textContent = code;
  $("code-dialog").showModal();
}

async function showCode() {
  try {
    const res = await call("script");
    openCodeDialog("Cleaning steps as pandas code", "Run it next to your CSV to reproduce the exact same result.", res.code, res.fileName);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function renderPreview() {
  const preview = app.state.preview;
  $("preview").hidden = !preview;
  if (!preview) return;
  const label = (name, shape) => `${name} · ${plural(shape[0], "row")} × ${plural(shape[1], "col")}`;
  $("preview-before-title").textContent = tr(label("Before", preview.before.shape));
  $("preview-after-title").textContent = tr(label("After", preview.after.shape));
  renderTable($("preview-before"), preview.before.table);
  renderTable($("preview-after"), preview.after.table, { types: true });
}

/* ------------------------------------------------------------------ */
/* query (SQL)                                                          */
/* ------------------------------------------------------------------ */

const SAVED_QUERIES_KEY = "databoss.savedQueries";
const QUERY_PREVIEW_LIMIT = 500;

function loadSavedQueries() {
  try {
    const list = JSON.parse(localStorage.getItem(SAVED_QUERIES_KEY) || "[]");
    return Array.isArray(list) ? list.filter((q) => q && typeof q.sql === "string") : [];
  } catch {
    return [];
  }
}

function storeSavedQueries(list) {
  try {
    localStorage.setItem(SAVED_QUERIES_KEY, JSON.stringify(list.slice(0, 30)));
  } catch {
    /* storage unavailable: saved queries just won't persist */
  }
}

async function loadQueryInfo() {
  if (!app.state) return;
  app.query.infoStale = false;
  try {
    app.query.info = await window.api.call("query_info", {});
    renderQuerySide();
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function insertAtCursor(textarea, text) {
  const { selectionStart: a, selectionEnd: b, value } = textarea;
  textarea.value = value.slice(0, a) + text + value.slice(b);
  textarea.selectionStart = textarea.selectionEnd = a + text.length;
  textarea.focus();
  app.query.sql = textarea.value;
}

function setEditorSql(sql, run = true) {
  const ed = $("sql-editor");
  ed.value = sql;
  app.query.sql = sql;
  ed.focus();
  if (run) runQuery();
}

function renderQuerySide() {
  const info = app.query.info;
  if (!info) return;
  $("query-columns").replaceChildren(
    ...info.columns.map((c) =>
      el("button", {
        class: "col-chip",
        title: `Insert ${c.sql}`,
        onclick: () => insertAtCursor($("sql-editor"), c.sql),
      },
      el("span", { class: "col-chip-name", text: c.name }),
      el("span", { class: "col-chip-type", text: c.dtype }))
    )
  );
  $("query-examples").replaceChildren(
    ...info.examples.map((e) =>
      el("button", { class: "query-item", title: e.sql, onclick: () => setEditorSql(e.sql) }, icon("i-play"), el("span", { text: e.title }))
    )
  );
  renderSavedQueries();
}

function renderSavedQueries() {
  const list = loadSavedQueries();
  const box = $("query-saved");
  if (!list.length) {
    box.replaceChildren(el("p", { class: "query-empty", text: "Save a query to reuse it later." }));
    return;
  }
  box.replaceChildren(
    ...list.map((q, i) => {
      const remove = el("button", { class: "query-remove", title: "Remove", "aria-label": `Remove ${q.title}` }, icon("i-x"));
      remove.addEventListener("click", (e) => {
        e.stopPropagation();
        const next = loadSavedQueries();
        next.splice(i, 1);
        storeSavedQueries(next);
        renderSavedQueries();
      });
      return el("div", { class: "query-item", role: "button", tabindex: "0", title: q.sql, onclick: () => setEditorSql(q.sql) },
        icon("i-star"), el("span", { text: q.title }), remove);
    })
  );
}

function saveCurrentQuery() {
  const sql = ($("sql-editor").value || "").trim();
  if (!sql) return;
  const firstLine = sql.split("\n").find((l) => l.trim()) || "Query";
  const title = firstLine.replace(/\s+/g, " ").slice(0, 60);
  const list = loadSavedQueries().filter((q) => q.sql !== sql);
  list.unshift({ title, sql });
  storeSavedQueries(list);
  renderSavedQueries();
  toast("success", "Query saved.");
}

let querySeq = 0;

async function runQuery() {
  if (!app.state) return;
  const sql = ($("sql-editor").value || "").trim();
  app.query.sql = sql;
  const out = $("query-output");
  $("query-result-card").hidden = false;
  // Until this query finishes, Apply/Chart/Save would act on the previous result: hide them.
  app.query.lastSql = "";
  $("query-actions").hidden = true;
  const seq = ++querySeq;
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Running query…");
  const showLoading = setTimeout(() => seq === querySeq && out.replaceChildren(loading), 120);
  const hideCancel = delayedCancel(loading, "query", () => {
    if (seq !== querySeq) return;
    out.replaceChildren(note("info", "Query cancelled."));
  });
  try {
    const res = await callLatest("query", "query", { sql, limit: QUERY_PREVIEW_LIMIT });
    if (seq !== querySeq) return;
    app.query.result = res;
    app.query.lastSql = sql;
    renderQueryResult(res);
    if (!$("query-chart-card").hidden) renderQueryChartFields(true);
  } catch (err) {
    if (seq !== querySeq || isCancelled(err)) return;
    app.query.result = null;
    $("query-meta").textContent = tr("");
    $("query-actions").hidden = true;
    out.replaceChildren(el("pre", { class: "query-error", text: cleanError(err) }));
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}

function renderQueryResult(res) {
  const shown = res.table.data.length;
  const cols = res.columns.length;
  $("query-meta").textContent =
    `${plural(res.total, "row")} × ${plural(cols, "column")} · ${res.ms} ms` +
    (res.total > shown ? ` · showing the first ${fmt(shown)}` : "");
  $("query-actions").hidden = false;
  const out = $("query-output");
  if (!res.total) {
    out.replaceChildren(note("info", "The query ran but returned no rows."));
    return;
  }
  const wrap = el("div", { class: "table-wrap" });
  renderTable(wrap, res.table, { indexLabel: "#", meta: new Map(res.columns.map((c) => [c.name, c])) });
  out.replaceChildren(wrap);
}

async function applyQuery() {
  const sql = app.query.lastSql;
  if (!sql) return;
  try {
    const res = await call("query_apply", { sql });
    setState(res.state);
    toast("success", `${res.message} Undo it from Clean if needed.`);
    runQuery();
  } catch (err) {
    toast("error", cleanError(err));
  }
}

/* ---- quick chart of the result ------------------------------------------ */

function suggestQueryChart(columns) {
  const num = columns.filter((c) => c.kind === "numeric").map((c) => c.name);
  const cat = columns.filter((c) => c.kind === "categorical").map((c) => c.name);
  const dt = columns.filter((c) => c.dtype.startsWith("datetime")).map((c) => c.name);
  if (dt.length && num.length) return { kind: "LINE", x: dt[0], y: num[0] };
  if (cat.length && num.length) return { kind: "BAR", x: cat[0], y: num[num.length - 1] };
  if (num.length >= 2) return { kind: "SCAT", x: num[0], y: num[1] };
  if (num.length) return { kind: "HIST", x: num[0], y: "" };
  if (cat.length) return { kind: "COUNT", x: cat[0], y: "" };
  return null;
}

const QUERY_CHART_KINDS = [
  ["BAR", "Bar"], ["LINE", "Line"], ["SCAT", "Scatter"], ["HIST", "Histogram"], ["COUNT", "Count"],
];

function queryChartParams({ kind, x, y }) {
  switch (kind) {
    case "BAR": return { x, y: y || undefined, agg: y ? "sum" : "count", top_n: "25" };
    case "LINE": return { x, y, agg: "mean" };
    case "SCAT": return { x, y };
    case "HIST": return { column: x };
    case "COUNT": return { column: x, top_n: "25" };
    default: return {};
  }
}

function renderQueryChartFields(reset = false) {
  const res = app.query.result;
  if (!res) return;
  const cols = res.columns.map((c) => c.name);
  if (reset || !app.query.chart || !cols.includes(app.query.chart.x)) {
    app.query.chart = suggestQueryChart(res.columns);
  }
  const cfg = app.query.chart;
  if (!cfg) {
    $("query-chart-fields").replaceChildren();
    $("query-chart-output").replaceChildren(note("info", "Nothing to chart in this result."));
    return;
  }
  const needsY = cfg.kind === "BAR" || cfg.kind === "LINE" || cfg.kind === "SCAT";
  const select = (label, value, options, onChange) => {
    const s = el("select", { "aria-label": label, onchange: (e) => onChange(e.target.value) },
      options.map(([v, t]) => el("option", { value: v, text: t })));
    s.value = value;
    return s;
  };
  $("query-chart-fields").replaceChildren(...[
    select("Chart type", cfg.kind, QUERY_CHART_KINDS, (v) => { cfg.kind = v; renderQueryChartFields(); }),
    select("X axis", cfg.x, cols.map((c) => [c, c]), (v) => { cfg.x = v; drawQueryChart(); }),
    needsY
      ? select("Y axis", cfg.y || "", [...(cfg.kind === "BAR" ? [["", "Number of rows"]] : []), ...cols.map((c) => [c, c])],
          (v) => { cfg.y = v; drawQueryChart(); })
      : null,
  ].filter(Boolean));
  drawQueryChart();
}

let queryChartSeq = 0;

async function drawQueryChart() {
  const cfg = app.query.chart;
  if (!cfg || !app.query.lastSql) return;
  const seq = ++queryChartSeq;
  $("query-chart-loading").hidden = false;
  $("query-chart-stage").classList.add("busy-stage");
  try {
    const res = await callLatest("query_chart", "query_chart", {
      sql: app.query.lastSql,
      kind: cfg.kind,
      params: queryChartParams(cfg),
      style: chartStyle(),
      width: Math.max(600, $("query-chart-stage").clientWidth - 32),
    });
    if (seq !== queryChartSeq) return;
    $("query-chart-output").replaceChildren(el("img", { src: res.image, alt: `${cfg.kind} chart of the query result` }));
    const box = $("query-chart-insights");
    box.hidden = !res.insights.length;
    box.replaceChildren(
      el("div", { class: "insights" },
        el("div", { class: "insights-title" }, icon("i-bulb"), "What this shows"),
        el("ul", {}, res.insights.map((t) => el("li", { text: t }))))
    );
  } catch (err) {
    if (seq !== queryChartSeq || isCancelled(err)) return;
    $("query-chart-output").replaceChildren(note("error", cleanError(err)));
    $("query-chart-insights").hidden = true;
  } finally {
    if (seq === queryChartSeq) {
      $("query-chart-loading").hidden = true;
      $("query-chart-stage").classList.remove("busy-stage");
    }
  }
}

function toggleQueryChart() {
  const card = $("query-chart-card");
  card.hidden = !card.hidden;
  if (!card.hidden) {
    renderQueryChartFields(true);
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

/* ------------------------------------------------------------------ */
/* analyze: pivot table                                                 */
/* ------------------------------------------------------------------ */

let pivotValues = {};

function pivotSpecs(memory) {
  const groups = groupCols();
  const cols = allCols();
  const counting = !memory.values;
  const additive = counting || ["count", "sum"].includes(memory.agg || "mean");
  const specs = [
    { key: "rows", label: "Rows", type: "multi", options: cols, default: groups.slice(0, 1),
      hint: "Each distinct combination becomes a row." },
    { key: "columns", label: "Columns (optional)", type: "select", options: [{ value: "", label: "None" }, ...groups], rerender: true },
    { key: "values", label: "Values", type: "select", rerender: true,
      options: [{ value: "", label: "Number of rows" }, ...cols], default: numericCols()[0] || "" },
  ];
  if (!counting) {
    specs.push({ key: "agg", label: "Combine with", type: "select", rerender: true, default: "mean",
      options: toOptions([["mean", "Mean"], ["sum", "Sum"], ["median", "Median"], ["min", "Min"], ["max", "Max"], ["count", "Count (non-empty)"], ["nunique", "Distinct values"]]) });
  }
  if (additive) {
    const pct = [["none", "Values"], ["total", "% of grand total"]];
    if (memory.columns) pct.splice(1, 0, ["row", "% of row"], ["column", "% of column"]);
    specs.push({ key: "percent", label: "Show as", type: "select", options: toOptions(pct) });
  }
  specs.push(
    { key: "sort", label: "Order rows", type: "select",
      options: toOptions([["label", "By label"], ["value_desc", "Largest first"], ["value_asc", "Smallest first"]]) },
    TOGGLE("totals", "Show totals", true)
  );
  return specs;
}

function pivotParams(v) {
  const counting = !v.values;
  const agg = counting ? "count" : v.agg || "mean";
  const additive = ["count", "sum"].includes(agg);
  let percent = additive ? v.percent || "none" : "none";
  if (!v.columns && (percent === "row" || percent === "column")) percent = "none";
  return {
    rows: v.rows || [],
    columns: v.columns || null,
    values: v.values || null,
    agg,
    percent,
    sort: v.sort || "label",
    totals: v.totals !== false,
  };
}

function renderPivotFields(run = false) {
  const memory = (app.forms.pivot ||= {});
  const specs = pivotSpecs(memory);
  const rerender = new Set(specs.filter((s) => s.rerender).map((s) => s.key));
  pivotValues = buildForm($("pivot-fields"), specs, memory, (values, key) => {
    pivotValues = values;
    if (key && rerender.has(key)) return renderPivotFields(true);
    schedulePivot();
  });
  if (run || app.section === "analyze") schedulePivot(0);
  else app.pivotStale = true;
}

let pivotTimer = null;
let pivotSeq = 0;

function schedulePivot(delay = 250) {
  clearTimeout(pivotTimer);
  if (!(pivotValues.rows && pivotValues.rows.length)) {
    $("pivot-actions").hidden = true;
    $("pivot-sub").textContent = tr("");
    $("pivot-output").replaceChildren(note("info", "Pick at least one column for the rows."));
    $("pivot-notes").replaceChildren();
    return;
  }
  pivotTimer = setTimeout(runPivot, delay);
}

function pivotSubtitle(p) {
  const what = p.values ? (p.agg === "nunique" ? trf("distinct {0}", p.values) : trf(`${p.agg} of {0}`, p.values)) : tr("number of rows");
  const by = [p.rows.join(" × "), p.columns].filter(Boolean).join(tr(" by "));
  const pct = { row: ` · ${tr("% of row")}`, column: ` · ${tr("% of column")}`, total: ` · ${tr("% of grand total")}` }[p.percent] || "";
  return `${trf("{0} by {1}", what, by)}${pct}`;
}

async function runPivot() {
  if (!app.state) return;
  const seq = ++pivotSeq;
  const params = pivotParams(pivotValues);
  app.pivotStale = false;
  const out = $("pivot-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Building table…");
  const showLoading = setTimeout(() => seq === pivotSeq && out.replaceChildren(loading), 150);
  const hideCancel = delayedCancel(loading, "pivot", () => seq === pivotSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("pivot", "pivot", { params });
    if (seq !== pivotSeq) return;
    app.pivot = { params, res };
    $("pivot-sub").textContent = tr(pivotSubtitle(params));
    $("pivot-actions").hidden = false;
    out.replaceChildren(pivotTable(res));
    $("pivot-notes").replaceChildren(...res.notes.map((t) => el("p", { text: t })));
    if (!$("pivot-chart-card").hidden) renderPivotChartFields();
  } catch (err) {
    if (seq !== pivotSeq || isCancelled(err)) return;
    app.pivot = null;
    $("pivot-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
    $("pivot-notes").replaceChildren();
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}

function pivotTable(res) {
  const t = res.table;
  const nRows = res.rows.length;
  const valueCols = res.valueColumns;
  const isTotalCol = (name) => res.hasTotals && name === "Total" && valueCols.length > 1;
  const lastIsTotal = res.hasTotals;
  // Heat scale from the inner cells only (no totals).
  const inner = [];
  t.data.forEach((row, i) => {
    if (lastIsTotal && i === t.data.length - 1) return;
    row.slice(nRows).forEach((v, j) => {
      if (typeof v === "number" && !isTotalCol(t.columns[nRows + j])) inner.push(v);
    });
  });
  const lo = Math.min(...inner);
  const hi = Math.max(...inner);
  const shade = (v) => (hi > lo ? 4 + ((v - lo) / (hi - lo)) * 34 : 12);
  const fmtCell = (v) => (v == null ? "—" : res.percent ? `${fnum(v)}%` : fnum(v));

  const head = el("tr", {}, t.columns.map((c, i) =>
    el("th", { text: c, title: c, raw: c !== "Total", class: [i >= nRows ? "num" : "", isTotalCol(c) ? "total" : ""].join(" ") })));
  const body = t.data.map((row, i) => {
    const totalRow = lastIsTotal && i === t.data.length - 1;
    return el("tr", { class: totalRow ? "total-row" : null },
      row.map((v, j) => {
        if (j < nRows) return el("td", { class: "rowkey", text: v ?? "", title: v ?? "", raw: !(totalRow && v === "Total") });
        const col = t.columns[j];
        const cls = ["cell", v == null ? "empty" : "", isTotalCol(col) ? "total" : ""].join(" ");
        const cell = el("td", { class: cls, text: fmtCell(v), raw: true });
        if (!totalRow && !isTotalCol(col) && typeof v === "number") {
          cell.style.background = `color-mix(in srgb, var(--primary) ${shade(v).toFixed(0)}%, var(--surface))`;
        }
        return cell;
      }));
  });
  return el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, head), el("tbody", {}, body)));
}

async function savePivot() {
  if (!app.pivot) return;
  try {
    const res = await call("pivot_apply", { params: app.pivot.params });
    setState(res.state);
    toast("success", `${res.message} Undo it from Clean if needed.`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function showPivotCode() {
  if (!app.pivot) return;
  openCodeDialog("Pivot table as pandas code", "Builds the same table from your file.", app.pivot.res.code, "pivot_table.py");
}

/* ---- statistical tests ------------------------------------------------- */

function selectAnalyzeTab(tab) {
  app.analyzeTab = tab;
  for (const b of document.querySelectorAll("#analyze-tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const t of ["pivot", "trends", "segment", "tests"]) $(`analyze-${t}`).hidden = tab !== t;
  if (!app.state) return;
  if (tab === "tests") renderTestFields(app.testStale !== false);
  else if (tab === "segment") renderSegmentFields(app.segmentStale !== false);
  else if (tab === "trends") renderTrendFields(app.trendStale !== false);
  else if (app.pivotStale) renderPivotFields(true);
}

/* ---- segment comparison ------------------------------------------------ */

let segmentValues = {};
let segmentTimer = null;
let segmentSeq = 0;
const MAX_CONDITIONS = 3;

function renderSegmentFields(run = false) {
  const memory = (app.forms.segment ||= { count: 1 });
  const cols = allCols();
  const box = $("segment-fields");
  box.replaceChildren();
  const values = {};
  for (let i = 0; i < memory.count; i++) {
    const p = `c${i}_`;
    const column = cols.includes(memory[p + "column"]) ? memory[p + "column"] : groupCols()[0] || cols[0];
    const ops = numericCols().includes(column) ? FILTER_OPS_NUMERIC : FILTER_OPS_TEXT;
    const op = ops.some(([v]) => v === memory[p + "operator"]) ? memory[p + "operator"] : "==";
    const specs = [
      { key: p + "column", label: i ? "And" : "Column", type: "select", options: cols, default: column, rerender: true },
      { key: p + "operator", label: "Condition", type: "select", options: toOptions(ops), default: op, rerender: true },
    ];
    if (op !== "is_missing" && op !== "not_missing") specs.push({ key: p + "value", label: "Value", type: "text" });
    const group = el("div", { class: "segment-cond" });
    const v = buildForm(group, specs, memory, (vals, key) => {
      Object.assign(segmentValues, vals);
      if (key === p + "column" || key === p + "operator") return renderSegmentFields(true);
      scheduleSegment(450);
    });
    Object.assign(values, v);
    if (i > 0) {
      group.append(el("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: () => {
        for (let j = i; j < memory.count - 1; j++) {
          for (const k of ["column", "operator", "value"]) memory[`c${j}_${k}`] = memory[`c${j + 1}_${k}`];
        }
        memory.count -= 1;
        renderSegmentFields(true);
      } }, "Remove condition"));
    }
    box.append(group);
  }
  if (memory.count < MAX_CONDITIONS) {
    box.append(el("button", { class: "btn btn-sm", type: "button", onclick: () => { memory.count += 1; renderSegmentFields(false); } },
      "+ Add condition"));
  }
  segmentValues = values;
  if (run) scheduleSegment(0);
}

function segmentConditions(v) {
  const out = [];
  for (let i = 0; i < MAX_CONDITIONS; i++) {
    const column = v[`c${i}_column`];
    if (!column) continue;
    out.push({ column, operator: v[`c${i}_operator`] || "==", value: v[`c${i}_value`] || "" });
  }
  return out;
}

function scheduleSegment(delay = 250) {
  clearTimeout(segmentTimer);
  app.segmentStale = false;
  const conds = segmentConditions(segmentValues);
  const missing = conds.find((c) => !["is_missing", "not_missing"].includes(c.operator) && !c.value.trim());
  if (!conds.length || missing) {
    $("segment-actions").hidden = true;
    $("segment-sub").textContent = tr("");
    $("segment-output").replaceChildren(note("info", "Describe the segment: pick a column, a condition and a value, e.g. churned equals yes."));
    return;
  }
  segmentTimer = setTimeout(runSegment, delay);
}

async function runSegment() {
  if (!app.state) return;
  const seq = ++segmentSeq;
  const out = $("segment-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Comparing every column…");
  const showLoading = setTimeout(() => seq === segmentSeq && out.replaceChildren(loading), 150);
  const hideCancel = delayedCancel(loading, "segment", () => seq === segmentSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("segment", "segment", { conditions: segmentConditions(segmentValues) });
    if (seq !== segmentSeq) return;
    app.segment = res;
    $("segment-sub").textContent = trf("{0} · {1} vs {2} rows", tr(res.label), fmt(res.segmentRows), fmt(res.restRows));
    $("segment-actions").hidden = false;
    out.replaceChildren(segmentView(res));
  } catch (err) {
    if (seq !== segmentSeq || isCancelled(err)) return;
    app.segment = null;
    $("segment-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}

function pairBars(items) {
  const max = Math.max(...items.flatMap((i) => [i.seg ?? 0, i.rest ?? 0]), 1e-12);
  return el("div", { class: "seg-bars" },
    items.map((i) =>
      el("div", { class: "seg-bar-row" },
        el("span", { class: "seg-bar-label", text: i.label, title: i.label }),
        el("div", { class: "seg-bar-pair" },
          el("div", { class: "seg-bar seg" }, el("span", { style: `width:${Math.max(0.5, ((i.seg ?? 0) / max) * 100)}%` })),
          el("div", { class: "seg-bar rest" }, el("span", { style: `width:${Math.max(0.5, ((i.rest ?? 0) / max) * 100)}%` }))),
        el("span", { class: "seg-bar-value mono", text: `${i.fmt(i.seg)} · ${i.fmt(i.rest)}` }))));
}

function segmentView(res) {
  const found = res.columns.some((c) => c.significant);
  const head = el("div", { class: `test-verdict ${found ? "found" : "none"}` },
    el("div", { class: "test-verdict-label", text: found ? "The segment stands out" : "No clear differences" }),
    el("p", { class: "test-sentence", text: `${res.summary} Segment: ${res.label} (${fmt(res.segmentRows)} rows) vs the other ${fmt(res.restRows)} rows.` }));
  const legend = el("div", { class: "trend-legend muted" },
    el("span", { class: "trend-key seg-key" }), "segment", el("span", { class: "trend-key rest-key" }), "rest");
  const rows = res.columns.map((c) => {
    const pct = (v) => fmtPct((v ?? 0) * 100);
    const bars = c.kind === "numeric"
      ? pairBars([{ label: "mean", seg: c.segment.mean, rest: c.rest.mean, fmt: fnum },
        { label: "median", seg: c.segment.median, rest: c.rest.median, fmt: fnum }])
      : pairBars(c.shares.map((s) => ({ label: s.value, seg: s.segment, rest: s.rest, fmt: pct })));
    return el("div", { class: `seg-row ${c.significant ? "" : "dim"}` },
      el("div", { class: "tgt-main" },
        el("div", { class: "tgt-head" },
          el("span", { class: "tgt-name", text: c.column, title: c.column }),
          el("span", { class: "chip", text: c.kind === "numeric" ? "number" : "category" }),
          el("span", { class: `tgt-strength ${c.significant ? "good-text" : ""}`, text: c.significant ? "differs" : "not clear" })),
        el("p", { class: "tgt-sentence", text: c.sentence }),
        el("div", { class: "tgt-meta muted" },
          trf("{0} · adjusted p {1} · {2} {3} · n = {4} / {5}", tr(c.test), pText(c.pAdjusted), tr(c.effectName), c.effect.toFixed(2), fmt(c.segment.n), fmt(c.rest.n)))),
      bars);
  });
  const list = el("div", { class: "card seg-card" },
    el("div", { class: "seg-head" }, el("h2", { text: "Column by column" }), legend),
    el("p", { class: "card-hint", text: "Clear differences first, strongest at the top. " + res.caveats.join(" ") }),
    rows.length ? el("div", { class: "tgt-list" }, rows) : note("info", "No other column could be compared."));
  const skipped = res.skipped.length
    ? el("details", { class: "card tgt-skipped" },
      el("summary", { text: `Skipped columns (${res.skipped.length})` }),
      el("ul", {}, res.skipped.map((k) => el("li", {}, el("strong", { text: k.column }), ` — ${k.reason}`))))
    : null;
  return el("div", { class: "test-body" }, head, list, skipped);
}

function showSegmentCode() {
  if (!app.segment) return;
  openCodeDialog("Segment as pandas code", "Rebuilds your data, splits off the segment and shows how to test a column.", app.segment.code, "segment.py");
}

/* ---- trends ------------------------------------------------------------ */

let trendValues = {};
let trendTimer = null;
let trendSeq = 0;

function renderTrendFields(run = false) {
  const memory = (app.forms.trends ||= {});
  const dates = datetimeCols();
  if (!dates.length) {
    $("trend-fields").replaceChildren(el("p", { class: "muted no-inputs",
      text: "No date columns yet. Use Convert to date in Clean on the column that holds dates." }),
      el("button", { class: "btn btn-sm", onclick: () => openFix({ method: "TO_DATETIME", label: "Convert to date" }) },
        icon("i-clean"), "Convert to date…"));
    $("trend-actions").hidden = true;
    $("trend-sub").textContent = tr("");
    $("trend-output").replaceChildren(note("info", "Trends need a date column."));
    app.trendStale = false;
    return;
  }
  const counting = !memory.value;
  const specs = [
    { key: "date", label: "Date column", type: "select", options: dates },
    { key: "value", label: "Value", type: "select", rerender: true,
      options: [{ value: "", label: "Number of rows" }, ...allCols().filter((c) => !dates.includes(c))], default: numericCols()[0] || "" },
  ];
  if (!counting) {
    specs.push({ key: "agg", label: "Combine with", type: "select", default: "sum",
      options: toOptions([["sum", "Sum"], ["mean", "Mean"], ["median", "Median"], ["min", "Min"], ["max", "Max"], ["count", "Count (non-empty)"], ["nunique", "Distinct values"]]) });
  }
  specs.push(
    { key: "freq", label: "Period", type: "select", default: "M",
      options: toOptions([["D", "Day"], ["W", "Week"], ["M", "Month"], ["Q", "Quarter"], ["Y", "Year"]]) },
    { key: "compare", label: "Compare with", type: "select",
      options: toOptions([["previous", "Previous period"], ["year", "Same period last year"]]) },
    { key: "window", label: "Moving average", type: "select", default: "3",
      options: toOptions([["0", "None"], ["3", "3 periods"], ["6", "6 periods"], ["12", "12 periods"]]) },
  );
  const rerender = new Set(specs.filter((x) => x.rerender).map((x) => x.key));
  trendValues = buildForm($("trend-fields"), specs, memory, (values, key) => {
    trendValues = values;
    if (key && rerender.has(key)) return renderTrendFields(true);
    scheduleTrend();
  });
  if (run) scheduleTrend(0);
}

function trendParams(v) {
  return { date: v.date, value: v.value || null, agg: v.value ? v.agg || "sum" : "count", freq: v.freq || "M",
    compare: v.compare || "previous", window: Number(v.window || 0) };
}

function scheduleTrend(delay = 250) {
  clearTimeout(trendTimer);
  app.trendStale = false;
  trendTimer = setTimeout(runTrend, delay);
}

async function runTrend() {
  if (!app.state || !trendValues.date) return;
  const seq = ++trendSeq;
  const out = $("trend-output");
  const params = trendParams(trendValues);
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Calculating…");
  const showLoading = setTimeout(() => seq === trendSeq && out.replaceChildren(loading), 150);
  const hideCancel = delayedCancel(loading, "trends", () => seq === trendSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("trends", "trends", { params });
    if (seq !== trendSeq) return;
    app.trend = { params, res };
    $("trend-sub").textContent = `${trf("{0} per {1}", tr(res.label), tr(res.unit))}${res.compare === "year" ? ` · ${tr("vs a year earlier")}` : ""}`;
    $("trend-actions").hidden = false;
    out.replaceChildren(trendView(res));
  } catch (err) {
    if (seq !== trendSeq || isCancelled(err)) return;
    app.trend = null;
    $("trend-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}

const rowsOf = (t) => t.data.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])));

function trendChart(rows, hasAvg) {
  const W = 800, H = 240, L = 56, R = 12, T = 12, B = 30;
  const vals = rows.flatMap((r) => [r.value, hasAvg ? r.movingAvg : null]).filter((v) => v != null);
  if (!vals.length) return null;
  let lo = Math.min(0, ...vals), hi = Math.max(...vals);
  if (hi === lo) hi = lo + 1;
  const x = (i) => L + (rows.length === 1 ? 0 : (i / (rows.length - 1)) * (W - L - R));
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const ns = "http://www.w3.org/2000/svg";
  const svg = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = tr(text);
    return n;
  };
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "trend-svg", role: "img", "aria-label": "Trend chart" });
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    root.append(svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "trend-grid" }),
      svg("text", { x: L - 8, y: y(v) + 4, class: "trend-axis", "text-anchor": "end" }, fnum(v)));
  }
  const ticks = [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])];
  for (const i of ticks) {
    root.append(svg("text", { x: x(i), y: H - 8, class: "trend-axis", "text-anchor": i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle" }, rows[i].period));
  }
  const path = (key) => rows.map((r, i) => (r[key] == null ? null : `${x(i)},${y(r[key])}`)).filter(Boolean).join(" ");
  root.append(svg("polyline", { points: path("value"), class: "trend-line" }));
  if (hasAvg) root.append(svg("polyline", { points: path("movingAvg"), class: "trend-avg" }));
  if (rows.length <= 120) {
    rows.forEach((r, i) => {
      if (r.value == null) return;
      const dot = svg("circle", { cx: x(i), cy: y(r.value), r: 3.5, class: r.complete ? "trend-dot" : "trend-dot partial" });
      dot.append(svg("title", {}, `${r.period}: ${fnum(r.value)}${r.complete ? "" : " (incomplete)"}`));
      root.append(dot);
    });
  }
  return root;
}

function trendView(res) {
  const rows = rowsOf(res.table);
  const hasAvg = res.table.columns.includes("movingAvg");
  const hasTotal = res.table.columns.includes("runningTotal");
  const insights = el("div", { class: "test-verdict trend-insights" },
    el("div", { class: "test-verdict-label", text: "What changed" }),
    el("ul", {}, res.insights.map((t) => el("li", { text: t }))));
  const legend = el("div", { class: "trend-legend muted" },
    el("span", { class: "trend-key value" }), res.label,
    hasAvg ? el("span", { class: "trend-key avg" }) : null, hasAvg ? `${res.window}-${res.unit} moving average` : null,
    rows.some((r) => !r.complete) ? el("span", { class: "trend-key partial" }) : null,
    rows.some((r) => !r.complete) ? "incomplete period" : null);
  const chart = el("div", { class: "trend-chart" }, trendChart(rows, hasAvg), legend);
  const heads = ["Period", "Value", "Change", "Change %", hasAvg ? "Moving avg" : null, hasTotal ? "Running total" : null].filter(Boolean);
  const body = rows.slice().reverse().map((r) =>
    el("tr", { class: r.complete ? null : "muted" },
      el("td", { text: r.period + (r.complete ? "" : " *") }),
      el("td", { class: "num", text: fnum(r.value) }),
      el("td", { class: `num ${r.change > 0 ? "good-text" : r.change < 0 ? "bad-text" : "muted"}`, text: r.change == null ? "—" : (r.change > 0 ? "+" : "") + fnum(r.change) }),
      el("td", { class: `num ${r.changePct > 0 ? "good-text" : r.changePct < 0 ? "bad-text" : "muted"}`,
        text: r.changePct == null ? "—" : `${r.changePct > 0 ? "+" : ""}${r.changePct.toFixed(1)}%` }),
      hasAvg ? el("td", { class: "num muted", text: fnum(r.movingAvg) }) : null,
      hasTotal ? el("td", { class: "num muted", text: fnum(r.runningTotal) }) : null));
  const tableCard = el("div", { class: "table-wrap trend-table" },
    el("table", { class: "test-table" },
      el("thead", {}, el("tr", {}, heads.map((h, i) => el("th", { text: h, class: i ? "num" : null })))),
      el("tbody", {}, body)));
  const notes = res.notes.length ? el("div", { class: "chart-footnotes" }, res.notes.map((t) => el("p", { text: t }))) : null;
  return el("div", { class: "test-body" }, insights, chart, tableCard, notes);
}

function showTrendCode() {
  if (!app.trend) return;
  openCodeDialog("Trend table as pandas code", "Rebuilds your data and the same period table.", app.trend.res.code, "trend.py");
}

const testable = () => app.state.columns.filter((c) => c.kind !== "other").map((c) => c.name);
const kindOf = (name) => (app.state.columns.find((c) => c.name === name) || {}).kind;
/** The column whose values form the groups, if either side is a category. */
function testGroupColumn(v) {
  if (v.by && kindOf(v.by) !== "numeric") return v.by;
  if (v.outcome && kindOf(v.outcome) !== "numeric") return v.outcome === v.by ? null : v.outcome;
  return null;
}

let testValues = {};
let testTimer = null;
let testSeq = 0;
const testGroupCache = new Map();

function renderTestFields(run = false) {
  const memory = (app.forms.tests ||= {});
  const cols = testable();
  const num = numericCols();
  const groups = groupCols();
  const specs = [
    { key: "outcome", label: "Measure", type: "select", options: cols, default: num[0] || cols[0], rerender: true,
      hint: "The value you want to compare, e.g. fee or rating." },
    { key: "by", label: "Compare by", type: "select", options: cols, default: groups[0] || cols.find((c) => c !== (memory.outcome || num[0])),
      rerender: true, hint: "Groups (a category) or a second number to correlate with." },
  ];
  const draft = { outcome: memory.outcome ?? specs[0].default, by: memory.by ?? specs[1].default };
  const groupCol = testGroupColumn(draft);
  const cached = groupCol && testGroupCache.get(groupCol);
  if (groupCol && cached) {
    specs.push({ key: `groups:${groupCol}`, label: `Only these groups of ${groupCol} (optional)`, type: "multi",
      options: cached.values.map((g) => ({ value: g.value, label: `${g.value} (${fmt(g.count)})` })),
      hint: cached.total > cached.values.length ? `Showing the ${cached.values.length} most common of ${fmt(cached.total)}.` : "Leave empty to compare all groups." });
  }
  testValues = buildForm($("test-fields"), specs, memory, (values, key) => {
    testValues = values;
    if (key === "outcome" || key === "by") return renderTestFields(true);
    scheduleTest();
  });
  if (groupCol && !cached) {
    call("stats_groups", { column: groupCol })
      .then((res) => { testGroupCache.set(groupCol, res); if (app.analyzeTab === "tests") renderTestFields(false); })
      .catch(() => {});
  }
  if (run) scheduleTest(0);
}

function testParams(v) {
  const groupCol = testGroupColumn(v);
  const groups = groupCol ? v[`groups:${groupCol}`] || [] : [];
  return { outcome: v.outcome, by: v.by, groups: groups.length ? groups : null };
}

function scheduleTest(delay = 250) {
  clearTimeout(testTimer);
  app.testStale = false;
  if (!testValues.outcome || !testValues.by || testValues.outcome === testValues.by) {
    $("test-actions").hidden = true;
    $("test-name").textContent = tr("Statistical test");
    $("test-question").textContent = tr("");
    $("test-output").replaceChildren(note("info", "Pick two different columns."));
    return;
  }
  testTimer = setTimeout(runTest, delay);
}

async function runTest() {
  if (!app.state) return;
  const seq = ++testSeq;
  const out = $("test-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Running the test…");
  const showLoading = setTimeout(() => seq === testSeq && out.replaceChildren(loading), 150);
  const hideCancel = delayedCancel(loading, "stats", () => seq === testSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("stats", "stats_test", testParams(testValues));
    if (seq !== testSeq) return;
    app.test = res;
    $("test-name").textContent = tr(res.test);
    $("test-question").textContent = tr(res.question);
    $("test-actions").hidden = false;
    out.replaceChildren(testResult(res));
  } catch (err) {
    if (seq !== testSeq || isCancelled(err)) return;
    app.test = null;
    $("test-actions").hidden = true;
    $("test-name").textContent = tr("Statistical test");
    $("test-question").textContent = tr("");
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    clearTimeout(showLoading);
    hideCancel();
  }
}

const pText = (p) => (p == null ? "—" : p < 0.001 ? "< 0.001" : p < 0.01 ? p.toFixed(3) : p.toFixed(2));

/** A row of CI whiskers on one shared scale. */
function whiskers(rows, est, lo, hi, format = fnum) {
  const vals = rows.flatMap((r) => [r[lo], r[hi], r[est]]).filter((v) => v != null);
  const min = Math.min(...vals);
  const span = Math.max(...vals) - min || 1;
  const pos = (v) => `${((v - min) / span) * 100}%`;
  return (r) =>
    el("div", { class: "whisker", title: `${format(r[est])} (95% CI ${format(r[lo])} … ${format(r[hi])})` },
      r[lo] != null ? el("span", { class: "whisker-line", style: `left:${pos(r[lo])};right:calc(100% - ${pos(r[hi])})` }) : null,
      el("span", { class: "whisker-dot", style: `left:${pos(r[est])}` }));
}

function testResult(res) {
  const found = res.significant;
  const what = res.kind === "groups" ? "difference" : "relationship";
  const verdict = el(
    "div",
    { class: `test-verdict ${found ? "found" : "none"}` },
    el("div", { class: "test-verdict-label", text: found ? `A ${what} beyond chance` : `No clear ${what}` }),
    el("p", { class: "test-sentence", text: res.interpretation })
  );
  const eff = res.effect;
  const tiles = el(
    "div",
    { class: "stats test-tiles" },
    stat("p-value", pText(res.p), found ? `below ${res.alpha}: unlikely to be chance alone` : `${res.alpha} or above: could be chance`,
      found ? "good" : ""),
    stat(eff.name, eff.value == null ? "—" : (eff.value > 0 && res.kind === "correlation" ? "+" : "") + eff.value.toFixed(2),
      `${tr(eff.size)} · ${tr(eff.explain)}`),
    res.ci
      ? stat("95% confidence interval", `${fnum(res.ci.low)} … ${fnum(res.ci.high)}`, res.ci.label)
      : stat("Rows used", fmt(res.n), res.dropped ? `${fmt(res.dropped)} left out (empty values)` : "No rows left out")
  );

  const statLine = res.statistic
    ? `${res.statistic.name} = ${fnum(res.statistic.value)}${res.df != null ? `, df = ${Array.isArray(res.df) ? res.df.map(fnum).join(", ") : fnum(res.df)}` : ""}, n = ${fmt(res.n)}`
    : "";
  const why = el(
    "div",
    { class: "test-why" },
    el("h3", { text: "Why this test" }),
    el("ul", {}, res.why.map((w) => el("li", { text: w[0].toUpperCase() + w.slice(1) + "." }))),
    el("div", { class: "test-checks" },
      res.checks.map((c) =>
        el("div", { class: `test-check ${c.ok ? "ok" : "warn"}` },
          el("span", { class: "test-check-mark", text: c.ok ? "✓" : "!" }),
          el("div", {}, el("strong", { text: c.name }), el("span", { class: "muted", text: ` — ${c.detail}` }))))),
    statLine ? el("p", { class: "test-stat mono muted", text: statLine }) : null
  );

  let detail = null;
  if (res.groups) {
    const w = whiskers(res.groups, "mean", "ciLow", "ciHigh");
    detail = el("div", { class: "table-wrap" },
      el("table", { class: "test-table" },
        el("thead", {}, el("tr", {}, ["Group", "n", "Mean", "95% CI of mean", "", "Median", "Std dev"].map((h, i) =>
          el("th", { text: h, class: [1, 2, 5, 6].includes(i) ? "num" : null })))),
        el("tbody", {}, res.groups.map((g) =>
          el("tr", {},
            el("td", { text: g.group }), el("td", { class: "num", text: fmt(g.n) }), el("td", { class: "num", text: fnum(g.mean) }),
            el("td", { class: "mono muted", text: g.ciLow == null ? "—" : `${fnum(g.ciLow)} … ${fnum(g.ciHigh)}` }),
            el("td", { class: "whisker-cell" }, w(g)),
            el("td", { class: "num", text: fnum(g.median) }), el("td", { class: "num", text: fnum(g.std) }))))));
  } else if (res.shares) {
    const pct = (v) => fmtPct(v * 100);
    const w = whiskers(res.shares, "share", "ciLow", "ciHigh", pct);
    detail = el("div", { class: "table-wrap" },
      el("table", { class: "test-table" },
        el("thead", {}, el("tr", {}, [res.by, "n", `% ${res.outcome} = ${res.focus}`, "95% CI", ""].map((h, i) =>
          el("th", { text: h, class: [1, 2].includes(i) ? "num" : null })))),
        el("tbody", {}, res.shares.map((g) =>
          el("tr", {},
            el("td", { text: g.group }), el("td", { class: "num", text: fmt(g.n) }), el("td", { class: "num", text: pct(g.share) }),
            el("td", { class: "mono muted", text: `${pct(g.ciLow)} … ${pct(g.ciHigh)}` }),
            el("td", { class: "whisker-cell" }, w(g)))))));
  }
  const pairwise = res.pairwise
    ? el("div", {},
      el("h3", { text: "Which groups differ" }),
      el("p", { class: "card-hint", text: `${res.pairwise.test} for each pair, p-values adjusted with the ${res.pairwise.correction} method.` }),
      el("div", { class: "table-wrap" },
        el("table", { class: "test-table" },
          el("thead", {}, el("tr", {}, ["Pair", "p", "Adjusted p", ""].map((h, i) => el("th", { text: h, class: i && i < 3 ? "num" : null })))),
          el("tbody", {}, res.pairwise.rows.map((r) =>
            el("tr", {},
              el("td", { text: `${r.a} vs ${r.b}` }), el("td", { class: "num muted", text: pText(r.p) }),
              el("td", { class: "num", text: pText(r.pAdjusted) }),
              el("td", { class: r.significant ? "good-text" : "muted", text: r.significant ? "differ" : "not clear" })))))))
    : null;
  const caveats = el("div", { class: "test-caveats" },
    el("h3", { text: "Keep in mind" }),
    el("ul", {}, res.caveats.map((c) => el("li", { text: c }))));
  return el("div", {}, verdict, tiles, el("div", { class: "test-body" }, why, detail, pairwise, caveats));
}

function showTestCode() {
  if (!app.test) return;
  openCodeDialog(`${app.test.test} as Python code`, "Rebuilds your data and runs the same test with scipy.", app.test.code, "statistical_test.py");
}

/* ---- chart of the pivot ----------------------------------------------- */

function renderPivotChartFields() {
  const res = app.pivot && app.pivot.res;
  if (!res) return;
  const box = $("pivot-chart-fields");
  if (res.rows.length !== 1) {
    box.replaceChildren();
    $("pivot-chart-output").replaceChildren(note("info", "Charts work with exactly one row grouping."));
    $("pivot-chart-insights").hidden = true;
    return;
  }
  const values = res.valueColumns;
  if (!values.includes(app.pivotChartValue)) app.pivotChartValue = values.includes("Total") ? "Total" : values[0];
  const select = el("select", { "aria-label": "Value to chart", onchange: (e) => { app.pivotChartValue = e.target.value; drawPivotChart(); } },
    values.map((v) => el("option", { value: v, text: v })));
  select.value = app.pivotChartValue;
  box.replaceChildren(select);
  drawPivotChart();
}

let pivotChartSeq = 0;

async function drawPivotChart() {
  if (!app.pivot) return;
  const seq = ++pivotChartSeq;
  $("pivot-chart-loading").hidden = false;
  $("pivot-chart-stage").classList.add("busy-stage");
  try {
    const res = await callLatest("pivot_chart", "pivot_chart", {
      params: app.pivot.params,
      value: app.pivotChartValue,
      style: chartStyle(),
      width: Math.max(600, $("pivot-chart-stage").clientWidth - 32),
    });
    if (seq !== pivotChartSeq) return;
    $("pivot-chart-output").replaceChildren(el("img", { src: res.image, alt: `Bar chart of ${app.pivotChartValue}` }));
    const box = $("pivot-chart-insights");
    box.hidden = !res.insights.length;
    box.replaceChildren(el("div", { class: "insights" },
      el("div", { class: "insights-title" }, icon("i-bulb"), "What this shows"),
      el("ul", {}, res.insights.map((t) => el("li", { text: t })))));
  } catch (err) {
    if (seq !== pivotChartSeq || isCancelled(err)) return;
    $("pivot-chart-output").replaceChildren(note("error", cleanError(err)));
    $("pivot-chart-insights").hidden = true;
  } finally {
    if (seq === pivotChartSeq) {
      $("pivot-chart-loading").hidden = true;
      $("pivot-chart-stage").classList.remove("busy-stage");
    }
  }
}

function togglePivotChart() {
  const card = $("pivot-chart-card");
  card.hidden = !card.hidden;
  if (!card.hidden) {
    renderPivotChartFields();
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

/* ------------------------------------------------------------------ */
/* visualize                                                            */
/* ------------------------------------------------------------------ */

let chartValues = {};

/** Column name as a SQL identifier (quoted when needed), matching src/query.quote_ident. */
const SQL_KEYWORDS = new Set(["select", "from", "where", "group", "order", "by", "limit", "table"]);
const sqlName = (name) =>
  /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) && !SQL_KEYWORDS.has(name.toLowerCase()) ? name : `"${String(name).replace(/"/g, '""')}"`;

const datetimeCols = () => app.state.columns.filter((c) => c.dtype.startsWith("datetime")).map((c) => c.name);
function uniqueOf(name) {
  const p = app.state.profile;
  const iCol = p.columns.indexOf("Column");
  const iUni = p.columns.indexOf("Unique");
  const row = p.data.find((r) => String(r[iCol]) === name);
  return row ? row[iUni] : 0;
}
/** Text columns that make sensible groups (2–50 distinct values), most useful first. */
const groupCols = () =>
  categoricalCols()
    .filter((c) => uniqueOf(c) >= 2 && uniqueOf(c) <= 50)
    .sort((a, b) => missingOf(a) - missingOf(b) || uniqueOf(a) - uniqueOf(b));

const TOGGLE = (key, label, def = false, hint) => ({ key, label, type: "toggle", default: def, hint });
const TITLE = { key: "title", label: "Title (optional)", type: "text" };

function chartSpecs(kind, memory) {
  const num = numericCols();
  const cat = categoricalCols();
  const groups = groupCols();
  const none = { value: "", label: "None" };
  const hueOpts = [none, ...groups];
  switch (kind) {
    case "HIST":
      if (!num.length) return { error: "No numeric columns to draw a histogram." };
      return { fields: [
        { key: "column", label: "Column", type: "select", options: num },
        { key: "bins", label: "Bins", type: "select", options: toOptions([["auto", "Automatic"], ["10", "10"], ["20", "20"], ["30", "30"], ["50", "50"]]) },
        { key: "hue", label: "Split by", type: "select", options: hueOpts },
        TOGGLE("kde", "Smooth density curve", true),
        TITLE,
      ] };
    case "BOX":
      if (!num.length) return { error: "Need at least one numeric column for a box plot." };
      return { fields: [
        { key: "y", label: "Values", type: "select", options: num },
        { key: "x", label: "Group by", type: "select", options: [none, ...groups], default: groups[0] || "" },
        { key: "top_n", label: "Max groups", type: "select", options: ["5", "8", "12", "20"], default: "12" },
        TOGGLE("log", "Log scale", false, "Helps when a few values are much larger than the rest."),
        TITLE,
      ] };
    case "SCAT":
      if (num.length < 2) return { error: "Need at least two numeric columns for a scatter plot." };
      return { fields: [
        { key: "x", label: "X axis", type: "select", options: num, default: num[0] },
        { key: "y", label: "Y axis", type: "select", options: num, default: num[1] },
        { key: "hue", label: "Color by", type: "select", options: hueOpts },
        TOGGLE("trend", "Trend line", true),
        TOGGLE("log_x", "Log scale on X"),
        TOGGLE("log_y", "Log scale on Y"),
        TITLE,
      ] };
    case "HEAT":
      if (num.length < 2) return { error: "Need at least two numeric columns for a correlation heatmap." };
      return { fields: [
        { key: "columns", label: "Columns", type: "multi", options: num, default: num.slice(0, 12) },
        { key: "method", label: "Method", type: "select", options: toOptions([["pearson", "Pearson (linear)"], ["spearman", "Spearman (rank)"]]) },
        TITLE,
      ] };
    case "LINE": {
      if (!num.length) return { error: "Need a numeric column for the Y axis." };
      const dts = datetimeCols();
      const x = allCols().includes(memory.x) ? memory.x : dts[0] || allCols()[0];
      const fields = [
        { key: "x", label: "X axis", type: "select", options: allCols(), default: x, rerender: true,
          hint: dts.length ? null : "Tip: convert a date column in Clean → Convert to date to get time grouping." },
        { key: "y", label: "Y axis", type: "select", options: num },
      ];
      if (dts.includes(x)) {
        fields.push({ key: "freq", label: "Group dates by", type: "select", default: "M",
          options: toOptions([["D", "Day"], ["W", "Week"], ["M", "Month"], ["Q", "Quarter"], ["Y", "Year"]]) });
      }
      fields.push({ key: "agg", label: "Combine values with", type: "select",
        options: toOptions([["mean", "Mean"], ["sum", "Sum"], ["median", "Median"], ["count", "Count"], ["min", "Min"], ["max", "Max"], ["none", "Don't combine (raw)"]]) });
      fields.push(TITLE);
      return { fields };
    }
    case "BAR": {
      if (!cat.length) return { error: "Need a text or category column for the bars." };
      const fields = [
        { key: "x", label: "Bars (categories)", type: "select", options: cat, default: groups[0] },
        { key: "y", label: "Bar height", type: "select", options: [{ value: "", label: "Number of rows" }, ...num], default: num[0] || "", rerender: true },
      ];
      if (memory.y !== "" && num.length) {
        fields.push({ key: "agg", label: "Combine with", type: "select",
          options: toOptions([["mean", "Mean"], ["sum", "Sum"], ["median", "Median"], ["min", "Min"], ["max", "Max"]]) });
      }
      fields.push(
        { key: "top_n", label: "Show top", type: "select", options: ["5", "10", "15", "25", "50"], default: "15" },
        { key: "sort", label: "Order", type: "select", options: toOptions([["desc", "Largest first"], ["asc", "Smallest first"], ["label", "Alphabetical"]]) },
        { key: "horizontal", label: "Direction", type: "select", options: toOptions([["auto", "Automatic"], ["true", "Horizontal bars"], ["false", "Vertical bars"]]) },
        TOGGLE("labels", "Value labels", true),
        TITLE
      );
      return { fields };
    }
    case "COUNT":
      return { fields: [
        { key: "column", label: "Column", type: "select", options: allCols(), default: groups[0] || cat[0] },
        { key: "top_n", label: "Show top", type: "select", options: ["5", "10", "15", "25", "50"], default: "15" },
        { key: "sort", label: "Order", type: "select", options: toOptions([["desc", "Most common first"], ["asc", "Least common first"], ["label", "Alphabetical"]]) },
        { key: "horizontal", label: "Direction", type: "select", options: toOptions([["auto", "Automatic"], ["true", "Horizontal bars"], ["false", "Vertical bars"]]) },
        TOGGLE("percent", "Show percentages"),
        TITLE,
      ] };
    case "PAIR":
      if (num.length < 2) return { error: "Need at least two numeric columns for a pair plot." };
      return { fields: [
        { key: "columns", label: "Columns", type: "multi", options: num, default: num.slice(0, 4) },
        { key: "hue", label: "Color by", type: "select", options: hueOpts },
        TITLE,
      ] };
    default:
      return { fields: [] };
  }
}

function chartParams(kind, v) {
  const p = { ...v };
  if ("horizontal" in p) p.horizontal = p.horizontal === "auto" ? "auto" : p.horizontal === "true";
  if (kind === "BAR" && !p.y) delete p.agg;
  if (kind === "LINE" && !datetimeCols().includes(p.x)) delete p.freq;
  for (const k of Object.keys(p)) if (p[k] === "" || p[k] == null) delete p[k];
  return p;
}

function chartInvalid(kind, v) {
  if ((kind === "HEAT" || kind === "PAIR") && !(v.columns && v.columns.length >= 2)) return "Select at least two columns.";
  if (kind === "SCAT" && v.x === v.y) return "Choose two different columns.";
  return "";
}

function renderChartTiles() {
  $("chart-types").replaceChildren(
    ...CHART_TYPES.map((t) =>
      el("button", {
        class: "chart-tile",
        role: "radio",
        "aria-checked": String(t.kind === app.chartKind),
        title: t.hint,
        onclick: () => selectChart(t.kind),
      }, icon(t.icon), t.label)
    )
  );
}

function selectChart(kind, params) {
  if (params) app.forms.chart[kind] = { ...params };
  app.chartKind = kind;
  renderChartTiles();
  renderChartFields(true);
}

const chartLabel = () => tr((CHART_TYPES.find((t) => t.kind === app.chartKind) || { label: "Chart" }).label);

function chartSubtitle(kind, v) {
  const by = (a, b) => (b ? trf("{0} by {1}", a, b) : a);
  const of = (a, col) => trf(`${a} of {0}`, col);
  switch (kind) {
    case "HIST": return by(v.column, v.hue);
    case "BOX": return by(v.y, v.x);
    case "SCAT": return v.hue ? trf("{0} vs {1}, colored by {2}", v.y, v.x, v.hue) : trf("{0} vs {1}", v.y, v.x);
    case "HEAT": return trf("{0} columns · {1}", (v.columns || []).length, v.method || "pearson");
    case "LINE": return v.agg && v.agg !== "none" ? trf("{0} over {1}", of(v.agg, v.y), v.x) : trf("{0} over {1}", v.y, v.x);
    case "BAR": return v.y ? trf("{0} by {1}", of(v.agg || "mean", v.y), v.x) : trf("rows per {0}", v.x);
    case "COUNT": return trf("values in {0}", v.column);
    case "PAIR": return (v.columns || []).join(", ");
    default: return "";
  }
}

/** Build the settings form. Renders only when the Visualize screen is visible. */
function renderChartFields(render = false) {
  const kind = app.chartKind;
  $("chart-config").hidden = !kind;
  if (!kind) {
    renderChartEmpty();
    return;
  }
  const memory = (app.forms.chart[kind] ||= {});
  const spec = chartSpecs(kind, memory);
  if (spec.error) {
    $("chart-fields").replaceChildren(note("warn", spec.error));
    showChartMessage("warn", spec.error);
    return;
  }
  const rerenderKeys = new Set(spec.fields.filter((f) => f.rerender).map((f) => f.key));
  const update = (values, changedKey) => {
    chartValues = values;
    if (changedKey && rerenderKeys.has(changedKey)) {
      renderChartFields(true);
      return;
    }
    scheduleRender(changedKey === "title" ? 650 : 300);
  };
  chartValues = buildForm($("chart-fields"), spec.fields, memory, update);
  if (render || app.section === "visualize") scheduleRender(0);
  else app.chartStale = true;
}

/* ---- rendering ------------------------------------------------------ */

let renderTimer = null;
let renderSeq = 0;

function scheduleRender(delay = 300) {
  clearTimeout(renderTimer);
  const reason = chartInvalid(app.chartKind, chartValues);
  if (reason) {
    showChartMessage("info", reason);
    return;
  }
  renderTimer = setTimeout(generateChart, delay);
}

/** Theme colours handed to Matplotlib so charts match the UI. */
function chartStyle() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    surface: v("--surface"),
    text: v("--text"),
    muted: v("--muted"),
    border: v("--border"),
    positive: v("--primary"),
    negative: v("--danger"),
    palette: [1, 2, 3, 4, 5, 6].map((i) => v(`--chart-${i}`)),
  };
}

function setChartHeading(kind, values) {
  $("viz-kind").textContent = tr(kind ? chartLabel() : "No chart yet");
  $("viz-sub").textContent = tr(kind ? chartSubtitle(kind, values) : "");
}

function showChartMessage(kind, text) {
  $("viz-loading").hidden = true;
  $("viz-actions").hidden = true;
  $("viz-insights").hidden = true;
  app.chartImage = null;
  if (typeof disposeEchart === "function") disposeEchart();
  setChartHeading(app.chartKind, chartValues);
  $("chart-output").replaceChildren(el("div", { class: "viz-message" }, note(kind, text)));
}

async function generateChart() {
  if (!app.state || !app.chartKind) return;
  const seq = ++renderSeq;
  const kind = app.chartKind;
  const params = chartParams(kind, chartValues);
  app.chartStale = false;
  $("viz-loading").hidden = false;
  $("chart-stage").classList.add("busy-stage");
  const hideCancel = delayedCancel($("viz-loading"), "plot", () => {
    if (seq !== renderSeq) return;
    renderSeq++; // invalidate this render
    $("chart-stage").classList.remove("busy-stage");
    showChartMessage("info", "Chart cancelled. Change a setting to draw it again.");
  });
  try {
    const width = Math.max(600, $("chart-stage").clientWidth - 32);
    const res = await callLatest("plot", "plot", { kind, params, style: chartStyle(), width });
    if (seq !== renderSeq) return; // a newer render is on its way
    app.chartImage = res.image;
    app.chartCode = res.code;
    app.chartParams = params;
    setChartHeading(kind, chartValues);
    app.chartSpec = res.spec;
    showChartView();
    renderInsights(res.insights, res.notes);
    $("viz-actions").hidden = false;
    rememberChart(kind, { ...chartValues }, res.image);
  } catch (err) {
    if (seq !== renderSeq || isCancelled(err)) return;
    showChartMessage("error", cleanError(err));
  } finally {
    hideCancel();
    if (seq === renderSeq) {
      $("viz-loading").hidden = true;
      $("chart-stage").classList.remove("busy-stage");
    }
  }
}

function renderInsights(insights, notes) {
  const box = $("viz-insights");
  box.hidden = !insights.length && !notes.length;
  box.replaceChildren(
    ...[
    insights.length
      ? el("div", { class: "insights" },
          el("div", { class: "insights-title" }, icon("i-bulb"), "What this shows"),
          el("ul", {}, insights.map((t) => el("li", { text: t }))))
      : null,
    notes.length ? el("div", { class: "chart-footnotes" }, notes.map((t) => el("p", { text: t }))) : null,
    ].filter(Boolean)
  );
}

/* ---- empty state with suggestions ---------------------------------- */

function chartSuggestions() {
  const num = numericCols();
  const groups = groupCols();
  const dts = datetimeCols();
  const out = [];
  const spread = [...num].sort((a, b) => uniqueOf(b) - uniqueOf(a));
  if (spread[0]) out.push({ kind: "HIST", text: `Distribution of ${spread[0]}`, params: { column: spread[0] } });
  if (groups[0]) out.push({ kind: "COUNT", text: `Most common ${groups[0]}`, params: { column: groups[0] } });
  if (num[0] && groups[0]) out.push({ kind: "BOX", text: `${num[0]} across ${groups[0]}`, params: { y: num[0], x: groups[0] } });
  if (num.length >= 2) out.push({ kind: "SCAT", text: `${spread[1] || num[1]} vs ${spread[0]}`, params: { x: spread[0], y: spread[1] || num[1] } });
  if (dts[0] && num[0]) out.push({ kind: "LINE", text: `${num[0]} over time`, params: { x: dts[0], y: num[0], freq: "M" } });
  if (num.length >= 3) out.push({ kind: "HEAT", text: "How numeric columns relate", params: {} });
  return out.slice(0, 5);
}

function renderChartEmpty() {
  app.chartImage = null;
  if (typeof disposeEchart === "function") disposeEchart();
  $("viz-actions").hidden = true;
  $("viz-insights").hidden = true;
  setChartHeading("", {});
  const ideas = app.state ? chartSuggestions() : [];
  $("chart-output").replaceChildren(
    el("div", { class: "viz-empty" },
      el("div", { class: "viz-empty-icon" }, icon("i-chart")),
      el("h2", { text: "Pick a chart type" }),
      el("p", { text: ideas.length ? "Or start from a suggestion based on your columns:" : "Choose one on the left." }),
      ideas.length
        ? el("div", { class: "suggestions" },
            ideas.map((s) => {
              const t = CHART_TYPES.find((c) => c.kind === s.kind);
              return el("button", { class: "suggestion", onclick: () => selectChart(s.kind, s.params) },
                icon(t.icon), el("span", {}, el("strong", { text: t.label }), el("span", { text: s.text })));
            }))
        : null)
  );
}

/* ---- recent charts --------------------------------------------------- */

function rememberChart(kind, values, image) {
  const key = JSON.stringify([kind, values]);
  app.recent = (app.recent || []).filter((r) => r.key !== key);
  app.recent.unshift({ key, kind, values, image, sub: chartSubtitle(kind, values) });
  app.recent = app.recent.slice(0, 8);
  renderRecent();
}

function renderRecent() {
  const list = app.recent || [];
  $("recent-charts").hidden = list.length < 2;
  $("recent-list").replaceChildren(
    ...list.map((r, i) =>
      el("button", {
        class: `recent-item ${i === 0 ? "current" : ""}`,
        title: `${CHART_TYPES.find((t) => t.kind === r.kind).label}: ${r.sub}`,
        onclick: () => selectChart(r.kind, r.values),
      },
      el("img", { src: r.image, alt: "" }),
      el("span", { text: r.sub }))
    )
  );
}

/* ---- export ---------------------------------------------------------- */

const chartFileName = (ext) =>
  `${[chartLabel(), chartSubtitle(app.chartKind, chartValues)].join(" ").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60)}.${ext}`;

async function saveChart() {
  if (!app.chartImage) return;
  try {
    const res = await window.api.saveImage(app.chartImage, chartFileName("png"));
    if (res) toast("success", `Saved ${res.path}`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function saveChartSvg() {
  if (!app.chartImage) return;
  try {
    const res = await call("plot", { kind: app.chartKind, params: app.chartParams, style: chartStyle(), width: $("chart-stage").clientWidth, fmt: "svg" });
    const saved = await window.api.saveText(res.svg, chartFileName("svg"));
    if (saved) toast("success", `Saved ${saved.path}`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

async function copyChart() {
  if (!app.chartImage) return;
  try {
    await window.api.copyImage(app.chartImage);
    toast("success", "Chart copied. Paste it into a document or chat.");
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function showChartCode() {
  if (!app.chartCode) return;
  openCodeDialog("Chart as Python code", "Recreates this chart with pandas, matplotlib and seaborn.", app.chartCode, chartFileName("py"));
}

/* ------------------------------------------------------------------ */
/* wiring                                                               */
/* ------------------------------------------------------------------ */

$("btn-open").addEventListener("click", openFile);
$("btn-open-empty").addEventListener("click", openFile);
$("btn-export").addEventListener("click", () => toggleExportMenu());
for (const item of document.querySelectorAll("#export-menu [data-format]")) {
  item.addEventListener("click", () => exportData(item.dataset.format));
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".menu-wrap")) toggleExportMenu(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("export-menu").hidden) toggleExportMenu(false);
});
$("sheet-close").addEventListener("click", () => $("sheet-dialog").close());
$("import-close").addEventListener("click", () => $("import-dialog").close());
$("import-cancel").addEventListener("click", () => $("import-dialog").close());
$("import-apply").addEventListener("click", applyImportSettings);
$("btn-undo").addEventListener("click", undo);
$("btn-undo-2").addEventListener("click", undo);
$("btn-do").addEventListener("click", doClean);
$("btn-save-chart").addEventListener("click", saveChart);
$("btn-save-svg").addEventListener("click", saveChartSvg);
$("btn-copy-chart").addEventListener("click", copyChart);
$("btn-chart-code").addEventListener("click", showChartCode);
$("vc-column").addEventListener("change", renderValueCounts);
for (const tab of document.querySelectorAll("#inspect-tabs button")) {
  tab.addEventListener("click", () => {
    app.inspectKind = tab.dataset.kind;
    renderInspect();
  });
}
$("btn-code").addEventListener("click", showCode);
$("btn-pivot-save").addEventListener("click", savePivot);
$("btn-pivot-code").addEventListener("click", showPivotCode);
$("btn-test-code").addEventListener("click", showTestCode);
$("btn-trend-code").addEventListener("click", showTrendCode);
$("btn-segment-code").addEventListener("click", showSegmentCode);
for (const b of document.querySelectorAll("#analyze-tabs button")) b.addEventListener("click", () => selectAnalyzeTab(b.dataset.tab));
$("btn-pivot-chart").addEventListener("click", togglePivotChart);
$("btn-run-query").addEventListener("click", runQuery);
$("btn-query-apply").addEventListener("click", applyQuery);
$("btn-query-save").addEventListener("click", saveCurrentQuery);
$("btn-query-chart").addEventListener("click", toggleQueryChart);
$("sql-editor").addEventListener("input", (e) => (app.query.sql = e.target.value));
$("sql-editor").addEventListener("keydown", (e) => {
  if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    insertAtCursor(e.target, "  ");
  }
});
$("code-close").addEventListener("click", () => $("code-dialog").close());
$("code-copy").addEventListener("click", async () => {
  await window.api.copyText(app.script ? app.script.code : "");
  toast("success", "Code copied to the clipboard.");
});
$("code-save").addEventListener("click", async () => {
  if (!app.script) return;
  const res = await window.api.saveText(app.script.code, app.script.fileName);
  if (res) toast("success", `Saved ${res.path}`);
});

$("page-prev").addEventListener("click", () => {
  if (app.page > 0) {
    app.page--;
    loadPage();
  }
});
$("page-next").addEventListener("click", () => {
  app.page++;
  loadPage();
});

/* theme toggle ------------------------------------------------------- */

function syncThemeButton() {
  const dark = document.documentElement.dataset.theme === "dark";
  $("theme-label").textContent = tr(dark ? "Light mode" : "Dark mode");
}

function setTheme(theme, persist) {
  document.documentElement.dataset.theme = theme;
  if (persist) {
    try {
      localStorage.setItem("theme", theme);
    } catch {}
  }
  syncThemeButton();
  // Re-render the current chart so its colours match the new theme.
  if (app.chartImage) generateChart();
  if (!$("query-chart-card").hidden && app.query.lastSql) drawQueryChart();
  if (!$("pivot-chart-card").hidden && app.pivot) drawPivotChart();
}

$("btn-theme").addEventListener("click", () =>
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true)
);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
  let saved = null;
  try {
    saved = localStorage.getItem("theme");
  } catch {}
  if (!saved) setTheme(e.matches ? "dark" : "light", false);
});
syncThemeButton();

for (const btn of document.querySelectorAll("#nav .nav-item")) {
  btn.addEventListener("click", () => {
    if (app.state) showSection(btn.dataset.section);
  });
}

// Drag & drop a CSV anywhere in the window.
let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  e.preventDefault();
  dragDepth++;
  document.body.classList.add("dragging");
});
window.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) document.body.classList.remove("dragging");
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  const file = e.dataTransfer.files[0];
  if (file) loadDroppedFile(file);
});

window.api.onBackendExit((reason) => toast("error", reason));

// Keyboard shortcuts: Ctrl/Cmd+O open, Ctrl/Cmd+S export, Ctrl/Cmd+Z undo.
window.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key === "Enter" && app.section === "clean") {
    e.preventDefault();
    doClean();
    return;
  }
  if (e.key === "Enter" && app.section === "query") {
    e.preventDefault();
    runQuery();
    return;
  }
  const tag = document.activeElement && document.activeElement.tagName;
  const key = e.key.toLowerCase();
  if (key === "o") {
    e.preventDefault();
    openFile();
  } else if (key === "s" && app.state) {
    e.preventDefault();
    exportData("csv");
  } else if (key === "z" && app.state && app.state.canUndo && tag !== "INPUT" && tag !== "TEXTAREA") {
    e.preventDefault();
    undo();
  }
});

for (const btn of document.querySelectorAll("#nav .nav-item")) btn.disabled = true;
renderChartTiles();
syncInspectTabs();
renderOpList();

/* ------------------------------------------------------------------ */
/* report builder                                                       */
/* ------------------------------------------------------------------ */

const REPORT_KEY = "databoss.report.v1";
const REPORT_LABELS = { dashboard: "Dashboard", heading: "Heading", text: "Text note", chart: "Chart", table: "Table", trend: "Trend", test: "Test result", insights: "Findings" };

function loadReport() {
  try {
    const saved = JSON.parse(localStorage.getItem(REPORT_KEY) || "null");
    if (saved && Array.isArray(saved.blocks)) return saved;
  } catch {
    /* storage unavailable or corrupt: start fresh */
  }
  return { title: "Data report", blocks: [] };
}

function saveReport() {
  try {
    const text = JSON.stringify(app.report);
    if (text.length < 4_500_000) localStorage.setItem(REPORT_KEY, text);
    else localStorage.removeItem(REPORT_KEY); // too big to keep between sessions
  } catch {
    /* not critical */
  }
}

app.report = loadReport();
let reportSeq = Date.now();

function syncReportBadge() {
  const n = app.report.blocks.length;
  const badge = $("nav-report-badge");
  badge.hidden = !n;
  badge.textContent = String(n);
}

function addToReport(block, quiet = false) {
  app.report.blocks.push({ id: `b${++reportSeq}`, source: app.state ? app.state.fileName : null, ...block });
  saveReport();
  syncReportBadge();
  if (app.section === "report") renderReport();
  if (!quiet) toast("success", `Added to the report (${plural(app.report.blocks.length, "item")}).`);
}

/** Matplotlib colours from the light theme, so report charts print well whatever the app theme is. */
function lightChartStyle() {
  const root = document.documentElement;
  const before = root.dataset.theme;
  root.dataset.theme = "light";
  try {
    return chartStyle();
  } finally {
    if (before === undefined) delete root.dataset.theme;
    else root.dataset.theme = before;
  }
}

async function reportChart() {
  if (!app.chartImage || !app.chartKind) return;
  try {
    const res = await window.api.call("plot", { kind: app.chartKind, params: app.chartParams, style: lightChartStyle(), width: 900 });
    addToReport({ type: "chart", title: `${chartLabel()}: ${chartSubtitle(app.chartKind, chartValues)}`, image: res.image,
      insights: res.insights, notes: res.notes });
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function reportPivot() {
  if (!app.pivot) return;
  const t = app.pivot.res.table;
  addToReport({ type: "table", title: `Pivot: ${pivotSubtitle(app.pivot.params)}`,
    table: { columns: t.columns, data: t.data.slice(0, 200) }, truncated: t.data.length > 200,
    notes: app.pivot.res.notes, percent: app.pivot.res.percent, valueColumns: app.pivot.res.valueColumns });
}

function reportTrend() {
  if (!app.trend) return;
  const res = app.trend.res;
  const svg = document.querySelector("#trend-output .trend-svg");
  addToReport({ type: "trend", title: `Trend: ${res.label} per ${res.unit}`, insights: res.insights, notes: res.notes,
    svg: svg ? svg.outerHTML : null });
}

function reportSegment() {
  if (!app.segment) return;
  const s = app.segment;
  const clear = s.columns.filter((c) => c.significant).slice(0, 8).map((c) => c.sentence);
  addToReport({ type: "insights", title: `Segment: ${s.label}`,
    lead: `${s.summary} The segment has ${fmt(s.segmentRows)} rows; the rest has ${fmt(s.restRows)}.`,
    items: clear, notes: s.caveats });
}

function reportTest() {
  if (!app.test) return;
  const r = app.test;
  const stats = [["p-value", pText(r.p)]];
  if (r.effect && r.effect.value != null) stats.push([`${tr(r.effect.name)} (${tr(r.effect.size)})`, r.effect.value.toFixed(2)]);
  if (r.ci) stats.push([`95% CI · ${r.ci.label}`, `${fnum(r.ci.low)} … ${fnum(r.ci.high)}`]);
  stats.push(["Rows used", fmt(r.n)]);
  addToReport({ type: "test", title: `${tr(r.test)}: ${tr(r.question)}`, sentence: r.interpretation, significant: r.significant,
    stats, why: r.why.map((w) => tr(`${w[0].toUpperCase()}${w.slice(1)}.`).replace(/\.$/, "")), notes: r.caveats });
}

/* ---- rendering a block as part of the document ---------------------- */

function svgFromMarkup(markup) {
  if (!markup) return null;
  const doc = new DOMParser().parseFromString(markup, "image/svg+xml");
  const root = doc.documentElement;
  if (!root || root.nodeName !== "svg") return null;
  root.querySelectorAll("script, foreignObject").forEach((n) => n.remove());
  return document.importNode(root, true);
}

function reportBlockBody(b) {
  const notes = b.notes && b.notes.length ? el("ul", { class: "r-small" }, b.notes.map((t) => el("li", { text: t }))) : null;
  switch (b.type) {
    case "heading":
      return el("h2", { text: b.text || "Untitled section" });
    case "text":
      return el("p", { class: "r-text", text: b.text || "" });
    case "chart":
      return el("div", {},
        el("h3", { text: b.title }),
        el("img", { src: b.image, alt: b.title }),
        b.insights && b.insights.length ? el("ul", {}, b.insights.map((t) => el("li", { text: t }))) : null,
        notes);
    case "table": {
      const t = b.table;
      const numeric = t.columns.map((c, i) => t.data.some((r) => typeof r[i] === "number"));
      return el("div", {},
        el("h3", { text: b.title }),
        el("table", {},
          el("thead", {}, el("tr", {}, t.columns.map((c, i) => el("th", { text: c, class: numeric[i] ? "num" : null })))),
          el("tbody", {}, t.data.map((r) =>
            el("tr", { class: r[0] === "Total" ? "r-total" : null },
              r.map((v, i) => el("td", { class: numeric[i] ? "num" : null,
                text: v == null ? "" : typeof v === "number" ? (b.percent && i >= t.columns.length - b.valueColumns.length ? fmtPct(v) : fnum(v)) : String(v) })))))),
        b.truncated ? el("p", { class: "r-small", text: "Showing the first 200 rows." }) : null,
        notes);
    }
    case "trend":
      return el("div", {},
        el("h3", { text: b.title }),
        el("div", { class: "r-callout" }, el("ul", {}, b.insights.map((t) => el("li", { text: t })))),
        b.svg ? el("div", { class: "r-chart" }, svgFromMarkup(b.svg)) : null,
        notes);
    case "test":
      return el("div", {},
        el("h3", { text: b.title }),
        el("div", { class: `r-callout ${b.significant ? "good" : ""}` }, el("p", { text: b.sentence })),
        el("div", { class: "r-stats" }, b.stats.map(([k, v]) => el("div", { class: "r-stat" }, el("b", { text: v }), el("span", { text: k })))),
        b.why && b.why.length ? el("p", { class: "r-small", text: trf("Why this test: {0}.", b.why.join("; ")), raw: true }) : null,
        notes);
    case "dashboard":
      if (b.rendered) {
        return el("div", {}, el("h2", { text: b.title || "Dashboard" }),
          b.rendered.map((r) => el("div", { class: "r-block" }, reportBlockBody(r))));
      }
      return el("div", {}, el("h3", { text: b.title || "Dashboard" }),
        el("p", { class: "r-small", text: `The ${plural(app.dashboard.tiles.length, "pinned tile")} on the Dashboard, drawn from the data as it is when you export.` }));
    case "insights":
      return el("div", {},
        el("h3", { text: b.title }),
        el("div", { class: "r-callout" }, el("p", { text: b.lead }),
          b.items.length ? el("ul", {}, b.items.map((t) => el("li", { text: t }))) : null),
        notes);
    default:
      return null;
  }
}

function reportSources() {
  return [...new Set(app.report.blocks.map((b) => b.source).filter(Boolean))];
}

/** The finished document: what the export contains. */
function reportDocument(blocks = app.report.blocks) {
  const date = new Date().toLocaleDateString(i18n.lang === "ar" ? "ar-IQ" : "en-GB", { day: "numeric", month: "long", year: "numeric", numberingSystem: "latn" });
  const sources = reportSources();
  return el("article", { class: "report-doc" },
    el("h1", { text: app.report.title || "Data report" }),
    el("p", { class: "r-meta", text: sources.length ? trf("Created {0} with Data Boss · Data: {1}", date, sources.join(", ")) : trf("Created {0} with Data Boss", date), raw: true }),
    blocks
      .filter((b) => !((b.type === "text" || b.type === "heading") && !(b.text || "").trim()))
      .map((b) => el("section", { class: "r-block" }, reportBlockBody(b))),
    el("p", { class: "r-footer", text: "Statistics are computed from the data as loaded and cleaned in Data Boss. Associations and differences describe this data; they do not by themselves show cause." }));
}

/* ---- editor ------------------------------------------------------------ */

function moveBlock(i, delta) {
  const blocks = app.report.blocks;
  const j = i + delta;
  if (j < 0 || j >= blocks.length) return;
  [blocks[i], blocks[j]] = [blocks[j], blocks[i]];
  saveReport();
  renderReport();
}

function renderReport() {
  syncReportBadge();
  $("report-title").value = app.report.title || "";
  const blocks = app.report.blocks;
  const editor = $("report-editor");
  const hasContent = blocks.length > 0;
  for (const id of ["btn-report-html", "btn-report-pdf", "btn-report-clear"]) $(id).disabled = !hasContent;
  if (!hasContent) {
    editor.replaceChildren(el("div", { class: "card report-empty" },
      el("h2", { text: "Your report is empty" }),
      el("p", { class: "card-hint", text: "Use the Report button on a chart (Visualize), a pivot table, a trend, a segment comparison or a test result (Analyze). Add headings and notes here to tell the story." })));
    return;
  }
  const items = blocks.map((b, i) => {
    let body;
    if (b.type === "heading" || b.type === "text") {
      const input = el(b.type === "text" ? "textarea" : "input", {
        class: b.type === "text" ? "report-textarea" : "report-heading-input",
        type: b.type === "text" ? null : "text",
        placeholder: b.type === "text" ? "Write what the reader should take away…" : "Section heading",
        rows: b.type === "text" ? 4 : null,
        "aria-label": REPORT_LABELS[b.type],
        oninput: (e) => { b.text = e.target.value; saveReport(); },
      });
      input.value = b.text || "";
      body = input;
    } else {
      body = el("div", { class: "report-doc report-inline" }, reportBlockBody(b));
    }
    return el("div", { class: "report-item card", "data-type": b.type },
      el("div", { class: "report-item-bar" },
        el("span", { class: "chip", text: REPORT_LABELS[b.type] || b.type }),
        b.source && !["heading", "text"].includes(b.type) ? el("span", { class: "muted report-item-src", text: b.source }) : null,
        el("span", { class: "report-item-spacer" }),
        el("button", { class: "icon-btn", title: "Move up", "aria-label": "Move up", disabled: i === 0, onclick: () => moveBlock(i, -1) }, icon("i-up")),
        el("button", { class: "icon-btn", title: "Move down", "aria-label": "Move down", disabled: i === blocks.length - 1, onclick: () => moveBlock(i, 1) }, icon("i-down")),
        el("button", { class: "icon-btn", title: "Remove", "aria-label": "Remove", onclick: () => {
          blocks.splice(i, 1);
          saveReport();
          renderReport();
        } }, icon("i-x"))),
      body);
  });
  editor.replaceChildren(...items);
}

async function exportReport(format, testPath) {
  if (!app.report.blocks.length) return null;
  try {
    let blocks = app.report.blocks;
    if (blocks.some((b) => b.type === "dashboard")) {
      const rendered = await dashboardForReport();
      blocks = blocks.map((b) => (b.type === "dashboard" ? { ...b, rendered } : b));
    }
    const res = await window.api.exportReport(reportDocument(blocks).outerHTML, app.report.title || "Data report", format, testPath);
    if (res) toast("success", `Report saved to ${res.path}`);
    return res;
  } catch (err) {
    toast("error", cleanError(err));
    return null;
  }
}

$("report-title").addEventListener("input", (e) => { app.report.title = e.target.value; saveReport(); });
$("btn-report-heading").addEventListener("click", () => { addToReport({ type: "heading", text: "" }, true); focusLastReportInput(); });
$("btn-report-text").addEventListener("click", () => { addToReport({ type: "text", text: "" }, true); focusLastReportInput(); });
$("btn-report-html").addEventListener("click", () => exportReport("html"));
$("btn-report-pdf").addEventListener("click", () => exportReport("pdf"));
$("btn-report-clear").addEventListener("click", (e) => {
  const btn = e.currentTarget;
  if (btn.dataset.armed !== "1") {
    btn.dataset.armed = "1";
    btn.textContent = tr("Click again to clear");
    setTimeout(() => { btn.dataset.armed = ""; btn.textContent = tr("Clear"); }, 3000);
    return;
  }
  btn.dataset.armed = "";
  btn.textContent = tr("Clear");
  app.report.blocks = [];
  saveReport();
  renderReport();
});
$("btn-report-chart").addEventListener("click", reportChart);
$("btn-report-pivot").addEventListener("click", reportPivot);
$("btn-report-trend").addEventListener("click", reportTrend);
$("btn-report-segment").addEventListener("click", reportSegment);
$("btn-report-test").addEventListener("click", reportTest);

function focusLastReportInput() {
  requestAnimationFrame(() => {
    const inputs = $("report-editor").querySelectorAll(".report-textarea, .report-heading-input");
    const last = inputs[inputs.length - 1];
    if (last) { last.focus(); last.scrollIntoView({ block: "center" }); }
  });
}
syncReportBadge();

/* ---- notebook export --------------------------------------------------- */

async function exportNotebook() {
  if (!app.state) return;
  const charts = (app.recent || []).slice().reverse().map((r) => ({
    kind: r.kind,
    params: chartParams(r.kind, r.values),
    title: `${CHART_TYPES.find((t) => t.kind === r.kind).label}: ${r.sub}`,
  }));
  try {
    const res = await call("notebook", { charts });
    const saved = await window.api.saveText(res.notebook, res.fileName);
    if (saved) toast("success", `Notebook saved to ${saved.path}`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

$("btn-notebook").addEventListener("click", exportNotebook);
$("btn-chart-notebook").addEventListener("click", exportNotebook);

/* ------------------------------------------------------------------ */
/* model builder                                                        */
/* ------------------------------------------------------------------ */

let modelValues = {};
let modelSeq = 0;

function renderModelFields() {
  const memory = (app.forms.model ||= {});
  const cols = app.state.columns.filter((c) => c.kind !== "other").map((c) => c.name);
  const target = cols.includes(memory.target) ? memory.target : numericCols()[0] || cols[0];
  const others = allCols().filter((c) => c !== target);
  const specs = [
    { key: "target", label: "Target (what to predict)", type: "select", options: cols, default: target, rerender: true },
    { key: "task", label: "Task", type: "select",
      options: toOptions([["auto", "Detect automatically"], ["regression", "Regression: predict a number"], ["classification", "Classification: predict a category"]]) },
    { key: `features:${target}`, label: "Use these columns", type: "multi", options: others, default: others,
      hint: "IDs, free text and dates are left out automatically; the result lists them." },
  ];
  modelValues = buildForm($("model-fields"), specs, memory, (values, key) => {
    modelValues = values;
    if (key === "target") renderModelFields();
  });
}

function modelParams(v) {
  return { target: v.target, task: v.task || "auto", features: v[`features:${v.target}`] || [] };
}

async function trainModel() {
  if (!app.state) return;
  const params = modelParams(modelValues);
  if (!params.features.length) {
    $("model-output").replaceChildren(note("warn", "Tick at least one column to learn from."));
    return;
  }
  const seq = ++modelSeq;
  const out = $("model-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Training three models…");
  out.replaceChildren(loading);
  $("btn-train").disabled = true;
  const hideCancel = delayedCancel(loading, "model", () => seq === modelSeq && out.replaceChildren(note("info", "Training cancelled.")));
  try {
    const res = await callLatest("model", "model", params);
    if (seq !== modelSeq) return;
    app.model = res;
    $("model-title").textContent = tr(res.task === "regression" ? `Predicting ${res.target} (regression)` : `Predicting ${res.target} (classification)`);
    $("model-sub").textContent = tr(`${fmt(res.trainRows)} training rows · ${fmt(res.testRows)} test rows · ${plural(res.features.length, "feature")}`);
    $("model-actions").hidden = false;
    out.replaceChildren(modelView(res));
  } catch (err) {
    if (seq !== modelSeq || isCancelled(err)) return;
    app.model = null;
    $("model-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    hideCancel();
    $("btn-train").disabled = false;
  }
}

const METRIC_COLUMNS = {
  regression: [["r2", "R²", (v) => v.toFixed(3)], ["mae", "MAE", fnum], ["rmse", "RMSE", fnum], ["trainScore", "Train R²", (v) => v.toFixed(3)]],
  classification: [["accuracy", "Accuracy", (v) => fmtPct(v * 100)], ["f1", "F1", (v) => v.toFixed(3)], ["rocAuc", "ROC-AUC", (v) => v.toFixed(3)],
    ["trainScore", "Train F1", (v) => v.toFixed(3)]],
};

function scatterSvg(points, label) {
  const W = 420, H = 300, L = 52, R = 10, T = 10, B = 36;
  const vals = points.flat().filter((v) => v != null);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo) hi = lo + 1;
  const sx = (v) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const sy = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const ns = "http://www.w3.org/2000/svg";
  const node = (tag, attrs, text) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = tr(text);
    return n;
  };
  const svg = node("svg", { viewBox: `0 0 ${W} ${H}`, class: "trend-svg model-scatter", role: "img", "aria-label": `Predicted vs actual ${label}` });
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    svg.append(node("line", { x1: L, x2: W - R, y1: sy(v), y2: sy(v), class: "trend-grid" }),
      node("text", { x: L - 6, y: sy(v) + 4, class: "trend-axis", "text-anchor": "end" }, fnum(v)),
      node("text", { x: sx(v), y: H - 20, class: "trend-axis", "text-anchor": "middle" }, fnum(v)));
  }
  svg.append(node("line", { x1: sx(lo), y1: sy(lo), x2: sx(hi), y2: sy(hi), class: "model-diag" }));
  for (const [a, p] of points) svg.append(node("circle", { cx: sx(a), cy: sy(p), r: 3, class: "model-point" }));
  svg.append(node("text", { x: (L + W - R) / 2, y: H - 4, class: "trend-axis", "text-anchor": "middle" }, `actual ${label}`),
    node("text", { x: 12, y: (T + H - B) / 2, class: "trend-axis", "text-anchor": "middle", transform: `rotate(-90 12 ${(T + H - B) / 2})` }, "predicted"));
  return svg;
}

function confusionTable(conf) {
  const max = Math.max(1, ...conf.matrix.flat());
  return el("div", { class: "table-wrap" },
    el("table", { class: "test-table confusion" },
      el("thead", {}, el("tr", {}, el("th", { text: "actual ↓ / predicted →" }), conf.labels.map((l) => el("th", { class: "num", text: l })))),
      el("tbody", {}, conf.matrix.map((row, i) =>
        el("tr", {}, el("th", { text: conf.labels[i] }),
          row.map((v, j) => el("td", { class: `num ${i === j ? "diag" : ""}`, text: fmt(v),
            style: `--shade:${(v / max).toFixed(3)}` })))))));
}

function modelView(res) {
  const verdict = el("div", { class: `test-verdict ${res.weak ? "none" : "found"}` },
    el("div", { class: "test-verdict-label", text: res.weak ? "Not much better than guessing" : "Result on unseen rows" }),
    el("p", { class: "test-sentence", text: res.summary }));
  const warnings = res.warnings.map((w) => note("warn", w.text));
  const cols = METRIC_COLUMNS[res.task];
  const table = el("div", { class: "table-wrap" },
    el("table", { class: "test-table" },
      el("thead", {}, el("tr", {}, el("th", { text: "Model" }), cols.map(([, h]) => el("th", { class: "num", text: h })))),
      el("tbody", {}, res.models.map((m) =>
        el("tr", { class: m.best ? "best-row" : null },
          el("td", {}, m.name, m.best ? el("span", { class: "chip chip-good", text: "best" }) : null),
          cols.map(([k, , f]) => el("td", { class: "num", text: m[k] == null ? "—" : f(m[k]) })))))));
  const hint = res.task === "regression"
    ? "R² = share of the variation explained (1 is perfect, 0 is no better than the average). MAE = typical error in the target's units."
    : `Accuracy = share of test rows right. F1 balances missed and false alarms${res.positiveClass ? ` for “${res.positiveClass}”` : " (averaged over classes)"}. ROC-AUC: 0.5 = guessing, 1 = perfect ranking.`;
  const imp = res.importance;
  const maxImp = Math.max(1e-12, ...imp.map((i) => i.mean || 0));
  const importance = el("div", { class: "card" },
    el("h2", { text: "Which columns matter" }),
    el("p", { class: "card-hint", text: `How much the best model's test score drops when a column is shuffled. Around zero or below = the model doesn't rely on it.` }),
    el("div", { class: "bar-list" }, imp.slice(0, 15).map((i) =>
      el("div", { class: "bar-row" },
        el("span", { class: "bar-label", text: i.feature, title: i.feature }),
        bar(Math.max(0, i.mean) / maxImp),
        el("span", { class: "bar-value", text: `${i.mean >= 0 ? "+" : ""}${i.mean.toFixed(3)}` })))));
  const best = res.models.find((m) => m.best);
  const detail = res.task === "regression"
    ? el("div", { class: "card" }, el("h2", { text: `Predicted vs actual (${best.name.toLowerCase()})` }),
      el("p", { class: "card-hint", text: "Each dot is a test row. On the diagonal = perfect prediction." }),
      el("div", { class: "model-chart" }, scatterSvg(res.details.points, res.target)))
    : res.details.confusion
      ? el("div", { class: "card" }, el("h2", { text: `Confusion matrix (${best.name.toLowerCase()})` }),
        el("p", { class: "card-hint", text: "Rows are the real values, columns the predictions; the diagonal is correct." }),
        confusionTable(res.details.confusion))
      : null;
  const extras = [...res.notes];
  const skipped = res.skipped.length
    ? el("details", { class: "card tgt-skipped" }, el("summary", { text: `Columns left out (${res.skipped.length})` }),
      el("ul", {}, res.skipped.map((k) => el("li", {}, el("strong", { text: k.column }), ` — ${k.reason}`))))
    : null;
  return el("div", { class: "test-body" },
    verdict, ...warnings,
    el("div", {}, table, el("p", { class: "card-hint model-hint", text: hint })),
    el("div", { class: "grid-2 model-grid" }, detail, importance),
    extras.length ? el("div", { class: "chart-footnotes" }, extras.map((t) => el("p", { text: t }))) : null,
    skipped);
}

function showModelCode() {
  if (!app.model) return;
  openCodeDialog("Models as scikit-learn code", "Rebuilds your data, the same split and pipelines, and prints the same scores.", app.model.code, "model.py");
}

function reportModel() {
  if (!app.model) return;
  const r = app.model;
  const cols = METRIC_COLUMNS[r.task];
  addToReport({ type: "table", title: `Model: predicting ${r.target} (${r.task})`,
    table: { columns: ["Model", ...cols.map(([, h]) => h)], data: r.models.map((m) => [m.name + (m.best ? " (best)" : ""), ...cols.map(([k]) => m[k])]) },
    notes: [r.summary, ...r.warnings.map((w) => w.text),
      `Most important: ${r.importance.slice(0, 3).map((i) => i.feature).join(", ")}.`, `${fmt(r.trainRows)} training rows, ${fmt(r.testRows)} test rows.`] });
}

$("btn-train").addEventListener("click", trainModel);
$("btn-model-code").addEventListener("click", showModelCode);
$("btn-report-model").addEventListener("click", reportModel);

/* ---- clustering ------------------------------------------------------- */

let clusterValues = {};
let clusterSeq = 0;

function selectModelTab(tab) {
  app.modelTab = tab;
  for (const b of document.querySelectorAll("#model-tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const t of ["predict", "clusters", "forecast"]) $(`model-${t}`).hidden = tab !== t;
  if (!app.state) return;
  if (tab === "clusters") renderClusterFields();
  else if (tab === "forecast") renderForecastFields();
  else renderModelFields();
}

function renderClusterFields() {
  const memory = (app.forms.clusters ||= {});
  const cols = allCols();
  const defaults = numericCols().length ? [...numericCols(), ...groupCols().filter((c) => uniqueOf(c) <= 12)] : cols;
  clusterValues = buildForm($("cluster-fields"), [
    { key: "features", label: "Columns that describe a row", type: "multi", options: cols, default: defaults,
      hint: "IDs, free text and dates are left out automatically." },
    { key: "k", label: "Number of clusters", type: "select",
      options: toOptions([["", "Automatic (best silhouette)"], ...[2, 3, 4, 5, 6, 7, 8, 10].map((k) => [String(k), String(k)])]) },
  ], memory, (values) => { clusterValues = values; });
}

async function findClusters() {
  if (!app.state) return;
  const features = clusterValues.features || [];
  if (!features.length) {
    $("cluster-output").replaceChildren(note("warn", "Tick at least one column."));
    return;
  }
  const seq = ++clusterSeq;
  const out = $("cluster-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Trying 2 to 8 clusters…");
  out.replaceChildren(loading);
  $("btn-cluster").disabled = true;
  const hideCancel = delayedCancel(loading, "clusters", () => seq === clusterSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("clusters", "clusters", { features, k: clusterValues.k ? Number(clusterValues.k) : null });
    if (seq !== clusterSeq) return;
    app.clusters = res;
    $("cluster-title").textContent = tr(`${res.k} clusters`);
    $("cluster-sub").textContent = tr(`${fmt(res.rows)} rows · ${plural(res.features.length, "column")}`);
    $("cluster-actions").hidden = false;
    out.replaceChildren(clusterView(res));
  } catch (err) {
    if (seq !== clusterSeq || isCancelled(err)) return;
    app.clusters = null;
    $("cluster-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    hideCancel();
    $("btn-cluster").disabled = false;
  }
}

function svgNode(tag, attrs, text) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = tr(text);
  return n;
}

function scanChart(scan, chosen) {
  const W = 420, H = 220, L = 46, R = 46, T = 12, B = 34;
  const ks = scan.map((s) => s.k);
  const x = (k) => L + ((k - ks[0]) / Math.max(1, ks[ks.length - 1] - ks[0])) * (W - L - R);
  const inMax = Math.max(...scan.map((s) => s.inertia)), inMin = Math.min(...scan.map((s) => s.inertia));
  const yi = (v) => T + (1 - (v - inMin) / (inMax - inMin || 1)) * (H - T - B);
  const silMax = Math.max(...scan.map((s) => s.silhouette)), silMin = Math.min(...scan.map((s) => s.silhouette));
  const ys = (v) => T + (1 - (v - silMin) / (silMax - silMin || 1)) * (H - T - B);
  const svg = svgNode("svg", { viewBox: `0 0 ${W} ${H}`, class: "trend-svg", role: "img", "aria-label": "Elbow and silhouette by number of clusters" });
  svg.append(svgNode("rect", { x: x(chosen) - 10, y: T, width: 20, height: H - T - B, class: "scan-chosen" }));
  for (const k of ks) svg.append(svgNode("text", { x: x(k), y: H - 14, class: "trend-axis", "text-anchor": "middle" }, String(k)));
  svg.append(svgNode("text", { x: (L + W - R) / 2, y: H - 1, class: "trend-axis", "text-anchor": "middle" }, "number of clusters"));
  svg.append(svgNode("polyline", { points: scan.map((s) => `${x(s.k)},${yi(s.inertia)}`).join(" "), class: "trend-line scan-inertia" }));
  svg.append(svgNode("polyline", { points: scan.map((s) => `${x(s.k)},${ys(s.silhouette)}`).join(" "), class: "trend-avg" }));
  for (const s of scan) {
    const d1 = svgNode("circle", { cx: x(s.k), cy: yi(s.inertia), r: 3, class: "trend-dot" });
    d1.append(svgNode("title", {}, `k=${s.k}: inertia ${fnum(s.inertia)}`));
    const d2 = svgNode("circle", { cx: x(s.k), cy: ys(s.silhouette), r: 3, class: "scan-sil-dot" });
    d2.append(svgNode("title", {}, `k=${s.k}: silhouette ${s.silhouette.toFixed(3)}`));
    svg.append(d1, d2);
  }
  svg.append(svgNode("text", { x: L - 6, y: T + 8, class: "trend-axis", "text-anchor": "end" }, "high"),
    svgNode("text", { x: W - R + 6, y: ys(silMax) + 4, class: "trend-axis" }, silMax.toFixed(2)),
    svgNode("text", { x: W - R + 6, y: ys(silMin) + 4, class: "trend-axis" }, silMin.toFixed(2)));
  return svg;
}

function clusterMap(points, k) {
  const W = 420, H = 300, P = 14;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v) => P + ((v - x0) / (x1 - x0 || 1)) * (W - 2 * P);
  const sy = (v) => P + (1 - (v - y0) / (y1 - y0 || 1)) * (H - 2 * P);
  const svg = svgNode("svg", { viewBox: `0 0 ${W} ${H}`, class: "trend-svg cluster-map", role: "img", "aria-label": "Rows on a 2-D map coloured by cluster" });
  svg.append(svgNode("rect", { x: 0.5, y: 0.5, width: W - 1, height: H - 1, class: "cluster-frame" }));
  for (const [a, b, c] of points) svg.append(svgNode("circle", { cx: sx(a), cy: sy(b), r: 3.2, class: `cl cl-${((c - 1) % 8) + 1}` }));
  return svg;
}

function clusterView(res) {
  const good = (res.silhouette ?? 0) >= 0.25;
  const verdict = el("div", { class: `test-verdict ${good ? "found" : "none"}` },
    el("div", { class: "test-verdict-label", text: good ? "Groups found" : "Groups are not clear-cut" }),
    el("p", { class: "test-sentence", text: res.summary }));
  const profiles = el("div", { class: "cluster-profiles" }, res.profiles.map((p) =>
    el("div", { class: "cluster-card" },
      el("div", { class: "cluster-card-head" },
        el("span", { class: `cl-swatch cl-${((p.cluster - 1) % 8) + 1}` }),
        el("strong", { text: `Cluster ${p.cluster}` }),
        el("span", { class: "muted", text: `${fmt(p.size)} rows · ${fmtPct(p.share * 100)}` })),
      el("p", { class: "cluster-name", text: p.name.replace(/^Cluster \d+: /, "") }),
      p.traits.length ? el("ul", {}, p.traits.map((t) => el("li", { text: t }))) : null)));
  const charts = el("div", { class: "grid-2 model-grid" },
    el("div", { class: "card" }, el("h2", { text: "Rows on a map" }),
      el("p", { class: "card-hint", text: `The columns squeezed into 2 dimensions (PCA, ${fmtPct((res.explained[0] + res.explained[1]) * 100)} of the variation). Nearby dots are similar rows.` }),
      clusterMap(res.points, res.k)),
    el("div", { class: "card" }, el("h2", { text: "How many clusters?" }),
      el("p", { class: "card-hint", text: "Solid: spread inside clusters (lower is tighter; look for the bend). Dashed: silhouette (higher = better separated). The shaded column is the number used." }),
      scanChart(res.scan, res.k)));
  const skipped = res.skipped.length
    ? el("details", { class: "card tgt-skipped" }, el("summary", { text: `Columns left out (${res.skipped.length})` }),
      el("ul", {}, res.skipped.map((k) => el("li", {}, el("strong", { text: k.column }), ` — ${k.reason}`))))
    : null;
  return el("div", { class: "test-body" }, verdict, profiles, charts, skipped);
}

async function applyClusters() {
  if (!app.clusters) return;
  const name = allCols().includes("cluster") ? `cluster_${app.clusters.k}` : "cluster";
  try {
    const res = await call("clean", { method: "ADD_CLUSTERS", params: { k: app.clusters.k, features: app.clusters.features, name } });
    setState(res.state);
    toast("success", `${res.message} Undo it from Clean if needed.`);
  } catch (err) {
    toast("error", cleanError(err));
  }
}

function reportClusters() {
  if (!app.clusters) return;
  const r = app.clusters;
  addToReport({ type: "insights", title: `Clusters: ${r.k} groups from ${r.features.join(", ")}`, lead: r.summary,
    items: r.profiles.map((p) => `${p.name} (${fmt(p.size)} rows, ${fmtPct(p.share * 100)})`) });
}

for (const b of document.querySelectorAll("#model-tabs button")) b.addEventListener("click", () => selectModelTab(b.dataset.tab));
$("btn-cluster").addEventListener("click", findClusters);
$("btn-cluster-apply").addEventListener("click", applyClusters);
$("btn-report-cluster").addEventListener("click", reportClusters);
$("btn-cluster-code").addEventListener("click", () => app.clusters &&
  openCodeDialog("Clusters as scikit-learn code", "Rebuilds your data and the same cluster numbers (fixed seed).", app.clusters.code, "clusters.py"));

/* ---- forecasting ------------------------------------------------------ */

let forecastValues = {};
let forecastSeq = 0;

function renderForecastFields() {
  const dates = datetimeCols();
  if (!dates.length) {
    $("forecast-fields").replaceChildren(el("p", { class: "muted no-inputs", text: "No date columns yet. Use Convert to date in Clean first." }),
      el("button", { class: "btn btn-sm", onclick: () => openFix({ method: "TO_DATETIME", label: "Convert to date" }) },
        icon("i-clean"), "Convert to date…"));
    $("btn-forecast").disabled = true;
    return;
  }
  $("btn-forecast").disabled = false;
  const memory = (app.forms.forecast ||= {});
  const specs = [
    { key: "date", label: "Date column", type: "select", options: dates },
    { key: "value", label: "Value", type: "select", rerender: true,
      options: [{ value: "", label: "Number of rows" }, ...numericCols()], default: numericCols()[0] || "" },
  ];
  if (memory.value) {
    specs.push({ key: "agg", label: "Combine with", type: "select", default: "sum",
      options: toOptions([["sum", "Sum"], ["mean", "Mean"], ["median", "Median"], ["count", "Count (non-empty)"]]) });
  }
  specs.push(
    { key: "freq", label: "Period", type: "select", default: "M",
      options: toOptions([["D", "Day"], ["W", "Week"], ["M", "Month"], ["Q", "Quarter"], ["Y", "Year"]]) },
    { key: "horizon", label: "Forecast ahead", type: "select",
      options: toOptions([["", "Automatic (one season)"], ["3", "3 periods"], ["6", "6 periods"], ["12", "12 periods"], ["24", "24 periods"]]) },
  );
  forecastValues = buildForm($("forecast-fields"), specs, memory, (values, key) => {
    forecastValues = values;
    if (key === "value") renderForecastFields();
  });
}

async function runForecast() {
  if (!app.state || !forecastValues.date) return;
  const v = forecastValues;
  const params = { date: v.date, value: v.value || null, agg: v.value ? v.agg || "sum" : "count", freq: v.freq || "M",
    horizon: v.horizon ? Number(v.horizon) : null };
  const seq = ++forecastSeq;
  const out = $("forecast-output");
  const loading = el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Fitting and backtesting…");
  out.replaceChildren(loading);
  $("btn-forecast").disabled = true;
  const hideCancel = delayedCancel(loading, "forecast", () => seq === forecastSeq && out.replaceChildren(note("info", "Cancelled.")));
  try {
    const res = await callLatest("forecast", "forecast", { params });
    if (seq !== forecastSeq) return;
    app.forecast = res;
    $("forecast-title").textContent = trf("Forecast: {0} per {1}", tr(res.label), tr(res.unit));
    $("forecast-sub").textContent = tr(res.method);
    $("forecast-actions").hidden = false;
    out.replaceChildren(forecastView(res));
  } catch (err) {
    if (seq !== forecastSeq || isCancelled(err)) return;
    app.forecast = null;
    $("forecast-actions").hidden = true;
    out.replaceChildren(note("warn", cleanError(err)));
  } finally {
    hideCancel();
    $("btn-forecast").disabled = false;
  }
}

function forecastChart(res) {
  const W = 800, H = 260, L = 60, R = 12, T = 12, B = 30;
  const hist = res.history, fc = res.forecast;
  const keep = Math.min(hist.values.length, Math.max(24, fc.values.length * 3));
  const hv = hist.values.slice(-keep), hp = hist.periods.slice(-keep);
  const periods = [...hp, ...fc.periods];
  const n = periods.length;
  const bt = res.backtest;
  const all = [...hv, ...fc.low95, ...fc.high95, ...(bt ? bt.predicted : [])].filter((v) => v != null);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi === lo) hi = lo + 1;
  const x = (i) => L + (i / Math.max(1, n - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const svg = svgNode("svg", { viewBox: `0 0 ${W} ${H}`, class: "trend-svg", role: "img", "aria-label": "History and forecast" });
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    svg.append(svgNode("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "trend-grid" }),
      svgNode("text", { x: L - 8, y: y(v) + 4, class: "trend-axis", "text-anchor": "end" }, fnum(v)));
  }
  const start = hv.length;
  const area = (lowKey, highKey, cls) => {
    const top = fc[highKey].map((v, i) => `${x(start + i)},${y(v)}`);
    const bottom = fc[lowKey].map((v, i) => `${x(start + i)},${y(v)}`).reverse();
    const join = `${x(start - 1)},${y(hv[hv.length - 1])}`;
    svg.append(svgNode("polygon", { points: [join, ...top, ...bottom].join(" "), class: cls }));
  };
  area("low95", "high95", "fc-band95");
  area("low80", "high80", "fc-band80");
  svg.append(svgNode("line", { x1: x(start - 0.5), x2: x(start - 0.5), y1: T, y2: H - B, class: "fc-split" }));
  if (bt) {
    const off = hv.length - bt.predicted.length;
    svg.append(svgNode("polyline", { points: bt.predicted.map((v, i) => `${x(off + i)},${y(v)}`).join(" "), class: "fc-backtest" }));
  }
  svg.append(svgNode("polyline", { points: hv.map((v, i) => `${x(i)},${y(v)}`).join(" "), class: "trend-line" }));
  svg.append(svgNode("polyline", { points: [`${x(start - 1)},${y(hv[hv.length - 1])}`, ...fc.values.map((v, i) => `${x(start + i)},${y(v)}`)].join(" "), class: "fc-line" }));
  for (const i of [0, start - 1, n - 1]) {
    svg.append(svgNode("text", { x: x(i), y: H - 8, class: "trend-axis", "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, periods[i]));
  }
  return svg;
}

function forecastView(res) {
  const bt = res.backtest;
  const trust = bt && bt.beatsNaive;
  const verdict = el("div", { class: `test-verdict ${trust ? "found" : "none"}` },
    el("div", { class: "test-verdict-label", text: bt ? (trust ? "Forecast beat the simple benchmark in the backtest" : "Use with care: no better than a simple benchmark") : "No backtest possible" }),
    el("ul", { class: "fc-insights" }, res.insights.map((t) => el("li", { text: t }))));
  const legend = el("div", { class: "trend-legend muted" },
    el("span", { class: "trend-key value" }), "history", el("span", { class: "trend-key fc-key" }), "forecast",
    el("span", { class: "trend-key band-key" }), "80% / 95% range",
    bt ? el("span", { class: "trend-key bt-key" }) : null, bt ? "backtest forecast" : null);
  const chart = el("div", { class: "trend-chart" }, forecastChart(res), legend);
  const f = res.forecast;
  const table = el("div", { class: "table-wrap trend-table" },
    el("table", { class: "test-table" },
      el("thead", {}, el("tr", {}, ["Period", "Forecast", "80% range", "95% range"].map((h, i) => el("th", { text: h, class: i ? "num" : null })))),
      el("tbody", {}, f.periods.map((p, i) => el("tr", {},
        el("td", { text: p }), el("td", { class: "num", text: fnum(f.values[i]) }),
        el("td", { class: "num muted", text: `${fnum(f.low80[i])} … ${fnum(f.high80[i])}` }),
        el("td", { class: "num muted", text: `${fnum(f.low95[i])} … ${fnum(f.high95[i])}` }))))));
  const backtest = bt
    ? el("div", { class: "card" }, el("h2", { text: "Backtest: how wrong would it have been?" }),
      el("p", { class: "card-hint", text: `The model was refitted without the last ${bt.periods.length} ${res.unit}s and asked to forecast them.` }),
      el("div", { class: "stats" },
        stat("Model error (MAE)", fnum(bt.mae), bt.mape != null ? `${bt.mape.toFixed(1)}% of the actual values on average` : "average absolute error",
          bt.beatsNaive ? "good" : "warn"),
        stat("Simple benchmark", fnum(bt.naiveMae), `error of “${bt.naive}”`)))
    : null;
  const notes = res.notes.length ? el("div", { class: "chart-footnotes" }, res.notes.map((t) => el("p", { text: t }))) : null;
  return el("div", { class: "test-body" }, verdict, chart, backtest, table, notes);
}

function reportForecast() {
  if (!app.forecast) return;
  const r = app.forecast;
  const f = r.forecast;
  addToReport({ type: "table", title: `Forecast: ${r.label} per ${r.unit} (${r.method.toLowerCase()})`,
    table: { columns: ["Period", "Forecast", "Low (80%)", "High (80%)"], data: f.periods.map((p, i) => [p, f.values[i], f.low80[i], f.high80[i]]) },
    notes: [...r.insights, ...r.notes] });
}

$("btn-forecast").addEventListener("click", runForecast);
$("btn-report-forecast").addEventListener("click", reportForecast);
$("btn-forecast-code").addEventListener("click", () => app.forecast &&
  openCodeDialog("Forecast as statsmodels code", "Rebuilds the period series, fits the same model and prints the forecast and backtest error.", app.forecast.code, "forecast.py"));

/* ------------------------------------------------------------------ */
/* interactive charts (ECharts)                                         */
/* ------------------------------------------------------------------ */

function chartMode() {
  try {
    return localStorage.getItem("chartMode") === "image" ? "image" : "interactive";
  } catch {
    return "interactive";
  }
}

function setChartMode(mode) {
  try { localStorage.setItem("chartMode", mode); } catch { /* per-viewer convenience only */ }
  showChartView();
}

function disposeEchart() {
  if (app.echart) {
    app.echart.dispose();
    app.echart = null;
  }
}

/** Show the current chart as an interactive ECharts view or as the exported image. */
function showChartView() {
  const mode = chartMode();
  for (const b of document.querySelectorAll("#chart-mode button")) b.setAttribute("aria-selected", String(b.dataset.mode === mode));
  const out = $("chart-output");
  disposeEchart();
  if (!app.chartImage) return;
  const alt = `${chartLabel()}: ${chartSubtitle(app.chartKind, chartValues)}`;
  if (mode === "image" || !app.chartSpec || typeof echarts === "undefined") {
    out.replaceChildren(el("img", { src: app.chartImage, alt }));
    return;
  }
  const box = el("div", { class: "echart", role: "img", "aria-label": alt });
  out.replaceChildren(box);
  try {
    const spec = app.chartSpec;
    const height = spec.type === "pair" ? Math.min(760, 160 * spec.columns.length + 60)
      : spec.type === "heat" ? Math.min(720, 46 * spec.columns.length + 140)
      : spec.type === "bar" && spec.horizontal ? Math.max(360, 26 * spec.labels.length + 80) : 440;
    box.style.height = `${height}px`;
    app.echart = echarts.init(box, null, { renderer: "canvas" });
    app.echart.setOption(echartOption(spec, chartStyle()));
    app.echart.on("click", (p) => onChartClick(spec, p));
  } catch (err) {
    console.warn("Interactive chart failed, showing the image instead:", err);
    disposeEchart();
    out.replaceChildren(el("img", { src: app.chartImage, alt }));
  }
}

const chartResize = new ResizeObserver(() => app.echart && app.echart.resize());
chartResize.observe($("chart-output"));

function echartOption(spec, t) {
  const axis = { axisLine: { lineStyle: { color: t.border } }, axisLabel: { color: t.muted }, splitLine: { lineStyle: { color: t.border, opacity: 0.6 } },
    nameTextStyle: { color: t.muted }, nameLocation: "middle" };
  const base = {
    backgroundColor: "transparent", color: t.palette, textStyle: { color: t.text, fontFamily: getComputedStyle(document.body).fontFamily },
    // Rich-text tooltips are drawn on the canvas: no HTML, so nothing clashes with the strict CSP.
    tooltip: { renderMode: "richText", backgroundColor: t.surface, borderColor: t.border, textStyle: { color: t.text }, confine: true },
    legend: { textStyle: { color: t.muted }, top: 0, type: "scroll" },
    grid: { left: 64, right: 24, top: 36, bottom: 56, containLabel: false },
    animationDuration: 300,
  };
  const zoom = (dims) => dims.map((d) => ({ type: "inside", [`${d}AxisIndex`]: 0, filterMode: "none" }));
  switch (spec.type) {
    case "hist": {
      const labels = spec.edges.slice(0, -1).map((e, i) => `${fnum(e)}–${fnum(spec.edges[i + 1])}`);
      const medianBin = spec.edges.findIndex((e, i) => i < spec.edges.length - 1 && spec.median >= e && spec.median <= spec.edges[i + 1]);
      return { ...base, legend: { ...base.legend, show: spec.series.length > 1 },
        tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
        xAxis: { ...axis, type: "category", data: labels, name: spec.x, nameGap: 36, axisLabel: { color: t.muted, hideOverlap: true } },
        yAxis: { ...axis, type: "value", name: tr("Count"), nameGap: 44 },
        dataZoom: zoom(["x"]),
        series: spec.series.map((sr, i) => ({ type: "bar", name: sr.name, data: sr.counts, barCategoryGap: "4%", barGap: "-100%",
          itemStyle: { opacity: spec.series.length > 1 ? 0.55 : 0.9 },
          markLine: i === 0 && medianBin >= 0 ? { symbol: "none", silent: true, label: { formatter: `median ${fnum(spec.median)}`, color: t.muted },
            lineStyle: { color: t.text, type: "dashed", opacity: 0.6 }, data: [{ xAxis: medianBin }] } : undefined })) };
    }
    case "box":
      return { ...base, legend: { show: false }, tooltip: { ...base.tooltip, trigger: "item" },
        xAxis: { ...axis, type: "category", data: spec.boxes.map((b) => b.name), name: spec.x || "", nameGap: 36, axisLabel: { color: t.muted, hideOverlap: true } },
        yAxis: { ...axis, type: spec.log ? "log" : "value", name: spec.y, nameGap: 50, scale: true },
        series: [
          { type: "boxplot", name: spec.y, data: spec.boxes.map((b) => b.stats), itemStyle: { color: `${t.palette[0]}33`, borderColor: t.palette[0] },
            tooltip: { formatter: (p) => { const b = spec.boxes[p.dataIndex]; const [lo, q1, md, q3, hi] = b.stats;
              return `${plain(b.name)} (n=${fmt(b.n)})\nmax ${fnum(hi)}\nQ3 ${fnum(q3)}\nmedian ${fnum(md)}\nQ1 ${fnum(q1)}\nmin ${fnum(lo)}`; } } },
          { type: "scatter", name: "outliers", symbolSize: 5, itemStyle: { color: t.negative, opacity: 0.7 },
            data: spec.boxes.flatMap((b, i) => b.outliers.map((o) => [i, o])) },
        ] };
    case "scatter": {
      const series = spec.series.map((sr) => ({ type: "scatter", name: sr.name, data: sr.points, symbolSize: sr.points.length > 1500 ? 4 : 7,
        itemStyle: { opacity: sr.points.length > 1500 ? 0.45 : 0.75 } }));
      if (spec.trend) series.push({ type: "line", name: "trend", data: spec.trend, symbol: "none", lineStyle: { type: "dashed", color: t.text, opacity: 0.7 }, tooltip: { show: false } });
      return { ...base, legend: { ...base.legend, show: !!spec.hue || !!spec.trend },
        tooltip: { ...base.tooltip, trigger: "item", formatter: (p) => `${plain(p.seriesName)}\n${plain(spec.x)}: ${fnum(p.value[0])}\n${plain(spec.y)}: ${fnum(p.value[1])}` },
        xAxis: { ...axis, type: spec.logX ? "log" : "value", name: spec.x, nameGap: 32, scale: true },
        yAxis: { ...axis, type: spec.logY ? "log" : "value", name: spec.y, nameGap: 50, scale: true },
        dataZoom: zoom(["x", "y"]), series };
    }
    case "heat": {
      const k = spec.columns.length;
      const data = [];
      spec.matrix.forEach((row, i) => row.forEach((v, j) => { if (j <= i && v != null) data.push([j, i, Number(v.toFixed(2))]); }));
      return { ...base, legend: { show: false }, grid: { left: 120, right: 80, top: 20, bottom: 110 },
        tooltip: { ...base.tooltip, formatter: (p) => `${plain(spec.columns[p.value[1]])} × ${plain(spec.columns[p.value[0]])}\nr = ${p.value[2].toFixed(2)}\n(click to plot them)` },
        xAxis: { ...axis, type: "category", data: spec.columns, axisLabel: { color: t.muted, rotate: 35, interval: 0 }, splitArea: { show: false } },
        yAxis: { ...axis, type: "category", data: spec.columns, inverse: true, axisLabel: { color: t.muted, interval: 0 } },
        visualMap: { min: -1, max: 1, calculable: true, orient: "vertical", right: 8, top: "middle", textStyle: { color: t.muted },
          inRange: { color: [t.negative, t.surface, t.positive] } },
        series: [{ type: "heatmap", data, label: { show: k <= 12, color: t.text, fontSize: 11 }, itemStyle: { borderColor: t.surface, borderWidth: 1 } }] };
    }
    case "line":
      return { ...base, legend: { show: false }, tooltip: { ...base.tooltip, trigger: "axis" },
        xAxis: { ...axis, type: "category", data: spec.points.map((p) => p[0]), name: spec.x, nameGap: 32, boundaryGap: false, axisLabel: { color: t.muted, hideOverlap: true } },
        yAxis: { ...axis, type: "value", name: spec.y, nameGap: 50, scale: true },
        dataZoom: spec.points.length > 30 ? [{ type: "inside" }, { type: "slider", height: 18, bottom: 6, borderColor: t.border, textStyle: { color: t.muted } }] : [{ type: "inside" }],
        grid: { ...base.grid, bottom: spec.points.length > 30 ? 70 : 56 },
        series: [{ type: "line", name: tr(spec.how), data: spec.points.map((p) => p[1]), showSymbol: spec.points.length <= 60, smooth: false, lineStyle: { width: 2 } }] };
    case "bar": {
      const pct = spec.percentOf;
      const label = { show: spec.labels.length <= 30, position: spec.horizontal ? "right" : "top", color: t.muted, fontSize: 11,
        formatter: (p) => (pct ? `${((p.value / pct) * 100).toFixed(0)}%` : fnum(p.value)) };
      const cat = { ...axis, type: "category", data: spec.labels, inverse: spec.horizontal, axisLabel: { color: t.muted, hideOverlap: !spec.horizontal, interval: spec.horizontal ? 0 : "auto", width: 140, overflow: "truncate" } };
      const val = { ...axis, type: "value", name: tr(spec.valueLabel), nameGap: spec.horizontal ? 30 : 50 };
      return { ...base, legend: { show: false }, tooltip: { ...base.tooltip, trigger: "axis", axisPointer: { type: "shadow" },
          formatter: (ps) => { const p = ps[0]; return `${plain(p.name)}\n${plain(spec.valueLabel)}: ${fnum(p.value)}${pct ? ` (${((p.value / pct) * 100).toFixed(1)}%)` : ""}\n(click for options)`; } },
        grid: spec.horizontal ? { left: 150, right: 56, top: 20, bottom: 44 } : base.grid,
        xAxis: spec.horizontal ? val : cat, yAxis: spec.horizontal ? cat : val,
        series: [{ type: "bar", data: spec.values, label, barMaxWidth: 56, itemStyle: { borderRadius: spec.horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] } }] };
    }
    case "pair": {
      const k = spec.columns.length;
      const gap = 4, cell = 100 / k;
      const grids = [], xAxes = [], yAxes = [], series = [];
      const groups = spec.groups || [null];
      for (let i = 0; i < k; i++) {
        for (let j = 0; j <= i; j++) {
          const idx = grids.length;
          grids.push({ left: `${6 + j * cell * 0.92}%`, top: `${4 + i * cell * 0.88}%`, width: `${cell * 0.92 - gap}%`, height: `${cell * 0.88 - gap}%` });
          const showX = i === k - 1, showY = j === 0;
          xAxes.push({ ...axis, gridIndex: idx, type: i === j ? "category" : "value", scale: true, name: showX ? spec.columns[j] : "", nameGap: 22,
            axisLabel: { show: showX, color: t.muted, fontSize: 9, hideOverlap: true }, splitLine: { show: false },
            data: i === j ? spec.edges[spec.columns[j]].slice(0, -1).map((e) => fnum(e)) : undefined });
          yAxes.push({ ...axis, gridIndex: idx, type: "value", scale: i !== j, name: showY && i !== j ? spec.columns[i] : "", nameGap: 36,
            axisLabel: { show: showY && i !== j, color: t.muted, fontSize: 9 }, splitLine: { show: false } });
          if (i === j) {
            const edges = spec.edges[spec.columns[i]];
            groups.forEach((g) => {
              const counts = new Array(edges.length - 1).fill(0);
              for (const r of spec.rows) {
                if (g !== null && r[k] !== g) continue;
                const v = r[i];
                if (v == null) continue;
                let b = edges.findIndex((e, q) => q < edges.length - 1 && v >= e && v <= edges[q + 1]);
                if (b < 0) b = v < edges[0] ? 0 : edges.length - 2;
                counts[b] += 1;
              }
              series.push({ type: "bar", name: g ?? spec.columns[i], xAxisIndex: idx, yAxisIndex: idx, data: counts, barCategoryGap: "8%", barGap: "-100%",
                itemStyle: { opacity: groups.length > 1 ? 0.55 : 0.85, color: t.palette[Math.max(0, groups.indexOf(g)) % t.palette.length] } });
            });
          } else {
            groups.forEach((g, gi) => series.push({ type: "scatter", name: g ?? "rows", xAxisIndex: idx, yAxisIndex: idx, symbolSize: 4,
              itemStyle: { opacity: 0.6, color: t.palette[gi % t.palette.length] },
              data: spec.rows.filter((r) => g === null || r[k] === g).map((r) => [r[j], r[i]]) }));
          }
        }
      }
      return { ...base, legend: { ...base.legend, show: groups.length > 1, data: groups.filter(Boolean) },
        tooltip: { ...base.tooltip, trigger: "item" }, grid: grids, xAxis: xAxes, yAxis: yAxes, series };
    }
    default:
      return {};
  }
}

/** Text for rich-text tooltips: braces and pipes are rich-text syntax, so drop them from data values. */
const plain = (text) => String(text).replace(/[{}|]/g, " ");

/* ---- click → filter / compare ----------------------------------------- */

function chartActions(items) {
  const box = el("div", { class: "chart-actions", role: "menu" },
    items.map(([label, fn]) => el("button", { class: "btn btn-sm", role: "menuitem", onclick: () => { box.remove(); fn(); } }, label)),
    el("button", { class: "icon-btn", title: "Close", "aria-label": "Close", onclick: () => box.remove() }, icon("i-x")));
  document.querySelectorAll(".chart-actions").forEach((n) => n.remove());
  $("chart-output").append(box);
  return box;
}

function compareSegment(conditions) {
  app.forms.segment = { count: conditions.length };
  conditions.forEach((c, i) => Object.assign(app.forms.segment, { [`c${i}_column`]: c.column, [`c${i}_operator`]: c.operator, [`c${i}_value`]: String(c.value) }));
  showSection("analyze");
  selectAnalyzeTab("segment");
  renderSegmentFields(true);
}

function keepCategory(column, value) {
  openFix({ method: "FILTER_ROWS", params: { mode: "keep", column, operator: "==", value: String(value) } });
}

function onChartClick(spec, p) {
  const at = (box) => {
    const e = p.event && p.event.event;
    if (!e) return;
    const rect = $("chart-output").getBoundingClientRect();
    box.style.left = `${Math.min(rect.width - 260, Math.max(8, e.clientX - rect.left + 8))}px`;
    box.style.top = `${Math.max(8, e.clientY - rect.top + 8)}px`;
  };
  if (spec.type === "bar" && spec.column && p.componentType === "series") {
    const value = spec.labels[p.dataIndex];
    at(chartActions([[`Keep only ${spec.column} = ${value}`, () => keepCategory(spec.column, value)],
      [`Compare ${value} with the rest`, () => compareSegment([{ column: spec.column, operator: "==", value }])]]));
  } else if (spec.type === "box" && spec.x && p.seriesType === "boxplot") {
    const value = spec.boxes[p.dataIndex].name;
    at(chartActions([[`Keep only ${spec.x} = ${value}`, () => keepCategory(spec.x, value)],
      [`Compare ${value} with the rest`, () => compareSegment([{ column: spec.x, operator: "==", value }])]]));
  } else if (spec.type === "hist" && p.componentType === "series") {
    const lo = spec.edges[p.dataIndex], hi = spec.edges[p.dataIndex + 1];
    at(chartActions([[`Compare ${spec.x} ${fnum(lo)}–${fnum(hi)} with the rest`,
      () => compareSegment([{ column: spec.x, operator: ">=", value: lo }, { column: spec.x, operator: "<=", value: hi }])]]));
  } else if (spec.type === "heat" && p.componentType === "series") {
    const [j, i] = p.value;
    if (i !== j) {
      selectChart("SCAT", { x: spec.columns[j], y: spec.columns[i] });
    }
  }
}

for (const b of document.querySelectorAll("#chart-mode button")) b.addEventListener("click", () => setChartMode(b.dataset.mode));

/* ------------------------------------------------------------------ */
/* dashboard                                                            */
/* ------------------------------------------------------------------ */

const DASH_KEY = "databoss.dashboard.v1";

function loadDashboard() {
  try {
    const saved = JSON.parse(localStorage.getItem(DASH_KEY) || "null");
    if (saved && Array.isArray(saved.tiles)) return saved;
  } catch { /* start empty */ }
  return { tiles: [] };
}
function saveDashboard() {
  try { localStorage.setItem(DASH_KEY, JSON.stringify(app.dashboard)); } catch { /* not critical */ }
}
app.dashboard = loadDashboard();
app.dashCharts = [];
let dashSeq = 0;

function syncDashBadge() {
  const n = app.dashboard.tiles.length;
  $("nav-dash-badge").hidden = !n;
  $("nav-dash-badge").textContent = String(n);
}

function pinTile(tile) {
  app.dashboard.tiles.push({ id: `t${Date.now()}${Math.floor(Math.random() * 1000)}`, ...tile });
  saveDashboard();
  syncDashBadge();
  app.dashStale = true;
  toast("success", `Pinned to the dashboard (${plural(app.dashboard.tiles.length, "tile")}).`);
}

function pinChart() {
  if (!app.chartKind || !app.chartParams) return;
  pinTile({ type: "chart", kind: app.chartKind, params: app.chartParams, title: `${chartLabel()}: ${chartSubtitle(app.chartKind, chartValues)}` });
}

function pinPivot() {
  if (!app.pivot) return;
  pinTile({ type: "pivot", params: app.pivot.params, title: `Pivot: ${pivotSubtitle(app.pivot.params)}` });
}

function disposeDashCharts() {
  for (const c of app.dashCharts) c.dispose();
  app.dashCharts = [];
}

function moveTile(i, delta) {
  const t = app.dashboard.tiles;
  const j = i + delta;
  if (j < 0 || j >= t.length) return;
  [t[i], t[j]] = [t[j], t[i]];
  saveDashboard();
  renderDashboard();
}

/** Draw every tile from the current data. Tiles render one after another on the worker. */
async function renderDashboard() {
  if (!app.state) return;
  const seq = ++dashSeq;
  app.dashStale = false;
  syncDashBadge();
  disposeDashCharts();
  const tiles = app.dashboard.tiles;
  const grid = $("dash-grid");
  $("btn-dash-report").disabled = !tiles.length;
  const last = app.state.log.at(-1);
  $("dash-updated").textContent = tr(tiles.length ? (last ? `Data as of step ${last.step}: ${last.msg}` : "Original data") : "");
  if (!tiles.length) {
    grid.replaceChildren(el("div", { class: "card report-empty dash-empty" },
      el("h2", { text: "Nothing pinned yet" }),
      el("p", { class: "card-hint", text: "Use Pin on a chart in Visualize or on a pivot table in Analyze. Pinned items stay here and redraw from the current data after every cleaning step, undo or new query." })));
    return;
  }
  const bodies = tiles.map(() => el("div", { class: "dash-body" }, el("div", { class: "inline-loading" }, el("span", { class: "impact-dot pulse" }), "Drawing…")));
  grid.replaceChildren(...tiles.map((t, i) =>
    el("div", { class: `card dash-tile ${t.type === "pivot" ? "dash-pivot" : ""}`, "data-type": t.type },
      el("div", { class: "dash-head" },
        el("strong", { class: "dash-title", text: t.title, title: t.title }),
        el("button", { class: "icon-btn", title: "Move earlier", "aria-label": "Move earlier", disabled: i === 0, onclick: () => moveTile(i, -1) }, icon("i-up")),
        el("button", { class: "icon-btn", title: "Move later", "aria-label": "Move later", disabled: i === tiles.length - 1, onclick: () => moveTile(i, 1) }, icon("i-down")),
        el("button", { class: "icon-btn", title: "Open to edit", "aria-label": "Open to edit", onclick: () => openTile(t) }, icon("i-play")),
        el("button", { class: "icon-btn", title: "Unpin", "aria-label": "Unpin", onclick: () => {
          tiles.splice(i, 1);
          saveDashboard();
          renderDashboard();
        } }, icon("i-x"))),
      bodies[i])));
  for (let i = 0; i < tiles.length; i++) {
    if (seq !== dashSeq) return;
    const t = tiles[i];
    try {
      if (t.type === "chart") {
        const res = await window.api.call("plot", { kind: t.kind, params: t.params, style: chartStyle(), width: 640 });
        if (seq !== dashSeq) return;
        const box = el("div", { class: "echart dash-chart" });
        bodies[i].replaceChildren(box);
        if (res.spec && typeof echarts !== "undefined") {
          const chart = echarts.init(box, null, { renderer: "canvas" });
          chart.setOption(echartOption(res.spec, chartStyle()));
          app.dashCharts.push(chart);
        } else {
          box.replaceChildren(el("img", { src: res.image, alt: t.title }));
        }
        if (res.insights.length) bodies[i].append(el("p", { class: "dash-insight", text: res.insights[0] }));
      } else {
        const res = await window.api.call("pivot", { params: t.params });
        if (seq !== dashSeq) return;
        bodies[i].replaceChildren(pivotTable(res));
      }
    } catch (err) {
      if (seq !== dashSeq) return;
      bodies[i].replaceChildren(note("warn", `Can't draw this with the current data: ${cleanError(err)}`));
    }
  }
}

function openTile(t) {
  if (t.type === "chart") {
    showSection("visualize");
    selectChart(t.kind, chartFormFromParams(t.kind, t.params));
  } else {
    app.forms.pivot = { rows: t.params.rows, columns: t.params.columns || "", values: t.params.values || "", agg: t.params.agg,
      percent: t.params.percent, sort: t.params.sort, totals: t.params.totals };
    showSection("analyze");
    selectAnalyzeTab("pivot");
    renderPivotFields(true);
  }
}

/** Chart form values from saved chart params (the form uses strings for some fields). */
function chartFormFromParams(kind, params) {
  const out = {};
  for (const [k, v] of Object.entries(params || {})) out[k] = typeof v === "number" ? String(v) : v;
  return out;
}

const dashResize = new ResizeObserver(() => app.dashCharts.forEach((c) => c.resize()));
dashResize.observe($("dash-grid"));

/** Fresh light-theme images/tables of every tile, for a report export. */
async function dashboardForReport() {
  const out = [];
  for (const t of app.dashboard.tiles) {
    try {
      if (t.type === "chart") {
        const res = await window.api.call("plot", { kind: t.kind, params: t.params, style: lightChartStyle(), width: 900 });
        out.push({ type: "chart", title: t.title, image: res.image, insights: res.insights.slice(0, 2), notes: [] });
      } else {
        const res = await window.api.call("pivot", { params: t.params });
        out.push({ type: "table", title: t.title, table: { columns: res.table.columns, data: res.table.data.slice(0, 200) },
          truncated: res.table.data.length > 200, percent: res.percent, valueColumns: res.valueColumns, notes: res.notes });
      }
    } catch (err) {
      out.push({ type: "text", text: `${t.title}: can't be drawn with the current data (${cleanError(err)}).` });
    }
  }
  return out;
}

$("btn-pin-chart").addEventListener("click", pinChart);
$("btn-pin-pivot").addEventListener("click", pinPivot);
$("btn-dash-report").addEventListener("click", () => {
  if (!app.dashboard.tiles.length) return;
  addToReport({ type: "dashboard", title: "Dashboard" });
});
syncDashBadge();

/* ---- interface language -------------------------------------------- */

(function setupLanguageButton() {
  const other = i18n.lang === "ar" ? { code: "en", name: "English" } : { code: "ar", name: "العربية" };
  const label = $("lang-label");
  label.textContent = other.name;
  label.lang = other.code;
  $("btn-lang").addEventListener("click", async () => {
    try {
      await window.api.setLanguage(other.code); // saved, then the window reloads in the new language
    } catch (err) {
      toast("error", cleanError(err));
    }
  });
})();

/** After a reload (e.g. a language switch) the engine still holds the data: show it again. */
(async function restoreSession() {
  try {
    const snapshot = await window.api.call("state");
    if (snapshot && snapshot.shape) onLoaded(snapshot);
  } catch {
    /* nothing loaded yet */
  }
})();

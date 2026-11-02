/* Interface language.
 *
 * Translations live in renderer/i18n/<lang>.json as {"English text": "translation"}.
 * The English sentence is the key (like gettext), so code keeps readable English
 * and anything without a translation simply shows in English.
 *
 * Keys may contain placeholders {0}, {1}, … for text built at runtime, e.g.
 *   "Removed {0} duplicate rows.": "تمت إزالة {0} من الصفوف المكررة."
 * Placeholders are matched against the displayed text, and the captured parts are
 * themselves translated when a translation exists (e.g. column kinds).
 */
(function () {
  const locale = window.locale || { lang: "en", messages: {} };
  const lang = locale.lang || "en";
  // Keys and looked-up text are compared with whitespace collapsed (non-breaking spaces, line breaks).
  const norm = (t) => t.replace(/\s+/g, " ").trim();
  const messages = {};
  for (const [k, v] of Object.entries(locale.messages || {})) if (!k.startsWith("_")) messages[norm(k)] = v;
  const rtl = lang === "ar";
  document.documentElement.lang = lang;
  document.documentElement.dir = rtl ? "rtl" : "ltr";

  // Placeholder templates, indexed by their first word so lookups stay cheap.
  const patterns = new Map();
  for (const [key, value] of Object.entries(messages)) {
    if (!/\{\d+\}/.test(key)) continue;
    const parts = key.split(/(\{\d+\})/);
    const order = [];
    const source = parts
      .map((p) => {
        const m = /^\{(\d+)\}$/.exec(p);
        if (m) {
          order.push(Number(m[1]));
          return "([\\s\\S]+?)";
        }
        return p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      })
      .join("");
    const specificity = key.replace(/\{\d+\}/g, "").trim().length;
    // Templates that join several placeholders with a tiny connector ("{0} by {1}") would grab unrelated
    // sentences; those are only used through trf(). Single-placeholder ones ("{0} cells") are safe.
    if (order.length > 1 && specificity < 6) continue;
    const re = new RegExp(`^${source}$`);
    const firstToken = key.split(/\s/)[0];
    const first = /\{\d+\}/.test(firstToken) ? "{" : firstToken;
    if (!patterns.has(first)) patterns.set(first, []);
    patterns.get(first).push({ re, order, value, specificity });
  }
  for (const list of patterns.values()) list.sort((a, b) => b.specificity - a.specificity);

  const misses = locale.collect ? new Set() : null;
  if (misses && window.i18nCollect) {
    let sent = 0;
    setInterval(() => {
      const all = [...misses];
      if (all.length > sent) {
        window.i18nCollect(all.slice(sent));
        sent = all.length;
      }
    }, 500);
  }

  function lookup(text) {
    if (Object.prototype.hasOwnProperty.call(messages, text)) return messages[text];
    const first = text.split(/\s/)[0];
    for (const bucket of [patterns.get(first), patterns.get("{")]) {
      if (!bucket) continue;
      for (const p of bucket) {
        const m = p.re.exec(text);
        if (!m) continue;
        const args = [];
        p.order.forEach((index, i) => { args[index] = m[i + 1]; });
        return p.value.replace(/\{(\d+)\}/g, (_, n) => {
          const arg = args[Number(n)] ?? "";
          if (arg.length >= text.length) return arg; // never loop on the same text
          const inner = /[A-Za-z]/.test(arg) ? lookup(arg.trim()) : null;
          return inner == null ? arg : inner;
        });
      }
    }
    return null;
  }

  /** Translate one piece of interface text (returns it unchanged in English or when unknown). */
  function tr(text) {
    if (typeof text !== "string" || !text.trim()) return text;
    if (lang === "en") {
      if (misses) misses.add(text);
      return text;
    }
    const lead = text.match(/^\s*/)[0];
    const tail = text.match(/\s*$/)[0];
    const core = norm(text);
    const hit = lookup(core);
    if (hit == null && misses && /[A-Za-z]/.test(core)) misses.add(core); // collecting: what still needs a translation
    return hit == null ? text : lead + hit + tail;
  }

  const ATTRS = ["title", "placeholder", "aria-label"];

  /** Translate the static text of a DOM subtree (used once for index.html). */
  function translateDom(root) {
    if (lang === "en" && !misses) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement && /^(SCRIPT|STYLE|TEXTAREA)$/.test(n.parentElement.tagName) ? NodeFilter.FILTER_REJECT
        : /[A-Za-z]/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP),
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) n.nodeValue = tr(n.nodeValue);
    for (const node of root.querySelectorAll(ATTRS.map((a) => `[${a}]`).join(","))) {
      for (const a of ATTRS) if (node.hasAttribute(a)) node.setAttribute(a, tr(node.getAttribute(a)));
    }
  }

  /** Translate a template the code fills itself, e.g. trf("{0} by {1}", "fee", "plan").
   *  The template is looked up as a key; arguments (usually column names) are inserted as they are. */
  function trf(template, ...args) {
    const known = Object.prototype.hasOwnProperty.call(messages, norm(template));
    if (misses && (lang === "en" || !known)) misses.add(template);
    const t = lang === "en" || !known ? template : messages[norm(template)];
    return t.replace(/\{(\d+)\}/g, (_, n) => String(args[Number(n)] ?? ""));
  }

  window.i18n = { lang, rtl, tr, trf, translateDom, misses: () => (misses ? [...misses] : []) };
  window.tr = tr;
  window.trf = trf;
})();

// Runs in <head> so the right theme is applied before first paint.
(function () {
  let saved = null;
  try {
    saved = localStorage.getItem("theme");
  } catch {}
  const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = saved === "light" || saved === "dark" ? saved : system;
})();

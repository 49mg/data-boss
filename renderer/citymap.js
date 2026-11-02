"use strict";

/**
 * Draws a decorative city street map as an inline SVG behind the content.
 * The layout is generated from a fixed seed, so it looks the same on every
 * launch. Colours come from CSS variables, so it follows the active theme.
 */
(function drawCityMap() {
  const host = document.getElementById("map-bg");
  if (!host) return;

  const W = 1600;
  const H = 1000;
  const COLS = 5;
  const ROWS = 3;
  const NS = "http://www.w3.org/2000/svg";

  // Small deterministic PRNG (mulberry32).
  let seed = 20251101;
  const rand = () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const between = (a, b) => a + rand() * (b - a);
  const r1 = (n) => Math.round(n * 10) / 10;

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
  const defs = document.createElementNS(NS, "defs");
  svg.append(defs);

  const add = (tag, attrs, parent = svg) => {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    parent.append(node);
    return node;
  };

  // 1. Jittered vertex grid -> irregular district polygons.
  const pts = [];
  for (let r = 0; r <= ROWS; r++) {
    pts.push([]);
    for (let c = 0; c <= COLS; c++) {
      const edgeX = c === 0 || c === COLS;
      const edgeY = r === 0 || r === ROWS;
      const x = (c / COLS) * (W + 200) - 100 + (edgeX ? 0 : between(-70, 70));
      const y = (r / ROWS) * (H + 200) - 100 + (edgeY ? 0 : between(-60, 60));
      pts[r].push([x, y]);
    }
  }

  const blocks = add("g", { class: "map-minor" });

  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const poly = [pts[r][c], pts[r][c + 1], pts[r + 1][c + 1], pts[r + 1][c]];
      const id = `district-${r}-${c}`;
      const clip = add("clipPath", { id }, defs);
      add("polygon", { points: poly.map((p) => p.map(r1).join(",")).join(" ") }, clip);

      // Roughly one district in seven is a park: no streets, just a few paths.
      if (rand() < 0.14) {
        const cx = poly.reduce((s, p) => s + p[0], 0) / 4;
        const cy = poly.reduce((s, p) => s + p[1], 0) / 4;
        add("ellipse", {
          class: "map-park",
          cx: r1(cx),
          cy: r1(cy),
          rx: r1(between(70, 120)),
          ry: r1(between(50, 90)),
          "clip-path": `url(#${id})`,
        });
        continue;
      }

      // Street grid at a district-specific angle and spacing.
      const cx = poly.reduce((s, p) => s + p[0], 0) / 4;
      const cy = poly.reduce((s, p) => s + p[1], 0) / 4;
      const angle = (between(-35, 35) * Math.PI) / 180;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const R = 420;
      const d = [];
      const lines = (spacing, rot) => {
        for (let o = -R; o <= R; o += spacing) {
          if (rand() < 0.12) continue; // occasional missing street
          // Break long streets into segments so blocks look irregular.
          let t = -R;
          while (t < R) {
            const len = between(80, 260);
            const end = Math.min(R, t + len);
            if (rand() > 0.12) {
              const a = rot ? [o, t] : [t, o];
              const b = rot ? [o, end] : [end, o];
              const x1 = cx + a[0] * cos - a[1] * sin;
              const y1 = cy + a[0] * sin + a[1] * cos;
              const x2 = cx + b[0] * cos - b[1] * sin;
              const y2 = cy + b[0] * sin + b[1] * cos;
              d.push(`M${r1(x1)} ${r1(y1)}L${r1(x2)} ${r1(y2)}`);
            }
            t = end + between(0, 14);
          }
        }
      };
      lines(between(26, 40), false);
      lines(between(34, 56), true);
      add("path", { d: d.join(""), "clip-path": `url(#${id})` }, blocks);
    }
  }

  // 2. District edges become main roads.
  const roads = [];
  for (let r = 0; r <= ROWS; r++) {
    roads.push("M" + pts[r].map((p) => p.map(r1).join(" ")).join("L"));
  }
  for (let c = 0; c <= COLS; c++) {
    roads.push("M" + pts.map((row) => row[c].map(r1).join(" ")).join("L"));
  }
  add("path", { class: "map-major", d: roads.join("") });

  // 3. Ring road and two long avenues.
  add("ellipse", { class: "map-arterial", cx: 820, cy: 470, rx: 430, ry: 300 });
  add("path", { class: "map-arterial", d: "M-50 140 C 420 260, 900 520, 1650 900" });
  add("path", { class: "map-arterial", d: "M300 1050 C 520 640, 980 360, 1300 -50" });

  // 4. River across the lower part of the map.
  const river = "M-60 780 C 260 690, 520 960, 860 840 S 1380 640, 1660 730";
  add("path", { class: "map-water", d: river });
  add("path", { class: "map-water-edge", d: river });

  host.append(svg);
})();

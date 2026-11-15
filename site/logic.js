// The page's logic, free of the DOM so the tests can drive it directly:
// which filters exist, which printers match, the order, the URL state, pages.

export const PAGE_SIZE = 48;
export const COMPARE_MAX = 4;

// Every filter of the side panel, by group. A flag keeps printers that have
// the feature; a choice keeps one value; min/max keep printers at or beyond a
// threshold (a printer whose sheet does not state the value is left out).
export const GROUPS = [
  { id: "availability", open: true, filters: [
    { key: "available", type: "flag", default: true },
    { key: "new", label: "new_week", type: "flag" },
    { key: "confirmed", type: "flag" },
  ] },
  { id: "two_sided", open: true, filters: [
    { key: "duplex_print", type: "flag" },
    { key: "duplex_scan", type: "flag" },
  ] },
  { id: "technology", open: true, filters: [
    { key: "technology", type: "choice", values: ["laser", "inkjet"] },
    { key: "ink_tank", type: "flag" },
  ] },
  { id: "colour", open: true, filters: [
    { key: "color", type: "choice", values: ["1", "0"], labels: ["colour_yes", "colour_no"] },
  ] },
  { id: "functions", open: true, filters: [
    { key: "scan", type: "flag" },
    { key: "copy", type: "flag" },
    { key: "fax", type: "flag" },
    { key: "adf", type: "flag" },
    { key: "borderless", type: "flag" },
  ] },
  { id: "connectivity", open: true, filters: [
    { key: "wifi", type: "flag" },
    { key: "wifi_direct", type: "flag" },
    { key: "ethernet", type: "flag" },
    { key: "usb", type: "flag" },
    { key: "airprint", type: "flag" },
    { key: "mopria", type: "flag" },
    { key: "nfc", type: "flag" },
    { key: "bluetooth", type: "flag" },
  ] },
  { id: "paper", filters: [
    { key: "a3", type: "flag" },
    { key: "paper_input", type: "min", step: 50 },
    { key: "paper_output", type: "min", step: 25 },
    { key: "adf_capacity", type: "min", step: 10 },
    { key: "trays", type: "min", step: 1 },
  ] },
  { id: "controls", filters: [
    { key: "display", type: "flag" },
    { key: "touchscreen", type: "flag" },
  ] },
  { id: "speed", filters: [
    { key: "ppm_black", type: "min", step: 5 },
    { key: "ppm_color", type: "min", step: 5 },
    { key: "first_page_s", type: "max", step: 1 },
  ] },
  { id: "workload", filters: [
    { key: "duty_cycle", type: "min", step: 5000 },
    { key: "monthly_volume", type: "min", step: 500 },
  ] },
  { id: "quality", filters: [
    { key: "print_dpi", type: "min", step: 600 },
    { key: "scan_dpi", type: "min", step: 600 },
  ] },
  { id: "size", filters: [
    { key: "width_mm", type: "max", step: 10 },
    { key: "depth_mm", type: "max", step: 10 },
    { key: "height_mm", type: "max", step: 10 },
    { key: "weight_kg", type: "max", step: 1 },
  ] },
  { id: "energy", filters: [
    { key: "noise_db", type: "max", step: 1 },
    { key: "power_w", type: "max", step: 10 },
    { key: "tec_kwh", type: "max", step: 0.1 },
  ] },
];

export const FILTERS = GROUPS.flatMap((g) => g.filters);
const BY_KEY = Object.fromEntries(FILTERS.map((f) => [f.key, f]));

// The rows of the detail view and the comparison, in reading order.
export const SPEC_ROWS = [
  "brand", "code", "technology", "color", "ink_tank", "duplex_print", "duplex_scan",
  "scan", "copy", "fax", "adf", "adf_capacity", "borderless", "max_paper",
  "paper_input", "paper_output", "trays", "ppm_black", "ppm_color", "ppm_iso",
  "first_page_s", "print_dpi", "scan_dpi", "duty_cycle", "monthly_volume", "wifi",
  "wifi_direct", "ethernet", "usb", "airprint", "mopria", "nfc", "bluetooth",
  "display", "touchscreen", "cartridges", "starter_yield", "width_mm", "depth_mm",
  "height_mm", "weight_kg", "noise_db", "power_w", "tec_kwh", "release_date",
  "end_of_life",
];

export function emptyState() {
  const state = { q: "", year: "", markets: new Set(), brands: new Set(), sort: "name", page: 1, compare: [] };
  for (const f of FILTERS) state[f.key] = f.type === "flag" ? Boolean(f.default) : f.type === "choice" ? "" : 0;
  return state;
}

// "new" means first seen in the latest week, but not on the very first fill,
// when every printer was first seen at once.
export function prepare(data) {
  const updated = data.updated ? new Date(data.updated) : new Date();
  const week = new Date(updated - 7 * 864e5).toISOString().slice(0, 10);
  const since = data.started && data.started > week ? data.started : week;
  for (const p of data.printers) {
    p.new = Boolean(p.first_seen && p.first_seen > since);
    p.a3 = Boolean(p.max_paper && Number(p.max_paper.replace(/\D/g, "")) <= 3);
    p.confirmed = Boolean(p.confirmed && p.confirmed.length);
    p._text = `${p.brand} ${p.name} ${p.code || ""}`.toLowerCase();
    p._year = p.release_date ? Number(p.release_date.slice(0, 4)) : null;
  }
  return data.printers;
}

// The slider bounds of the min/max filters, from the values the data holds.
export function ranges(printers) {
  const out = {};
  for (const f of FILTERS) {
    if (f.type !== "min" && f.type !== "max") continue;
    let lo = Infinity, hi = -Infinity;
    for (const p of printers) {
      const v = p[f.key];
      if (typeof v === "number") { if (v < lo) lo = v; if (v > hi) hi = v; }
    }
    if (hi === -Infinity) continue;
    const step = f.step;
    out[f.key] = { min: Math.floor(lo / step) * step, max: Math.ceil(hi / step) * step, step };
  }
  return out;
}

export function matches(p, state) {
  for (const f of FILTERS) {
    const want = state[f.key];
    if (f.type === "flag") {
      if (want && !p[f.key]) return false;
    } else if (f.type === "choice") {
      if (want === "") continue;
      if (f.key === "color") { if (Boolean(p.color) !== (want === "1")) return false; }
      else if (p[f.key] !== want) return false;
    } else if (want) {
      const v = p[f.key];
      if (typeof v !== "number") return false;
      if (f.type === "min" && v < want) return false;
      if (f.type === "max" && v > want) return false;
    }
  }
  if (state.year && !(p._year >= Number(state.year))) return false;
  if (state.brands.size && !state.brands.has(p.brand)) return false;
  if (state.markets.size && !(p.markets || []).some((m) => state.markets.has(m))) return false;
  if (state.q) {
    for (const word of state.q.toLowerCase().split(/\s+/)) {
      if (word && !p._text.includes(word)) return false;
    }
  }
  return true;
}

const byName = (a, b) => a.brand.localeCompare(b.brand) || a.name.localeCompare(b.name);
const missingLast = (key, dir) => (a, b) => {
  const x = a[key], y = b[key];
  if (x == null && y == null) return byName(a, b);
  if (x == null) return 1;
  if (y == null) return -1;
  return dir * (x - y) || byName(a, b);
};

export const SORTS = {
  name: byName,
  newest: (a, b) => (b.release_date || b.first_seen || "").localeCompare(a.release_date || a.first_seen || "") || byName(a, b),
  fastest: missingLast("ppm_black", -1),
  lightest: missingLast("weight_kg", 1),
};

export function search(printers, state) {
  return printers.filter((p) => matches(p, state)).sort(SORTS[state.sort] || SORTS.name);
}

export function paginate(items, page, size = PAGE_SIZE) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(Math.max(1, page), pages);
  return { page: current, pages, items: items.slice((current - 1) * size, current * size) };
}

// Page numbers to show: the ends, the neighbours of the current one, gaps as null.
export function pageNumbers(page, pages) {
  const keep = new Set([1, pages, page - 1, page, page + 1]);
  const out = [];
  for (let n = 1; n <= pages; n++) {
    if (keep.has(n)) out.push(n);
    else if (out[out.length - 1] !== null) out.push(null);
  }
  return out;
}

export function toggleCompare(list, id, max = COMPARE_MAX) {
  if (list.includes(id)) return { list: list.filter((x) => x !== id), full: false };
  if (list.length >= max) return { list, full: true };
  return { list: [...list, id], full: false };
}

// The filters that differ from the defaults, as [key, value] for the chips.
export function activeFilters(state) {
  const out = [];
  if (state.q) out.push(["q", state.q]);
  for (const f of FILTERS) {
    const v = state[f.key];
    const off = f.type === "flag" ? Boolean(f.default) : f.type === "choice" ? "" : 0;
    if (v !== off) out.push([f.key, v]);
  }
  if (state.year) out.push(["year", state.year]);
  for (const m of state.markets) out.push(["market", m]);
  for (const b of state.brands) out.push(["brand", b]);
  return out;
}

export function clearFilter(state, key, value) {
  if (key === "q") state.q = "";
  else if (key === "year") state.year = "";
  else if (key === "market") state.markets.delete(value);
  else if (key === "brand") state.brands.delete(value);
  else if (BY_KEY[key]) {
    const f = BY_KEY[key];
    state[key] = f.type === "flag" ? Boolean(f.default) : f.type === "choice" ? "" : 0;
  }
  state.page = 1;
  return state;
}

// --- the URL: filters, sort, page and comparison, so a view can be shared ---

export function encode(state) {
  const h = new URLSearchParams();
  if (state.q) h.set("q", state.q);
  for (const f of FILTERS) {
    const v = state[f.key];
    if (f.type === "flag") { if (v !== Boolean(f.default)) h.set(f.key, v ? "1" : "0"); }
    else if (v !== "" && v !== 0) h.set(f.key, String(v));
  }
  if (state.year) h.set("year", state.year);
  if (state.markets.size) h.set("in", [...state.markets].join(","));
  if (state.brands.size) h.set("brand", [...state.brands].join(","));
  if (state.sort !== "name") h.set("sort", state.sort);
  if (state.page > 1) h.set("page", String(state.page));
  if (state.compare.length) h.set("cmp", state.compare.join(","));
  return h.toString();
}

export function decode(hash) {
  const h = new URLSearchParams(hash.replace(/^#/, ""));
  const state = emptyState();
  state.q = h.get("q") || "";
  for (const f of FILTERS) {
    if (!h.has(f.key)) continue;
    const raw = h.get(f.key);
    if (f.type === "flag") state[f.key] = raw === "1";
    else if (f.type === "choice") state[f.key] = f.values.includes(raw) ? raw : "";
    else state[f.key] = Number(raw) || 0;
  }
  state.year = h.get("year") || "";
  state.markets = new Set((h.get("in") || "").split(",").filter(Boolean));
  state.brands = new Set((h.get("brand") || "").split(",").filter(Boolean));
  state.sort = SORTS[h.get("sort")] ? h.get("sort") : "name";
  state.page = Math.max(1, Number(h.get("page")) || 1);
  state.compare = (h.get("cmp") || "").split(",").filter(Boolean).slice(0, COMPARE_MAX);
  return state;
}

// Rows where the compared printers do not all agree.
export function differingRows(printers, rows = SPEC_ROWS) {
  return rows.filter((key) => new Set(printers.map((p) => JSON.stringify(p[key] ?? null))).size > 1);
}

export function markets(printers) {
  const counts = new Map();
  for (const p of printers) for (const m of p.markets || []) counts.set(m, (counts.get(m) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function brands(printers) {
  const counts = new Map();
  for (const p of printers) counts.set(p.brand, (counts.get(p.brand) || 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

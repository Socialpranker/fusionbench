// tests/site_logic.test.mjs — node unit tests for the pure DERIVE functions in site/app.js.
// Run: node tests/site_logic.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const app = require(path.join(here, "..", "site", "app.js"));

const CELLS = [
  { type: "math", recipe: "best-single", arm: "best_single", accuracy: 0.60, cost_usd: 0.001, worthiness_vs_best: 0.0, complementarity: null, recommended: false, n: 10 },
  { type: "math", recipe: "fusion-strong", arm: "fusion", accuracy: 0.80, cost_usd: 0.004, worthiness_vs_best: 0.20, complementarity: 0.7, recommended: true, n: 10 },
  { type: "code", recipe: "best-single", arm: "best_single", accuracy: 0.90, cost_usd: 0.0009, worthiness_vs_best: 0.0, complementarity: null, recommended: true, n: 8 },
];

// applyFilters: type filter
let r = app.applyFilters(CELLS, { type: "math", maxcost: Infinity, minacc: 0, sort: "worthiness" });
assert.strictEqual(r.length, 2, "type=math keeps 2");
assert.ok(r.every(c => c.type === "math"));

// applyFilters: maxcost + minacc
r = app.applyFilters(CELLS, { type: "", maxcost: 0.002, minacc: 0.7, sort: "worthiness" });
assert.deepStrictEqual(r.map(c => c.recipe), ["best-single"], "code/best-single passes cost<=0.002 & acc>=0.7");

// applyFilters: sort by accuracy desc
r = app.applyFilters(CELLS, { type: "", maxcost: Infinity, minacc: 0, sort: "accuracy" });
assert.deepStrictEqual(r.map(c => c.accuracy), [0.90, 0.80, 0.60], "sorted by accuracy desc");

// aggregateRecipePoints: mean cost/accuracy per recipe across kept cells
const pts = app.aggregateRecipePoints(CELLS);
const bs = pts.find(p => p.recipe === "best-single");
assert.strictEqual(bs.arm, "best_single");
assert.ok(Math.abs(bs.accuracy - (0.60 + 0.90) / 2) < 1e-9, "best-single avg accuracy");
assert.ok(Math.abs(bs.cost_usd - (0.001 + 0.0009) / 2) < 1e-9, "best-single avg cost");

// paretoFrontierJS: non-dominated, cost ascending
const front = app.paretoFrontierJS(pts);
const fcosts = front.map(p => p.cost_usd);
assert.deepStrictEqual(fcosts, [...fcosts].sort((a, b) => a - b), "pareto cost ascending");
assert.ok(front.length >= 1);

// toCSV: header + escaping of commas/quotes
const csv = app.toCSV([{ type: "math", recipe: 'a,b', arm: 'q"x', accuracy: 0.5, cost_usd: 0.001, latency_s: 0, worthiness_vs_best: 0.1, worthiness_vs_self_moa: 0, complementarity: null, recommended: true, n: 5 }]);
const lines = csv.trim().split("\n");
assert.ok(lines[0].startsWith("type,recipe,arm,accuracy,cost_usd"), "csv header");
assert.ok(lines[1].includes('"a,b"'), "comma value quoted");
assert.ok(lines[1].includes('"q""x"'), "quote value escaped & doubled");

console.log("site_logic: all assertions passed");

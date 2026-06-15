// site/app.js — renders hero-Pareto and heatmap from data.json via ECharts.
// Pure view layer: all numbers are precomputed in data.json by build_catalog.py.

// ===== DERIVE: pure functions (filter / aggregate / pareto / csv) =====
// Shared by the browser IIFE below and by node unit tests (UMD export at EOF).
function applyFilters(cells, f) {
  var maxcost = f.maxcost !== undefined ? f.maxcost : Infinity;  // missing bound = no limit
  var minacc = f.minacc !== undefined ? f.minacc : 0;
  var out = cells.filter(function (c) {
    return (!f.type || c.type === f.type) &&
           c.cost_usd <= maxcost &&
           c.accuracy >= minacc;
  });
  var sort = f.sort || "worthiness";
  out.sort(function (a, b) {
    if (sort === "recipe") return a.recipe < b.recipe ? -1 : a.recipe > b.recipe ? 1 : 0;
    if (sort === "cost") return a.cost_usd - b.cost_usd;            // cheapest first
    if (sort === "accuracy") return b.accuracy - a.accuracy;        // best first
    return b.worthiness_vs_best - a.worthiness_vs_best;             // worthiness: best first
  });
  return out;
}

function aggregateRecipePoints(cells) {
  var byRecipe = {};
  cells.forEach(function (c) {
    (byRecipe[c.recipe] = byRecipe[c.recipe] || []).push(c);
  });
  return Object.keys(byRecipe).sort().map(function (name) {
    var rs = byRecipe[name];
    var acc = rs.reduce(function (s, c) { return s + c.accuracy; }, 0) / rs.length;
    var cost = rs.reduce(function (s, c) { return s + c.cost_usd; }, 0) / rs.length;
    return { recipe: name, arm: rs[0].arm, accuracy: acc, cost_usd: cost };  // assumes recipe↔arm is 1:1
  });
}

function paretoFrontierJS(points) {
  var pts = points.slice().sort(function (a, b) { return a.cost_usd - b.cost_usd; });
  var front = [];
  var bestA = -1;
  pts.forEach(function (v) {
    if (v.accuracy > bestA + 1e-9) {
      front.push({ cost_usd: v.cost_usd, accuracy: v.accuracy });
      bestA = v.accuracy;
    }
  });
  return front;
}

var CSV_COLS = ["type", "recipe", "arm", "accuracy", "cost_usd", "latency_s",
  "worthiness_vs_best", "worthiness_vs_self_moa", "complementarity", "recommended", "n"];

function csvCell(v) {
  if (v === null || v === undefined) return "";
  var s = String(v);
  if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

function toCSV(cells) {
  var head = CSV_COLS.join(",");
  var rows = cells.map(function (c) {
    return CSV_COLS.map(function (k) { return csvCell(c[k]); }).join(",");
  });
  return head + "\n" + rows.join("\n") + "\n";
}

(function () {
  if (typeof document === "undefined") return; // not a browser — skip IIFE (node UMD load)
  var ARM_COLOR = {
    best_single: "#6b7280", self_moa: "#2563eb",
    fusion: "#0d9488", source_pool: "#7c3aed"
  };

  function fail(msg) {
    ["hero", "heatmap"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) { el.textContent = msg; el.style.color = "#6b7280"; el.style.padding = "16px"; }
    });
  }

  // Recoverable "no rows under current filter" — distinct from fatal fail() (CDN/404).
  function showEmpty(msg) {
    disposeCharts();                            // also clears orphaned canvases
    ["hero", "heatmap"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) { el.textContent = msg; el.style.color = "#6b7280"; el.style.padding = "16px"; }
    });
    // clear explorer too, so a stale table can't look current vs an empty export.
    ["explorer-chart", "explorer-table"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = "";
    });
  }

  function disposeCharts() {
    charts.forEach(function (c) { if (c && c.dispose) c.dispose(); });
    charts = [];
  }

  function isDark() { return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches; }
  function axisColors() {
    return isDark()
      ? { axis: "#9ca3af", text: "#e5e7eb", split: "#374151" }
      : { axis: "#6b7280", text: "#111827", split: "#e5e7eb" };
  }

  if (typeof echarts === "undefined") {
    // CDN unavailable while JS is on: <noscript> won't fire, so just message the container.
    fail("Charts unavailable (ECharts failed to load).");
    return;
  }

  var ALL = [];                        // all cells from data.json
  var state = { filters: { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" } };
  var charts = [];

  fetch("data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      ALL = data.cells || [];
      state.filters = parseHash();
      buildControls();
      wireExport();
      update();
      if (window.matchMedia) {
        matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { update(); });
      }
      window.addEventListener("hashchange", function () {
        if (hashTimer) { clearTimeout(hashTimer); hashTimer = null; }  // cancel pending slider write
        applyingHash = true;                  // suppress writeHash while applying external hash
        state.filters = parseHash(); buildControls(); update();
        applyingHash = false;
      });
      window.addEventListener("resize", function () {
        charts.forEach(function (c) { if (c) c.resize(); });
      });
    })
    .catch(function (e) { fail("Could not load data.json: " + e.message); });

  function update() {
    var cells = applyFilters(ALL, state.filters);
    if (!cells.length) {
      showEmpty("Нет данных под текущий фильтр. Сбросьте фильтры.");
      return;
    }
    disposeCharts();                 // tear down prior instances before re-init on same nodes
    var pts = aggregateRecipePoints(cells);
    var pareto = paretoFrontierJS(pts);
    charts = [renderHero(pts, pareto), renderHeatmap(cells), renderExplorer(cells)];
  }

  var TASK_TYPES = ["code", "deep_research", "multihop_qa", "math", "factual"];
  var SORTS = ["worthiness", "accuracy", "cost", "recipe"];
  var applyingHash = false;
  var hashTimer = null;

  function parseHash() {
    var h = (location.hash || "").replace(/^#/, "");
    var p = {};
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) p[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1));
    });
    var f = { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" };
    if (TASK_TYPES.indexOf(p.type) >= 0) f.type = p.type;
    if (p.maxcost && !isNaN(parseFloat(p.maxcost))) f.maxcost = parseFloat(p.maxcost);
    if (p.minacc && !isNaN(parseFloat(p.minacc))) f.minacc = parseFloat(p.minacc);
    if (SORTS.indexOf(p.sort) >= 0) f.sort = p.sort;
    return f;
  }

  function writeHash() {
    if (applyingHash) return;                 // don't write back while applying a hash
    var f = state.filters, parts = [];
    if (f.type) parts.push("type=" + f.type);
    if (f.maxcost !== Infinity) parts.push("maxcost=" + f.maxcost);
    if (f.minacc > 0) parts.push("minacc=" + f.minacc);
    if (f.sort !== "worthiness") parts.push("sort=" + f.sort);
    var hash = parts.length ? "#" + parts.join("&") : "";
    if (location.hash !== hash) {
      history.replaceState(null, "", hash || (location.pathname + location.search));
    }
  }

  function writeHashDebounced() {
    if (hashTimer) clearTimeout(hashTimer);
    hashTimer = setTimeout(writeHash, 200);
  }

  function costBounds() {
    var costs = ALL.map(function (c) { return c.cost_usd; }).filter(function (x) { return x > 0; });
    return { min: Math.min.apply(null, costs), max: Math.max.apply(null, costs) };
  }

  function buildControls() {
    var box = document.getElementById("filters");
    if (!box) return;
    box.textContent = "";
    var cb = costBounds();

    var typeSel = document.createElement("select");
    [""].concat(TASK_TYPES).forEach(function (t) {
      var o = document.createElement("option"); o.value = t; o.textContent = t || "all types";
      if (t === state.filters.type) o.selected = true; typeSel.appendChild(o);
    });
    typeSel.onchange = function () { state.filters.type = typeSel.value; update(); writeHash(); };

    var maxc = document.createElement("input");
    maxc.type = "range"; maxc.min = cb.min; maxc.max = cb.max;
    maxc.step = (cb.max - cb.min) / 100 || 0.0001;
    maxc.value = state.filters.maxcost === Infinity ? cb.max : state.filters.maxcost;
    var maxcLbl = document.createElement("span");
    maxcLbl.textContent = "≤ $" + Number(maxc.value).toFixed(4);
    maxc.oninput = function () {
      state.filters.maxcost = parseFloat(maxc.value);
      maxcLbl.textContent = "≤ $" + parseFloat(maxc.value).toFixed(4);
      update(); writeHashDebounced();
    };

    var minacc = document.createElement("input");
    minacc.type = "range"; minacc.min = 0; minacc.max = 1; minacc.step = 0.01;
    minacc.value = state.filters.minacc;
    var minaccLbl = document.createElement("span");
    minaccLbl.textContent = "acc ≥ " + Math.round(state.filters.minacc * 100) + "%";
    minacc.oninput = function () {
      state.filters.minacc = parseFloat(minacc.value);
      minaccLbl.textContent = "acc ≥ " + Math.round(parseFloat(minacc.value) * 100) + "%";
      update(); writeHashDebounced();
    };

    var sortSel = document.createElement("select");
    SORTS.forEach(function (s) {
      var o = document.createElement("option"); o.value = s; o.textContent = "sort: " + s;
      if (s === state.filters.sort) o.selected = true; sortSel.appendChild(o);
    });
    sortSel.onchange = function () { state.filters.sort = sortSel.value; update(); writeHash(); };

    var reset = document.createElement("button");
    reset.textContent = "Reset";
    reset.onclick = function () {
      state.filters = { type: "", maxcost: Infinity, minacc: 0, sort: "worthiness" };
      buildControls(); update(); writeHash();
    };

    [labelWrap("type", typeSel), labelWrap("max cost", maxc, maxcLbl),
     labelWrap("min acc", minacc, minaccLbl), labelWrap("sort by", sortSel), reset]
      .forEach(function (el) { box.appendChild(el); });
  }

  function labelWrap(text) {
    var wrap = document.createElement("label");
    wrap.style.display = "inline-flex"; wrap.style.alignItems = "center";
    wrap.style.gap = "6px"; wrap.style.fontSize = "13px"; wrap.style.color = "#6b7280";
    if (text) { var t = document.createElement("span"); t.textContent = text; wrap.appendChild(t); }
    for (var i = 1; i < arguments.length; i++) wrap.appendChild(arguments[i]);
    return wrap;
  }

  function renderHero(recipePoints, pareto) {
    var pts = (recipePoints || []).filter(function (c) { return c.cost_usd > 0; });
    var el = document.getElementById("hero");
    el.textContent = "";                 // clear any prior showEmpty/fail message
    var hero = echarts.init(el);
    hero.setOption({
      grid: { left: 56, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "log", name: "cost per task ($)", nameLocation: "middle", nameGap: 30,
               axisLine: { lineStyle: { color: axisColors().axis } },
               axisLabel: { color: axisColors().text },
               splitLine: { lineStyle: { color: axisColors().split } },
               nameTextStyle: { color: axisColors().text } },
      yAxis: {
        type: "value", name: "accuracy", min: 0, max: 1,
        axisLabel: { formatter: function (v) { return Math.round(v * 100) + "%"; }, color: axisColors().text },
        axisLine: { lineStyle: { color: axisColors().axis } },
        splitLine: { lineStyle: { color: axisColors().split } },
        nameTextStyle: { color: axisColors().text }
      },
      tooltip: {
        formatter: function (p) {
          if (p.seriesType !== "scatter") return "";
          return p.data.name + ": $" + p.data.value[0].toFixed(4) +
                 " · " + Math.round(p.data.value[1] * 100) + "%";
        }
      },
      series: [
        {
          type: "scatter", symbolSize: 16,
          data: pts.map(function (c) {
            return { name: c.recipe, value: [c.cost_usd, c.accuracy],
                     itemStyle: { color: ARM_COLOR[c.arm] || "#6b7280" } };
          }),
          label: { show: true, position: "top",
                   formatter: function (p) { return p.data.name; }, fontSize: 11 }
        },
        {
          type: "line", symbol: "none", silent: true,
          lineStyle: { type: "dashed", color: "#9ca3af" },
          data: (pareto || []).filter(function (p) { return p.cost_usd > 0; })
                  .map(function (p) { return [p.cost_usd, p.accuracy]; })
        }
      ]
    });
    return hero;
  }

  function renderHeatmap(cells) {
    cells = cells || [];
    var types = [];
    var recipes = [];
    cells.forEach(function (c) {
      if (types.indexOf(c.type) < 0) types.push(c.type);
      if (recipes.indexOf(c.recipe) < 0) recipes.push(c.recipe);
    });
    var matrix = cells.map(function (c) {
      return [recipes.indexOf(c.recipe), types.indexOf(c.type), c.worthiness_vs_best];
    });
    var hmEl = document.getElementById("heatmap");
    hmEl.textContent = "";               // clear any prior showEmpty/fail message
    var hm = echarts.init(hmEl);
    hm.setOption({
      grid: { left: 120, right: 24, top: 24, bottom: 60 },
      tooltip: {
        position: "top",
        formatter: function (p) {
          return recipes[p.value[0]] + " / " + types[p.value[1]] +
                 ": " + (p.value[2] > 0 ? "+" : "") + Math.round(p.value[2] * 100) + "%";
        }
      },
      xAxis: { type: "category", data: recipes, axisLabel: { rotate: 30, color: axisColors().text } },
      yAxis: { type: "category", data: types, axisLabel: { color: axisColors().text } },
      visualMap: {
        min: -0.1, max: 0.1, calculable: true, orient: "horizontal",
        left: "center", bottom: 0,
        inRange: { color: ["#b91c1c", "#f1f5f9", "#15803d"] }
      },
      series: [{
        type: "heatmap", data: matrix,
        label: {
          show: true,
          formatter: function (p) {
            var v = p.value[2];
            return (v > 0 ? "+" : "") + Math.round(v * 100);
          }
        }
      }]
    });
    return hm;
  }

  function renderExplorer(cells) {
    // scatter
    var chartEl = document.getElementById("explorer-chart");
    chartEl.textContent = "";
    var ec = echarts.init(chartEl);
    var maxN = Math.max.apply(null, cells.map(function (c) { return c.n || 1; }).concat([1]));
    ec.setOption({
      grid: { left: 56, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "log", name: "cost per task ($)", nameLocation: "middle", nameGap: 30,
               axisLine: { lineStyle: { color: axisColors().axis } },
               axisLabel: { color: axisColors().text },
               splitLine: { lineStyle: { color: axisColors().split } },
               nameTextStyle: { color: axisColors().text } },
      yAxis: { type: "value", name: "accuracy", min: 0, max: 1,
               axisLabel: { formatter: function (v) { return Math.round(v * 100) + "%"; }, color: axisColors().text },
               axisLine: { lineStyle: { color: axisColors().axis } },
               splitLine: { lineStyle: { color: axisColors().split } },
               nameTextStyle: { color: axisColors().text } },
      tooltip: {
        // ECharts renders formatter strings as HTML; data is build-controlled, not user input.
        formatter: function (p) {
          var c = p.data.cell;
          return c.recipe + " / " + c.type + "<br>acc " + Math.round(c.accuracy * 100) +
                 "% · $" + c.cost_usd.toFixed(4) + " · worth " +
                 (c.worthiness_vs_best > 0 ? "+" : "") + Math.round(c.worthiness_vs_best * 100) + "%";
        }
      },
      series: [{
        type: "scatter",
        data: cells.filter(function (c) { return c.cost_usd > 0; }).map(function (c) {
          return { value: [c.cost_usd, c.accuracy], cell: c,
                   symbolSize: 8 + 18 * (c.n || 1) / maxN,
                   itemStyle: { color: ARM_COLOR[c.arm] || "#6b7280" } };
        })
      }]
    });

    // table (createElement / textContent — no innerHTML)
    var cols = ["type", "recipe", "arm", "accuracy", "cost_usd", "worthiness_vs_best", "complementarity", "n"];
    var SORT_COL = { accuracy: "accuracy", cost_usd: "cost", worthiness_vs_best: "worthiness", recipe: "recipe" };
    var host = document.getElementById("explorer-table");
    host.textContent = "";
    var tbl = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    cols.forEach(function (k) {
      var th = document.createElement("th"); th.textContent = k;
      if (SORT_COL[k]) {                       // only sortable columns get the affordance
        th.style.cursor = "pointer";
        th.onclick = function () {
          state.filters.sort = SORT_COL[k]; buildControls(); update(); writeHash();
        };
      }
      htr.appendChild(th);
    });
    thead.appendChild(htr); tbl.appendChild(thead);
    var tb = document.createElement("tbody");
    cells.forEach(function (c) {
      var tr = document.createElement("tr");
      if (c.recommended) tr.className = "rec";
      cols.forEach(function (k) {
        var td = document.createElement("td");
        var v = c[k];
        if (k === "accuracy") td.textContent = Math.round(v * 100) + "%";
        else if (k === "cost_usd") td.textContent = "$" + v.toFixed(4);
        else if (k === "worthiness_vs_best") td.textContent = (v > 0 ? "+" : "") + Math.round(v * 100) + "%";
        else if (k === "complementarity") td.textContent = v == null ? "—" : v.toFixed(2);
        else td.textContent = v;
        if (k === "accuracy" || k === "cost_usd" || k === "worthiness_vs_best" || k === "n") td.className = "num";
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb); host.appendChild(tbl);
    return ec;
  }

  function downloadBlob(text, filename, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }

  function wireExport() {
    var csvBtn = document.getElementById("dl-csv");
    var jsonBtn = document.getElementById("dl-json");
    if (csvBtn) csvBtn.onclick = function () {
      downloadBlob(toCSV(applyFilters(ALL, state.filters)), "fusionbench-cells.csv", "text/csv");
    };
    if (jsonBtn) jsonBtn.onclick = function () {
      downloadBlob(JSON.stringify(applyFilters(ALL, state.filters), null, 2), "fusionbench-cells.json", "application/json");
    };
  }
})();

// UMD export for node unit tests (browser ignores this).
if (typeof module !== "undefined" && module.exports) {
  module.exports = { applyFilters: applyFilters, aggregateRecipePoints: aggregateRecipePoints,
                     paretoFrontierJS: paretoFrontierJS, toCSV: toCSV };
}

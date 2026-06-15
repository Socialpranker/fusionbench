// site/app.js — renders hero-Pareto and heatmap from data.json via ECharts.
// Pure view layer: all numbers are precomputed in data.json by build_catalog.py.
(function () {
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

  if (typeof echarts === "undefined") {
    // CDN unavailable while JS is on: <noscript> won't fire, so just message the container.
    fail("Charts unavailable (ECharts failed to load).");
    return;
  }

  fetch("data.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(render)
    .catch(function (e) { fail("Could not load data.json: " + e.message); });

  function render(data) {
    var charts = [renderHero(data), renderHeatmap(data)];
    window.addEventListener("resize", function () {
      charts.forEach(function (c) { if (c) c.resize(); });
    });
  }

  function renderHero(data) {
    var pts = data.recipe_points || [];
    var dropped = pts.filter(function (c) { return !(c.cost_usd > 0); });
    if (dropped.length) {
      console.warn("hero: dropped " + dropped.length + " point(s) with cost_usd<=0 (log axis can't show them)");
    }
    pts = pts.filter(function (c) { return c.cost_usd > 0; });
    var hero = echarts.init(document.getElementById("hero"));
    hero.setOption({
      grid: { left: 56, right: 24, top: 24, bottom: 48 },
      xAxis: { type: "log", name: "cost per task ($)", nameLocation: "middle", nameGap: 30 },
      yAxis: {
        type: "value", name: "accuracy", min: 0, max: 1,
        axisLabel: { formatter: function (v) { return Math.round(v * 100) + "%"; } }
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
          data: (data.pareto || []).filter(function (p) { return p.cost_usd > 0; })
                  .map(function (p) { return [p.cost_usd, p.accuracy]; })
        }
      ]
    });
    return hero;
  }

  function renderHeatmap(data) {
    var cells = data.cells || [];
    var types = [];
    var recipes = [];
    cells.forEach(function (c) {
      if (types.indexOf(c.type) < 0) types.push(c.type);
      if (recipes.indexOf(c.recipe) < 0) recipes.push(c.recipe);
    });
    var matrix = cells.map(function (c) {
      return [recipes.indexOf(c.recipe), types.indexOf(c.type), c.worthiness_vs_best];
    });
    var hm = echarts.init(document.getElementById("heatmap"));
    hm.setOption({
      grid: { left: 120, right: 24, top: 24, bottom: 60 },
      tooltip: {
        position: "top",
        formatter: function (p) {
          return recipes[p.value[0]] + " / " + types[p.value[1]] +
                 ": " + (p.value[2] > 0 ? "+" : "") + Math.round(p.value[2] * 100) + "%";
        }
      },
      xAxis: { type: "category", data: recipes, axisLabel: { rotate: 30 } },
      yAxis: { type: "category", data: types },
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
})();

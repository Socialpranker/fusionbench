// site/leaderboard.js — renders the relative contributor leaderboard from leaderboard.json.
// No innerHTML (project hook blocks it) — only textContent / createElement.
(function () {
  var board = document.getElementById("board");
  var foot = document.getElementById("foot");
  if (!board) return;  // page template always ships #board; guard defensively

  fetch("leaderboard.json")
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      var rows = (data && data.contributors) || [];
      if (foot) foot.textContent = "Updated " + ((data && data.updated) || "");
      if (!rows.length) {
        board.textContent = "No verified contributions yet.";
        board.style.color = "#6b7280"; board.style.padding = "16px";
        return;
      }
      board.appendChild(buildTable(rows));
    })
    .catch(function (e) {
      board.textContent = "Could not load leaderboard.json: " + e.message;
      board.style.color = "#6b7280"; board.style.padding = "16px";
    });

  function buildTable(rows) {
    var max = maxPoints(rows);
    var cols = ["#", "user", "points", "verified", "cells"];
    var tbl = document.createElement("table");
    var thead = document.createElement("thead");
    var htr = document.createElement("tr");
    cols.forEach(function (k) {
      var th = document.createElement("th"); th.textContent = k; htr.appendChild(th);
    });
    thead.appendChild(htr); tbl.appendChild(thead);
    var tb = document.createElement("tbody");
    rows.forEach(function (c, i) {
      var tr = document.createElement("tr");
      tr.appendChild(td(String(i + 1), "num"));
      tr.appendChild(td(c.user));
      tr.appendChild(pointsCell(c.points, max));
      tr.appendChild(td(String(c.verified), "num"));
      tr.appendChild(td((c.cells || []).join(", ")));
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    return tbl;
  }

  function pointsCell(points, max) {
    // relative bar (points / leader) + the number — avoids absolute-number culting
    var cell = document.createElement("td");
    var n = document.createElement("span");
    n.textContent = points;
    n.style.marginRight = "8px"; n.style.fontVariantNumeric = "tabular-nums";
    var wrap = document.createElement("span");
    wrap.className = "bar-wrap";
    wrap.style.display = "inline-block"; wrap.style.verticalAlign = "middle";
    wrap.style.width = "100px";
    var fill = document.createElement("span");
    fill.className = "bar-fill";
    fill.style.width = (max > 0 ? Math.round(100 * points / max) : 0) + "%";
    wrap.appendChild(fill);
    cell.appendChild(n); cell.appendChild(wrap);
    return cell;
  }

  function maxPoints(rows) {
    return rows.reduce(function (m, c) { return c.points > m ? c.points : m; }, 0);
  }

  function td(text, cls) {
    var el = document.createElement("td");
    el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
})();

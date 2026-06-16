"""FusionBench — единый CSS-токен-слой (Swiss editorial + mono).

Источник истины для HTML-шаблонов в build_catalog.py и score_contributions.py.
Не редактировать вручную: содержимое синхронизировано с /tmp/fb_design/tokens.css.
"""

TOKENS_CSS: str = """\
/* ============================================================================
   FusionBench — единый CSS-токен-слой (Swiss editorial + mono)
   Один источник истины для site/index.html и site/leaderboard.html.
   Канон: вне @media живут ВСЕ токены. В @media (dark) переопределяются ТОЛЬКО
   реально меняющиеся (surface/text/border + chart-axis/text/split + heatmap-mid
   + rec-bg + verdict). Accent / worse / better / шрифты / радиус / размеры —
   единственный источник истины ВНЕ @media (direction: "teal НЕ менять",
   "worse/better в dark не меняются").
   ============================================================================ */
:root {
  /* === Палитра: фон и поверхности === */
  --fb-bg:              #f8fafc;   /* body */
  --fb-surface:         #ffffff;   /* table/card/badge-text-on */
  --fb-surface-2:       #161b26;   /* (зарезервирован под dark th) */
  --fb-surface-2-light: #f1f5f9;   /* th background / bar-track / bar-wrap (light) */

  /* === Палитра: текст === */
  --fb-text:            #111827;
  --fb-text-muted:      #6b7280;   /* .sub, th, .legend, .bar-val, fail/showEmpty, labelWrap */
  --fb-text-faint:      #9ca3af;   /* .foot */
  --fb-text-strong:     #374151;   /* .bar-label (light) */

  /* === Палитра: рамки === */
  --fb-border:          #e5e7eb;   /* table/card border, foot top-border */
  --fb-border-faint:    #f1f5f9;   /* th/td border-bottom */

  /* === Акцент (бренд, НЕ менять) === */
  --fb-accent:          #0d9488;   /* nav-ссылки, .bar-fill, .badge bg, rec left-border */
  --fb-accent-bg:       #f0fdfa;   /* tr.rec фон (light) */

  /* === Worthiness: хуже / лучше (НЕ меняются в dark) === */
  --fb-worse:           #b91c1c;
  --fb-better:          #15803d;

  /* === Verdict-блок (index.html) — успех/итог === */
  --fb-verdict-bg:      #ecfdf5;
  --fb-verdict-border:  #a7f3d0;
  --fb-verdict-text:    #065f46;

  /* === Типографика === */
  --fb-font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --fb-font-body: system-ui, -apple-system, "Segoe UI", sans-serif;

  /* === Размеры (усиленная иерархия) === */
  --fb-h1:        2.125rem;   /* ~34px — mono */
  --fb-h1-lh:     1.15;
  --fb-h2:        1.25rem;    /* ~20px — mono */
  --fb-h2-lh:     1.25;
  --fb-body:      0.906rem;   /* ~14.5px */
  --fb-body-lh:   1.55;
  --fb-small:     0.8125rem;  /* ~13px */
  --fb-label:     0.78125rem; /* ~12.5px — th/foot (mono-метки) */

  /* === Mono-метка колонок (th) === */
  --fb-label-tracking: 0.04em;
  --fb-label-weight:   500;
  --fb-label-transform: uppercase;

  /* === Tabular nums === */
  --fb-num-features: "tnum" 1;

  /* === Layout (flat — БЕЗ теней) === */
  --fb-radius:     12px;
  --fb-radius-pill: 999px;
  --fb-max-width:  880px;
  --fb-shadow:     none;
  --fb-gap:        24px;
  --fb-gap-sm:     12px;

  /* === ECharts data-viz палитра === */
  --fb-arm-best-single: #6b7280;
  --fb-arm-self-moa:    #2563eb;
  --fb-arm-fusion:      #0d9488;
  --fb-arm-source-pool: #7c3aed;

  --fb-chart-axis:      #6b7280;
  --fb-chart-text:      #111827;
  --fb-chart-split:     #e5e7eb;
  --fb-chart-pareto:    #9ca3af;
  --fb-chart-svg-axis:  #d1d5db;

  --fb-heatmap-low:     #b91c1c;
  --fb-heatmap-mid:     #f1f5f9;
  --fb-heatmap-high:    #15803d;
}

@media (prefers-color-scheme: dark) {
  :root {
    --fb-bg:              #0f1419;
    --fb-surface:         #1a1f2e;
    --fb-surface-2:       #161b26;
    --fb-surface-2-light: #374151;

    --fb-text:            #e5e7eb;
    --fb-text-muted:      #9ca3af;
    --fb-text-faint:      #9ca3af;
    --fb-text-strong:     #9ca3af;

    --fb-border:          #374151;
    --fb-border-faint:    #1f2937;

    --fb-accent:          #0d9488;
    --fb-accent-bg:       #0f2a26;

    --fb-worse:           #b91c1c;
    --fb-better:          #15803d;

    --fb-verdict-bg:      #0f2a1e;
    --fb-verdict-border:  #14532d;
    --fb-verdict-text:    #a7f3d0;

    --fb-chart-axis:      #9ca3af;
    --fb-chart-text:      #e5e7eb;
    --fb-chart-split:     #374151;
    --fb-chart-pareto:    #9ca3af;
    --fb-heatmap-mid:     #1a1f2e;
  }
}
"""

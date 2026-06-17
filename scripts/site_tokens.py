"""FusionBench — единый CSS-токен-слой (brutalist-terminal hybrid).

Источник истины для HTML-шаблонов в build_catalog.py и score_contributions.py.
Меняешь стиль — меняешь значения здесь, и оба сайта (каталог + лидерборд) едут разом.
ECharts-мост (site/app.js) читает chart/arm/heatmap-токены через getComputedStyle —
их имена менять нельзя, только значения.
"""

TOKENS_CSS: str = """\
/* ============================================================================
   FusionBench — единый CSS-токен-слой (brutalist-terminal hybrid)
   Монохром-база (тонированная бумага/чернила) + ОДИН кислотный оранжевый акцент.
   Хард-границы 2px, нулевой радиус, mono-заголовки/числа, grotesque body.
   Канон: вне @media живут ВСЕ токены; в @media (dark) переопределяются ТОЛЬКО
   реально меняющиеся (surface/text/border + accent + chart/heatmap + verdict).
   accent — ЕДИНСТВЕННЫЙ бренд-цвет; worse/better несут смысл (хуже/лучше).
   ============================================================================ */
:root {
  /* === Палитра: фон и поверхности (тонированы — не чистый #fff) === */
  --fb-bg:              #f4f3ee;   /* body — тёплая бумага */
  --fb-surface:         #fbfbf8;   /* table/card */
  --fb-surface-2:       #1f2225;   /* (зарезервирован под dark th) */
  --fb-surface-2-light: #e8e6dd;   /* th background / bar-track (light) */

  /* === Палитра: текст (чернила — не чистый #000) === */
  --fb-text:            #141210;
  --fb-text-muted:      #5c574e;   /* .sub, th, .legend, .bar-val, labels */
  --fb-text-faint:      #8a8276;   /* .foot */
  --fb-text-strong:     #2a2620;   /* .bar-label (light) */

  /* === Палитра: рамки (хард 2px) === */
  --fb-border:          #141210;   /* table/card border — чернильный, жёсткий */
  --fb-border-faint:    #d9d5c9;   /* th/td border-bottom (тихий разделитель) */

  /* === Акцент (бренд — ЕДИНСТВЕННЫЙ цветной, кислотный оранжевый) === */
  --fb-accent:          #ff5b04;   /* nav, bar-fill, badge bg, rec-метка, verdict-полоса */
  --fb-accent-bg:       #fff0e8;   /* tr.rec фон (light) */
  --fb-accent-ink:      #5c1f00;   /* текст на оранжевой плашке (badge) */

  /* === Worthiness: хуже / лучше (несут смысл, не бренд) === */
  --fb-worse:           #c0341d;
  --fb-better:          #1f7a3d;

  /* === Verdict-блок — чернильная плита, инверсная (тянет глаз) === */
  --fb-verdict-bg:      #141210;
  --fb-verdict-border:  #141210;
  --fb-verdict-text:    #f4f3ee;

  /* === Типографика (mono display + grotesque body) === */
  --fb-font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --fb-font-body: "Space Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;

  /* === Размеры (жёсткая иерархия) === */
  --fb-h1:        2.5rem;      /* ~40px — mono, крупнее прежнего */
  --fb-h1-lh:     1.05;
  --fb-h2:        1.3125rem;   /* ~21px — mono */
  --fb-h2-lh:     1.2;
  --fb-body:      0.9375rem;   /* ~15px */
  --fb-body-lh:   1.55;
  --fb-small:     0.8125rem;   /* ~13px */
  --fb-label:     0.75rem;     /* ~12px — th/foot (mono-метки) */

  /* === Mono-метка колонок (th) — капс, трекинг === */
  --fb-label-tracking: 0.08em;
  --fb-label-weight:   500;
  --fb-label-transform: uppercase;

  /* === Tabular nums === */
  --fb-num-features: "tnum" 1;

  /* === Layout (хард-границы, нулевой радиус, офсет-тень) === */
  --fb-radius:      0;
  --fb-radius-pill: 0;          /* бейджи прямоугольные — брутал */
  --fb-border-w:    2px;        /* толщина хард-границы */
  --fb-max-width:   880px;
  --fb-shadow:      4px 4px 0 var(--fb-border);  /* офсет — ТОЛЬКО акцентные блоки */
  --fb-gap:         24px;
  --fb-gap-sm:      12px;

  /* === ECharts data-viz палитра (fusion = акцент, остальное — приглушено) === */
  --fb-arm-best-single: #8a8276;   /* нейтраль */
  --fb-arm-self-moa:    #3b6ea5;   /* приглушённый синий */
  --fb-arm-fusion:      #ff5b04;   /* акцент — fusion в центре истории */
  --fb-arm-source-pool: #7a4fb5;   /* приглушённый фиолет (категориально, не бренд) */

  --fb-chart-axis:      #5c574e;
  --fb-chart-text:      #141210;
  --fb-chart-split:     #d9d5c9;
  --fb-chart-pareto:    #8a8276;
  --fb-chart-svg-axis:  #c4bfb2;

  --fb-heatmap-low:     #c0341d;
  --fb-heatmap-mid:     #e8e6dd;
  --fb-heatmap-high:    #1f7a3d;
}

@media (prefers-color-scheme: dark) {
  :root {
    --fb-bg:              #0c0d0c;
    --fb-surface:         #15171a;
    --fb-surface-2:       #1f2225;
    --fb-surface-2-light: #1f2225;

    --fb-text:            #e8e6df;
    --fb-text-muted:      #9b968b;
    --fb-text-faint:      #6f6a60;
    --fb-text-strong:     #c4bfb2;

    --fb-border:          #e8e6df;   /* хард-граница светлеет на тёмном */
    --fb-border-faint:    #2a2d2a;

    --fb-accent:          #ff6a1a;   /* чуть ярче для тёмного фона */
    --fb-accent-bg:       #2a1810;
    --fb-accent-ink:      #ffd9c2;

    --fb-worse:           #e0533a;
    --fb-better:          #3ea866;

    --fb-verdict-bg:      #1f2225;   /* на тёмном плита — приподнятая поверхность */
    --fb-verdict-border:  #e8e6df;
    --fb-verdict-text:    #e8e6df;

    --fb-chart-axis:      #9b968b;
    --fb-chart-text:      #e8e6df;
    --fb-chart-split:     #2a2d2a;
    --fb-chart-pareto:    #6f6a60;
    --fb-heatmap-mid:     #1f2225;
  }
}
"""

"""FusionBench showcase — Gradio leaderboard + filterable catalog table.

Runs locally (`python app.py`) and on a Hugging Face Space unchanged: data is read
from FUSIONBENCH_DATA_DIR (local json) with a FUSIONBENCH_DATA_URL Pages fallback.
Set FUSIONBENCH_DATA_DIR=examples for the bundled demo fixtures.
"""
from __future__ import annotations

import tempfile

import gradio as gr

from webui import data_loader as dl
from webui import export as ex
from webui import transform as tr

# Kept in sync with fusionbench.presets.TASK_TYPES by hand: the HF Space ships only
# app.py + webui/ (not the src-layout fusionbench package), so importing it would break there.
TYPE_CHOICES = ["", "code", "deep_research", "multihop_qa", "math", "factual"]
SORT_CHOICES = ["worthiness", "accuracy", "cost", "recipe"]

# --- Visual identity ---------------------------------------------------------
# Mirrors the site's design tokens (brutalist-terminal hybrid) so the Gradio showcase
# reads as a continuation of the static site. Hex values are copied verbatim from the
# site token layer (scripts/site_tokens.py :root / @media dark).
#   monochrome paper/ink + ONE acid-orange accent · radius 0 · hard 2px borders
#   mono = IBM Plex Mono · body = Space Grotesk
# Theme carries BOTH light and _dark variants, so it tracks prefers-color-scheme.
# Font stack: BARE STRINGS — verified against gradio 6.18.0 with a real launch().
# Gradio 6's launch() runs is_custom_theme by comparing our theme.to_dict() to every
# built-in's; to_dict() keeps the font stack under _font/_font_mono as-is. Font.__eq__
# is `self.name == other.name and ...`, so when our element is a Font/GoogleFont and a
# built-in's aligned element is a bare str, `other.name` raises AttributeError (notably
# vs the Glass theme). The built-in themes themselves use bare strings — matching that
# form makes every comparison str==str, which never crashes. Webfonts are loaded by the
# @import in CUSTOM_CSS (Space Grotesk + IBM Plex Mono), so no GoogleFont object needed.
# NOTE: this supersedes the earlier "bare str crashes" note — that was an older gradio
# 6.x; on 6.18.0 bare str is the ROBUST form. Always re-verify with a real launch().
_FONT_BODY = ("Space Grotesk", "system-ui", "-apple-system", "Segoe UI", "sans-serif")
_FONT_MONO = ("IBM Plex Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace")
THEME = (
    gr.themes.Base(
        # primary hue drives interactive accents; we override the concrete fills
        # below with our exact orange so the built-in hue ramp can't drift the brand.
        primary_hue=gr.themes.colors.orange,
        neutral_hue=gr.themes.colors.stone,
        font=_FONT_BODY,
        font_mono=_FONT_MONO,
        radius_size=gr.themes.sizes.radius_none,
    )
    .set(
        # --- surfaces & body (light / dark) — tinted paper/ink, not pure #fff/#000 ---
        body_background_fill="#f4f3ee",
        body_background_fill_dark="#0c0d0c",
        body_text_color="#141210",
        body_text_color_dark="#e8e6df",
        body_text_color_subdued="#5c574e",
        body_text_color_subdued_dark="#9b968b",
        background_fill_primary="#fbfbf8",
        background_fill_primary_dark="#15171a",
        background_fill_secondary="#e8e6dd",
        background_fill_secondary_dark="#1f2225",
        block_background_fill="#fbfbf8",
        block_background_fill_dark="#15171a",
        panel_background_fill="#fbfbf8",
        panel_background_fill_dark="#15171a",
        # --- borders: hard ink (2px applied via CSS below) ---
        border_color_primary="#141210",
        border_color_primary_dark="#e8e6df",
        block_border_color="#141210",
        block_border_color_dark="#e8e6df",
        input_border_color="#141210",
        input_border_color_dark="#e8e6df",
        # --- inputs ---
        input_background_fill="#fbfbf8",
        input_background_fill_dark="#0c0d0c",
        # --- tables (catalog / leaderboard Dataframes) ---
        table_even_background_fill="#fbfbf8",
        table_even_background_fill_dark="#15171a",
        table_odd_background_fill="#f4f3ee",
        table_odd_background_fill_dark="#1f2225",
        table_border_color="#141210",
        table_border_color_dark="#e8e6df",
        # --- accent: exact site acid-orange on primary controls ---
        color_accent="#ff5b04",
        color_accent_soft="#fff0e8",
        color_accent_soft_dark="#2a1810",
        link_text_color="#ff5b04",
        link_text_color_dark="#ff6a1a",
        button_primary_background_fill="#ff5b04",
        button_primary_background_fill_dark="#ff6a1a",
        button_primary_background_fill_hover="#e04e00",
        button_primary_background_fill_hover_dark="#ff5b04",
        button_primary_text_color="#5c1f00",
        button_primary_text_color_dark="#2a1810",
        button_primary_border_color="#141210",
        button_primary_border_color_dark="#e8e6df",
        # --- radius 0 everywhere (square, brutal) ---
        block_radius="0",
        container_radius="0",
        input_radius="0",
        button_large_radius="0",
        button_small_radius="0",
        # --- flat: kill default drops; hard offset shadow added via CSS on accents ---
        block_shadow="none",
        block_shadow_dark="none",
        input_shadow="none",
        shadow_drop="none",
        shadow_drop_lg="none",
    )
)

# CSS adds what the theme can't express: the Space Grotesk import, brutalist hard
# 2px borders on blocks (theme only sets the color, not the width), square mono
# headings, the inverse "masthead" slab on the page title, and tabular-nums on
# table numbers. No shadows/gradients/purple — the theme owns the palette.
CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;700&display=swap');
.gradio-container h1,
.gradio-container h2 {
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: -0.02em;
  font-weight: 700;
}
/* page title (first h1) → inverse ink slab, mirrors the site masthead */
.gradio-container h1:first-of-type {
  background: var(--body-text-color);
  color: var(--body-background-fill);
  border: 2px solid var(--body-text-color);
  padding: 18px 22px;
  font-size: 2rem;
  line-height: 1.1;
}
.gradio-container h2 { font-size: 1.3125rem; line-height: 1.2; }
/* hard brutalist borders: theme sets the color, we force the 2px width + square */
.gradio-container .block,
.gradio-container .form,
.gradio-container table,
.gradio-container .gr-box {
  border-width: 2px !important;
  border-radius: 0 !important;
}
/* tabs read as terminal tabs: square, hard underline on the active one */
.gradio-container button.selected {
  border-bottom: 2px solid var(--color-accent) !important;
}
/* tabular figures + mono so numeric columns line up under the headers */
.gradio-container table td,
.gradio-container table th {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
.gradio-container table td { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace; }
"""


def _catalog_view(cells, type, maxcost, minacc, sort):
    rows = tr.filter_catalog(cells, type=type, maxcost=maxcost, minacc=minacc, sort=sort)
    _, df_rows = tr.to_catalog_df(rows)
    return rows, df_rows


def build_demo():
    leaderboard = dl.load_leaderboard()
    catalog = dl.load_catalog()
    cells = catalog.get("cells", [])
    bounds = tr.slider_bounds(cells)
    lb_headers, lb_rows = tr.to_leaderboard_df(leaderboard)
    cat_headers, _ = tr.to_catalog_df(cells)
    init_rows, init_df = _catalog_view(cells, "", bounds["maxcost"], 0.0, "worthiness")

    # theme/css are passed to the constructor on purpose: in Gradio 6 these moved to
    # launch(), but on a HF Space *HF* calls launch() (we don't), so the only way the
    # theme survives is via Blocks' _deprecated_theme/_deprecated_css, which launch()
    # falls back to when its own args are None. The single UserWarning this emits is the
    # accepted cost of HF compatibility; local `python app.py` also passes them to
    # launch() below, which takes precedence. See __main__.
    with gr.Blocks(title="FusionBench — showcase", theme=THEME, css=CUSTOM_CSS) as demo:
        gr.Markdown("# FusionBench — when is multi-model fusion worth it?")
        with gr.Tabs():
            with gr.Tab("Leaderboard"):
                if lb_rows:
                    gr.Dataframe(value=lb_rows, headers=lb_headers, type="array",
                                 interactive=False, label="Contributors")
                else:
                    gr.Markdown("_Пока нет верифицированных вкладов._")
            with gr.Tab("Catalog"):
                if not cells:
                    gr.Markdown("_Каталог пуст — сгенерируйте data.json (scripts/build_catalog.py)._")
                else:
                    state = gr.State(cells)
                    filtered = gr.State(init_rows)
                    with gr.Row():
                        f_type = gr.Dropdown(TYPE_CHOICES, value="", label="task type")
                        f_sort = gr.Dropdown(SORT_CHOICES, value="worthiness", label="sort")
                    with gr.Row():
                        f_maxcost = gr.Slider(0.0, bounds["maxcost"], value=bounds["maxcost"],
                                              label="max cost $")
                        f_minacc = gr.Slider(0.0, 1.0, value=0.0, label="min accuracy")
                    table = gr.Dataframe(value=init_df, headers=cat_headers, type="array",
                                         interactive=False, label="Recipes")
                    with gr.Row():
                        dl_csv = gr.DownloadButton("Download CSV")
                        dl_json = gr.DownloadButton("Download JSON")

                    inputs = [state, f_type, f_maxcost, f_minacc, f_sort]
                    for ctrl in (f_type, f_sort, f_maxcost, f_minacc):
                        ctrl.change(_catalog_view, inputs=inputs, outputs=[filtered, table])

                    def make_csv(rows_):
                        visible = tr.project_catalog_rows(rows_)
                        fh = tempfile.NamedTemporaryFile(
                            delete=False, suffix=".csv", prefix="fusionbench_catalog_")
                        fh.write(ex.rows_to_csv_bytes(visible))
                        fh.close()
                        return fh.name

                    def make_json(rows_):
                        visible = tr.project_catalog_rows(rows_)
                        fh = tempfile.NamedTemporaryFile(
                            delete=False, suffix=".json", prefix="fusionbench_catalog_")
                        fh.write(ex.rows_to_json_bytes(visible))
                        fh.close()
                        return fh.name

                    dl_csv.click(make_csv, inputs=[filtered], outputs=[dl_csv])
                    dl_json.click(make_json, inputs=[filtered], outputs=[dl_json])
    return demo


if __name__ == "__main__":
    # Local run: pass theme/css to launch() (the Gradio 6 home for them). These take
    # precedence over the constructor values, so the UserWarning at build time is moot.
    build_demo().launch(theme=THEME, css=CUSTOM_CSS)

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
# Mirrors the site's design tokens (Swiss editorial + IBM Plex Mono + teal) so the
# Gradio showcase reads as a continuation of the static site. Hex values are copied
# verbatim from the site token layer (site CSS :root / @media dark). Flat, no shadows.
#   accent teal #0d9488 · radius 12px · mono = IBM Plex Mono · body = system sans
# Theme carries BOTH light and _dark variants, so it tracks prefers-color-scheme.
# Each stack element must be a gradio Font object (not a bare str): Gradio 6
# compares themes at launch() via Font.__eq__, which reads `.name` off every
# element — a bare str has no `.name` and crashes is_custom_theme.
_FONT_BODY = tuple(
    gr.themes.Font(name)
    for name in ("system-ui", "-apple-system", "Segoe UI", "sans-serif")
)
THEME = (
    gr.themes.Base(
        # primary hue drives interactive accents; we override the concrete fills
        # below with our exact teal so the built-in hue ramp can't drift the brand.
        primary_hue=gr.themes.colors.teal,
        neutral_hue=gr.themes.colors.gray,
        font=_FONT_BODY,
        font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
        radius_size=gr.themes.sizes.radius_md,
    )
    .set(
        # --- surfaces & body (light / dark) ---
        body_background_fill="#f8fafc",
        body_background_fill_dark="#0f1419",
        body_text_color="#111827",
        body_text_color_dark="#e5e7eb",
        body_text_color_subdued="#6b7280",
        body_text_color_subdued_dark="#9ca3af",
        background_fill_primary="#ffffff",
        background_fill_primary_dark="#1a1f2e",
        background_fill_secondary="#f1f5f9",
        background_fill_secondary_dark="#161b26",
        block_background_fill="#ffffff",
        block_background_fill_dark="#1a1f2e",
        panel_background_fill="#ffffff",
        panel_background_fill_dark="#1a1f2e",
        # --- borders ---
        border_color_primary="#e5e7eb",
        border_color_primary_dark="#374151",
        block_border_color="#e5e7eb",
        block_border_color_dark="#374151",
        input_border_color="#e5e7eb",
        input_border_color_dark="#374151",
        # --- inputs ---
        input_background_fill="#ffffff",
        input_background_fill_dark="#0f1419",
        # --- tables (catalog / leaderboard Dataframes) ---
        table_even_background_fill="#ffffff",
        table_even_background_fill_dark="#1a1f2e",
        table_odd_background_fill="#f8fafc",
        table_odd_background_fill_dark="#161b26",
        table_border_color="#e5e7eb",
        table_border_color_dark="#374151",
        # --- accent: exact site teal on primary controls ---
        color_accent="#0d9488",
        color_accent_soft="#f0fdfa",
        color_accent_soft_dark="#0f2a26",
        link_text_color="#0d9488",
        link_text_color_dark="#0d9488",
        button_primary_background_fill="#0d9488",
        button_primary_background_fill_dark="#0d9488",
        button_primary_background_fill_hover="#0f766e",
        button_primary_background_fill_hover_dark="#0f766e",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#ffffff",
        button_primary_border_color="#0d9488",
        button_primary_border_color_dark="#0d9488",
        # --- radius 12px everywhere ---
        block_radius="12px",
        container_radius="12px",
        input_radius="12px",
        button_large_radius="12px",
        button_small_radius="12px",
        # --- flat: kill the default drop shadows ---
        block_shadow="none",
        block_shadow_dark="none",
        input_shadow="none",
        shadow_drop="none",
        shadow_drop_lg="none",
    )
)

# CSS only adds what the theme can't express: mono + editorial weight on the page
# headings (gr.Markdown h1/h2) and tabular-nums on table numbers so columns align.
# No shadows / gradients / purple — the theme owns the rest.
CUSTOM_CSS = """
.gradio-container h1,
.gradio-container h2 {
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  letter-spacing: -0.01em;
}
.gradio-container h1 { font-size: 2.125rem; line-height: 1.15; }
.gradio-container h2 { font-size: 1.25rem; line-height: 1.25; }
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

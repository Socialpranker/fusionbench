"""FusionBench showcase — Gradio leaderboard + filterable catalog table.

Runs locally (`python app.py`) and on a Hugging Face Space unchanged: data is read
from FUSIONBENCH_DATA_DIR (local json) with a FUSIONBENCH_DATA_URL Pages fallback.
Set FUSIONBENCH_DATA_DIR=examples for the bundled demo fixtures.
"""
from __future__ import annotations

import gradio as gr

from webui import data_loader as dl
from webui import export as ex
from webui import transform as tr

TYPE_CHOICES = ["", "code", "deep_research", "multihop_qa", "math", "factual"]
SORT_CHOICES = ["worthiness", "accuracy", "cost", "recipe"]


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

    with gr.Blocks(title="FusionBench — showcase") as demo:
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

                    def on_filter(cells_, type_, maxcost_, minacc_, sort_):
                        rows_, df_ = _catalog_view(cells_, type_, maxcost_, minacc_, sort_)
                        return rows_, df_

                    inputs = [state, f_type, f_maxcost, f_minacc, f_sort]
                    for ctrl in (f_type, f_sort, f_maxcost, f_minacc):
                        ctrl.change(on_filter, inputs=inputs, outputs=[filtered, table])

                    def make_csv(rows_):
                        path = "fusionbench_catalog.csv"
                        with open(path, "wb") as fh:
                            fh.write(ex.rows_to_csv_bytes(rows_))
                        return path

                    def make_json(rows_):
                        path = "fusionbench_catalog.json"
                        with open(path, "wb") as fh:
                            fh.write(ex.rows_to_json_bytes(rows_))
                        return path

                    dl_csv.click(make_csv, inputs=[filtered], outputs=[dl_csv])
                    dl_json.click(make_json, inputs=[filtered], outputs=[dl_json])
    return demo


if __name__ == "__main__":
    build_demo().launch()

from fusionbench.search import candidate_panels, pick_judge, shortlist_for_type
from fusionbench.judge import family_of


def test_candidate_panels_count():
    pool = ["a/1", "b/2", "c/3", "d/4"]
    assert len(candidate_panels(pool, 2)) == 6   # C(4,2)


def test_pick_judge_cross_family():
    panel = ("google/gemini-3-flash", "moonshotai/kimi-k2.6", "deepseek/deepseek-v4-pro")
    j = pick_judge(panel)
    assert family_of(j) not in {family_of(p) for p in panel}


def test_pick_judge_registry_fallback_for_broad_panel():
    # panel spans anthropic/openai/google; a clean judge must come from another family
    panel = ("anthropic/claude-fable-5", "openai/gpt-5.5", "google/gemini-3-pro")
    j = pick_judge(panel)
    assert family_of(j) not in {family_of(p) for p in panel}


def test_shortlist_picks_complementary_panel():
    pool = ["x/m1", "x/m2", "x/m3"]
    corr = {
        "x/m1": [True, False, True, False],
        "x/m2": [False, True, False, True],   # disjoint with m1 -> complementary
        "x/m3": [True, False, True, False],   # identical to m1 -> redundant
    }
    recipes, ranked, n = shortlist_for_type(
        corr, pool, panel_size=2, k=1, synth="s/s", best="x/m1", n_self_moa=3
    )
    assert n == 3
    assert ranked[0][0] == ("x/m1", "x/m2")
    names = {r.name for r in recipes}
    assert {"best-single", "self-moa", "fusion-top1", "source-pool"} <= names

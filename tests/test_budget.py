from fusionbench.budget import n_for_budget, cost_usd
from fusionbench.config import Usage, ModelSpec


def test_n_for_budget():
    assert n_for_budget(1000, 200) == 5
    assert n_for_budget(0, 200) == 1     # nothing to spend -> at least 1 sample
    assert n_for_budget(1000, 0) == 1    # unknown per-call size -> safe default


def test_cost_usd():
    spec = ModelSpec("x", "X", "fam", price_in=2.0, price_out=8.0)
    u = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost_usd(u, spec) - 10.0) < 1e-9

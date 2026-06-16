import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import publish_datasets as pd  # noqa: E402


def test_collect_picks_existing_json(tmp_path):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    files = pd.collect_dataset_files(str(src))
    paths_in_repo = {repo for _, repo in files}
    assert paths_in_repo == {"leaderboard.json", "data.json"}
    for local, _ in files:
        assert Path(local).exists()


def test_collect_missing_source_raises(tmp_path):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    # data.json missing -> incomplete results dataset, must raise
    with pytest.raises(FileNotFoundError):
        pd.collect_dataset_files(str(src))

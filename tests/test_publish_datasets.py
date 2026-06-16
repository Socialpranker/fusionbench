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


def test_dry_run_does_not_touch_api(capsys):
    uploaded = []

    class FakeApi:
        def create_repo(self, *a, **k):
            uploaded.append("create")

        def upload_file(self, *a, **k):
            uploaded.append("upload")

    pd.publish(FakeApi(), "user/fb-results",
               [("/tmp/leaderboard.json", "leaderboard.json")], dry_run=True)
    assert uploaded == []  # network untouched
    assert "leaderboard.json" in capsys.readouterr().out  # plan printed


def test_real_publish_calls_create_and_upload():
    calls = []

    class FakeApi:
        def create_repo(self, repo_id, repo_type, exist_ok):
            calls.append(("create", repo_id, repo_type, exist_ok))

        def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type):
            calls.append(("upload", path_in_repo))

    pd.publish(FakeApi(), "user/fb-results",
               [("/tmp/data.json", "data.json")], dry_run=False)
    assert ("create", "user/fb-results", "dataset", True) in calls
    assert ("upload", "data.json") in calls

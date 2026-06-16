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


def test_main_no_token_not_dryrun_exits(tmp_path, monkeypatch):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src)])
    with pytest.raises(SystemExit) as e:
        pd.main()
    assert e.value.code != 0


def test_main_dry_run_succeeds_without_token(tmp_path, monkeypatch, capsys):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")
    (src / "data.json").write_text("{}")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src), "--dry-run"])
    pd.main()  # no SystemExit, no token needed
    assert "[dry-run]" in capsys.readouterr().out


def test_main_missing_source_exits(tmp_path, monkeypatch):
    src = tmp_path / "site"
    src.mkdir()
    (src / "leaderboard.json").write_text("{}")  # data.json missing
    monkeypatch.setattr(sys, "argv", [
        "publish_datasets.py", "--repo", "user/fb", "--source", str(src), "--dry-run"])
    with pytest.raises(SystemExit) as e:
        pd.main()
    assert e.value.code != 0


def test_publish_retries_then_succeeds(monkeypatch):
    # upload fails once, then succeeds — publish must retry and not raise.
    monkeypatch.setattr(pd.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    class FlakyApi:
        def create_repo(self, *a, **k):
            pass

        def upload_file(self, *a, **k):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise RuntimeError("flaky TLS")

    pd.publish(FlakyApi(), "user/fb", [("/tmp/data.json", "data.json")],
               dry_run=False, attempts=3)
    assert attempts["n"] == 2  # one failure + one success


def test_publish_reraises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(pd.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    class DeadApi:
        def create_repo(self, *a, **k):
            pass

        def upload_file(self, *a, **k):
            attempts["n"] += 1
            raise RuntimeError("net down")

    with pytest.raises(RuntimeError, match="net down"):
        pd.publish(DeadApi(), "user/fb", [("/tmp/data.json", "data.json")],
                   dry_run=False, attempts=3)
    assert attempts["n"] == 3  # all attempts exhausted

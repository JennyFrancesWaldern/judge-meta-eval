"""Tests for the contamination probe. Never makes a real API call or a real
network fetch -- fetch_qa_items is monkeypatched throughout.
"""
import json
import sys

import pytest

from src import cache, contamination_probe as probe


def fake_qa_pool(n=300):
    return {
        f"qa_{i:04d}": {"item_id": f"qa_{i:04d}", "passage": f"Passage {i}.", "question": f"Question {i}?"}
        for i in range(n)
    }


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    yield


@pytest.fixture
def fake_source_passages(tmp_path, monkeypatch):
    labeling_pool = [{"item_id": f"qa_{i:04d}", "passage": f"Passage {i}.", "question": f"Q{i}?"} for i in range(200)]
    path = tmp_path / "source_passages.json"
    path.write_text(json.dumps(labeling_pool), encoding="utf-8")
    monkeypatch.setattr(probe, "SOURCE_PASSAGES_PATH", path)
    return labeling_pool


def test_probe_items_disjoint_from_labeling_pool(fake_source_passages, monkeypatch):
    monkeypatch.setattr(probe, "fetch_qa_items", lambda: fake_qa_pool(300))
    labeling_ids = {item["item_id"] for item in fake_source_passages}

    probe_items = probe.select_probe_items()

    assert len(probe_items) == probe.PROBE_SIZE
    probe_ids = {item["item_id"] for item in probe_items}
    assert probe_ids.isdisjoint(labeling_ids)


def test_probe_items_deterministic_given_seed(fake_source_passages, monkeypatch):
    monkeypatch.setattr(probe, "fetch_qa_items", lambda: fake_qa_pool(300))
    first = probe.select_probe_items()
    second = probe.select_probe_items()
    assert [i["item_id"] for i in first] == [i["item_id"] for i in second]


def test_missing_source_passages_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "SOURCE_PASSAGES_PATH", tmp_path / "does_not_exist.json")
    with pytest.raises(FileNotFoundError):
        probe.select_probe_items()


def test_main_loads_dotenv_before_checking_keys(monkeypatch, fake_source_passages):
    """Regression test: contamination_probe.py has its own entry point and
    must call load_dotenv() itself -- it cannot rely on generate_responses.py's
    main() to have done it, since that main() never runs when this script is
    invoked directly. This bug shipped once already."""
    monkeypatch.setattr(probe, "fetch_qa_items", lambda: fake_qa_pool(300))
    calls = []
    monkeypatch.setattr(probe, "load_dotenv", lambda *a, **k: calls.append("called"))
    monkeypatch.setattr(sys, "argv", ["contamination_probe", "--dry-run"])
    probe.main()
    assert calls == ["called"]


# --- Scoring ---

def write_probe_output(tmp_path, monkeypatch, judgments):
    path = tmp_path / "contamination_probe.json"
    items = [
        {
            "item_id": f"qa_{i:04d}",
            "question": f"Q{i}?",
            "passage": f"Passage {i}.",
            "withheld_answer": f"Answer {i}",
            "human_judged_correct": judgment,
        }
        for i, judgment in enumerate(judgments)
    ]
    path.write_text(json.dumps(items), encoding="utf-8")
    monkeypatch.setattr(probe, "PROBE_OUTPUT_PATH", path)
    return path


def test_score_computes_rate_below_threshold(tmp_path, monkeypatch, capsys):
    write_probe_output(tmp_path, monkeypatch, [True, False, False, False, False])  # 1/5 = 20%
    monkeypatch.setattr(sys, "argv", ["contamination_probe", "--score"])
    exit_code = probe.main()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "20.0%" in out
    assert "Below" in out


def test_score_flags_high_contamination(tmp_path, monkeypatch, capsys):
    write_probe_output(tmp_path, monkeypatch, [True, True, True, False, False])  # 3/5 = 60%
    monkeypatch.setattr(sys, "argv", ["contamination_probe", "--score"])
    exit_code = probe.main()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "60.0%" in out
    assert "should change" in out


def test_score_refuses_when_items_unscored(tmp_path, monkeypatch, capsys):
    write_probe_output(tmp_path, monkeypatch, [True, False, None, False, False])
    monkeypatch.setattr(sys, "argv", ["contamination_probe", "--score"])
    exit_code = probe.main()
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "still have human_judged_correct: null" in err


def test_score_missing_file_fails_loudly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "PROBE_OUTPUT_PATH", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(sys, "argv", ["contamination_probe", "--score"])
    exit_code = probe.main()
    assert exit_code == 1

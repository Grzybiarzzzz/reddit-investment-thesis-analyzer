import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('history_report', Path(__file__).resolve().parents[1]/'scripts/evaluate_history.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_rank_correlation_handles_ties_and_constant_scores():
    assert report.correlation([1,1,3,4],[2,2,6,8]) == pytest.approx(1)
    assert report.correlation([1,2,3],[3,2,1]) == pytest.approx(-1)
    assert report.correlation([1,1,1],[2,3,4]) is None


def test_summary_excludes_missing_pairs_but_keeps_coverage_visible():
    rows = [dict(status='ok',return_pct=10,excess_spy_pp=5,quality_score=70),
            dict(status='ok',return_pct=-20,excess_spy_pp=-25,quality_score=80),
            dict(status='ok',return_pct=900,excess_spy_pp=None,quality_score=90)]
    result = report.summarize(rows)
    assert result['stocks'] == 3
    assert result['paired_stocks'] == 2
    assert result['mean_return_pct'] == -5
    assert result['median_excess_spy_pp'] == -10
    assert result['beat_spy'] == 1

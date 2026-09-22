from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from memory_ledger.benchmark import DEFAULT_FIXTURE_DIR, run_benchmark
from memory_ledger.cli import app


def test_benchmark_is_complete_and_semantically_deterministic() -> None:
    first = run_benchmark()
    second = run_benchmark()

    assert first == second
    assert first.passed is True
    assert first.memory_count == 32
    assert first.expected_memory_count == 32
    assert first.pass_count == 20
    assert first.query_count == 20


def test_benchmark_fails_for_missing_and_forbidden_results(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    shutil.copytree(DEFAULT_FIXTURE_DIR, fixture_dir)
    query_path = fixture_dir / "queries.json"
    fixture = json.loads(query_path.read_text(encoding="utf-8"))
    fixture["queries"][0]["include"].append("city_bangalore_pending")
    fixture["queries"][0]["exclude"].append("city_pune_2")
    query_path.write_text(json.dumps(fixture), encoding="utf-8")

    result = run_benchmark(fixture_dir)
    first_query = result.query_results[0]

    assert result.passed is False
    assert first_query.passed is False
    assert first_query.missing == ("city_bangalore_pending",)
    assert first_query.forbidden == ("city_pune_2",)


def test_cli_reports_each_query_and_overall_result() -> None:
    result = CliRunner().invoke(app, ["benchmark"])

    assert result.exit_code == 0
    assert "PASS q01-current-city" in result.stdout
    assert "Overall: 20/20 queries passed; 32/32 memories loaded" in result.stdout

from __future__ import annotations

from pathlib import Path

from scripts import datactl, update_tushare_current


def test_data_dir_override_defaults_are_portable_and_coherent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(datactl, "REPO_ROOT", tmp_path)
    for name in (
        "LEAN_DATA_DIR",
        "LEAN_HOST_DATA_DIR",
        "LEAN_MARKET_DATA_DIR",
        "LEAN_PARQUET_DIR",
        "LEAN_HOST_PARQUET_DIR",
        "LEAN_DATA_SYNC_SPOOL_DIR",
    ):
        monkeypatch.delenv(name, raising=False)

    root = datactl._apply_data_dir_override("local-data")

    assert root == (tmp_path / "local-data").resolve()
    assert Path(datactl.os.environ["LEAN_DATA_DIR"]) == root
    assert Path(datactl.os.environ["LEAN_MARKET_DATA_DIR"]) == root
    assert Path(datactl.os.environ["LEAN_PARQUET_DIR"]) == root / "output" / "parquet"
    assert Path(datactl.os.environ["LEAN_DATA_SYNC_SPOOL_DIR"]) == root / ".sync-spool"


def test_update_tushare_current_has_no_drive_requirement(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(update_tushare_current, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("LEAN_DATA_DIR", raising=False)

    assert update_tushare_current._apply_data_dir_override(None) is None
    assert update_tushare_current._resolve_data_dir("data") == (tmp_path / "data").resolve()


def test_datactl_update_defaults_to_auto_and_all_managed_datasets():
    args = datactl._build_parser().parse_args(["update"])

    assert args.command == "update"
    assert args.mode == "auto"
    assert args.datasets is None


def test_datactl_validate_keeps_network_checks_opt_in():
    args = datactl._build_parser().parse_args(["validate"])

    assert args.deep is False
    assert args.live_provider is False
    assert args.fail_on_warning is False


def test_validation_step_fails_closed_without_exposing_exception_message():
    def fail():
        raise RuntimeError("postgresql://user:secret@example.invalid/db")

    result = datactl._step("archive", fail)

    assert result == {
        "step": "archive",
        "severity": "critical",
        "details": {"errorType": "RuntimeError"},
    }


def test_special_dataset_recovery_preserves_dividend_failure_across_extended_cycles(monkeypatch):
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeSync:
        counter = 0

        @staticmethod
        def create_sync_run(*, requested, mode, request_scope):
            calls.append((list(requested), dict(request_scope)))
            FakeSync.counter += 1
            return {"id": f"run-{FakeSync.counter}"}

        @staticmethod
        def run_sync(run_id):
            requested, scope = calls[-1]
            if requested == ["extended_daily"]:
                return {
                    "status": "success",
                    "datasets": {
                        "extended_daily": {
                            "deferredSymbolTasks": 0,
                            "partitionFailures": 0,
                        }
                    },
                }
            if requested == ["dividend"]:
                assert scope == {"retryFailedOnlyDatasets": ["dividend"]}
                return {
                    "status": "success",
                    "datasets": {"dividend": {"failed": 0}},
                }
            raise AssertionError(f"unexpected request: {requested}")

    initial = {
        "status": "partial",
        "datasets": {
            "extended_daily": {"deferredSymbolTasks": 2, "partitionFailures": 0},
            "dividend": {"failed": 1},
        },
    }

    result = update_tushare_current.complete_special_datasets(
        FakeSync,
        initial_result=initial,
        symbol_batch_size=100,
        max_extended_cycles=3,
        max_dividend_retries=2,
    )

    assert result["status"] == "success"
    assert result["extendedCycles"] == 2
    assert result["dividendFailures"] == 0
    assert [item[0] for item in calls] == [["extended_daily"], ["dividend"]]

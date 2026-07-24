from __future__ import annotations

from datetime import date, timedelta
from typing import Any


CHECK_VERSION = "experiment-leakage-v1"


def _day(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _overlap(left_start: Any, left_end: Any, right_start: Any, right_end: Any) -> int:
    start = max(_day(left_start), _day(right_start))
    end = min(_day(left_end), _day(right_end))
    return max(0, (end - start).days + 1)


def _count(lineage: dict[str, Any], key: str) -> int:
    value = lineage.get(key)
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 1 if value else 0


def evaluate_experiment_leakage(
    experiment_spec: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a frozen train/validation/OOS specification and fail closed.

    The caller supplies observed lineage facts. Boolean/count fields are never
    inferred away: a non-zero observation becomes a machine-readable violation.
    """

    train = dict(experiment_spec.get("train") or {})
    validation = dict(experiment_spec.get("validation") or {})
    oos = dict(experiment_spec.get("oos") or {})
    train_validation_overlap = _overlap(
        train.get("start"), train.get("end"), validation.get("start"), validation.get("end")
    )
    validation_oos_overlap = _overlap(
        validation.get("start"), validation.get("end"), oos.get("start"), oos.get("end")
    )
    train_oos_overlap = _overlap(
        train.get("start"), train.get("end"), oos.get("start"), oos.get("end")
    )

    label_horizon = max(0, int(experiment_spec.get("labelHorizonDays") or 0))
    label_boundary_violations = 0
    if label_horizon:
        if _day(train["end"]) + timedelta(days=label_horizon) >= _day(validation["start"]):
            label_boundary_violations += 1
        if _day(validation["end"]) + timedelta(days=label_horizon) >= _day(oos["start"]):
            label_boundary_violations += 1

    future_universe = _count(lineage, "futureUniverseReferences")
    future_fundamentals = _count(lineage, "futureFundamentalReferences")
    future_corporate_actions = _count(lineage, "futureCorporateActionReferences")
    full_sample_fits = _count(lineage, "fullSampleFitViolations")
    oos_selection = _count(lineage, "oosMetricSelectionReferences")
    revisions = _count(lineage, "dataRevisionAfterFreeze")
    duplicates = _count(lineage, "duplicateSymbolDateCrossings")
    benchmark_misalignment = _count(lineage, "benchmarkMisalignment")

    violations: list[dict[str, Any]] = []

    def add(code: str, count: int, message: str) -> None:
        if count:
            violations.append({"code": code, "count": count, "message": message})

    add("TRAIN_VALIDATION_OVERLAP", train_validation_overlap, "Train and validation dates overlap.")
    add("VALIDATION_OOS_OVERLAP", validation_oos_overlap, "Validation and OOS dates overlap.")
    add("TRAIN_OOS_OVERLAP", train_oos_overlap, "Train and OOS dates overlap.")
    add("LABEL_HORIZON_CROSSES_BOUNDARY", label_boundary_violations, "A label horizon crosses a phase boundary.")
    add("FUTURE_UNIVERSE_MEMBERSHIP", future_universe, "Universe membership was not known as of the observation date.")
    add("FUTURE_FUNDAMENTAL_PUBLICATION", future_fundamentals, "A fundamental publication occurs after the observation date.")
    add("FUTURE_CORPORATE_ACTION", future_corporate_actions, "A corporate action was referenced before its knowledge date.")
    add("FULL_SAMPLE_NORMALIZATION", full_sample_fits, "Feature fitting used full-sample statistics.")
    add("OOS_METRIC_USED_FOR_SELECTION", oos_selection, "OOS metrics participated in parameter selection.")
    add("DATA_REVISION_AFTER_FREEZE", revisions, "An input revision occurred after the run freeze.")
    add("DUPLICATE_SYMBOL_DATE_CROSSING", duplicates, "Duplicate symbol/date observations cross phase boundaries.")
    add("BENCHMARK_MISALIGNMENT", benchmark_misalignment, "Benchmark observations are not aligned with the experiment calendar.")

    return {
        "decision": "DENY" if violations else "ALLOW",
        "checkVersion": CHECK_VERSION,
        "violations": violations,
        "trainValidationOverlap": train_validation_overlap,
        "validationOosOverlap": validation_oos_overlap,
        "trainOosOverlap": train_oos_overlap,
        "futureUniverseReferences": future_universe,
        "futureFundamentalReferences": future_fundamentals,
        "futureCorporateActionReferences": future_corporate_actions,
        "labelBoundaryViolations": label_boundary_violations,
        "fullSampleFitViolations": full_sample_fits,
        "oosMetricSelectionReferences": oos_selection,
        "dataRevisionAfterFreeze": revisions,
        "duplicateSymbolDateCrossings": duplicates,
        "benchmarkMisalignment": benchmark_misalignment,
    }

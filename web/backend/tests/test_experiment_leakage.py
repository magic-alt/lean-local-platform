from app.services.experiment_leakage import evaluate_experiment_leakage


def test_leakage_evaluation_allows_disjoint_frozen_phases():
    result = evaluate_experiment_leakage(
        {
            "train": {"start": "2023-01-01", "end": "2023-12-20"},
            "validation": {"start": "2024-01-01", "end": "2024-06-20"},
            "oos": {"start": "2024-07-01", "end": "2024-12-31"},
            "labelHorizonDays": 5,
        },
        {},
    )

    assert result["decision"] == "ALLOW"
    assert result["violations"] == []


def test_leakage_evaluation_denies_every_observed_lookahead_class():
    result = evaluate_experiment_leakage(
        {
            "train": {"start": "2023-01-01", "end": "2024-01-03"},
            "validation": {"start": "2024-01-01", "end": "2024-07-03"},
            "oos": {"start": "2024-07-01", "end": "2024-12-31"},
            "labelHorizonDays": 3,
        },
        {
            "futureUniverseReferences": 1,
            "futureFundamentalReferences": 2,
            "futureCorporateActionReferences": 1,
            "fullSampleFitViolations": 1,
            "oosMetricSelectionReferences": 1,
            "dataRevisionAfterFreeze": 1,
            "duplicateSymbolDateCrossings": 1,
            "benchmarkMisalignment": 1,
        },
    )

    assert result["decision"] == "DENY"
    codes = {item["code"] for item in result["violations"]}
    assert {
        "TRAIN_VALIDATION_OVERLAP",
        "VALIDATION_OOS_OVERLAP",
        "LABEL_HORIZON_CROSSES_BOUNDARY",
        "FUTURE_UNIVERSE_MEMBERSHIP",
        "FUTURE_FUNDAMENTAL_PUBLICATION",
        "FUTURE_CORPORATE_ACTION",
        "FULL_SAMPLE_NORMALIZATION",
        "OOS_METRIC_USED_FOR_SELECTION",
        "DATA_REVISION_AFTER_FREEZE",
        "DUPLICATE_SYMBOL_DATE_CROSSING",
        "BENCHMARK_MISALIGNMENT",
    } <= codes

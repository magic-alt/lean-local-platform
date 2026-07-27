from __future__ import annotations


def test_gap_buy_templates_publish_distinct_execution_contracts():
    from app.services.strategies import get_template, render_python_template

    source = get_template("gap_buy_source_replica")
    executable = get_template("gap_buy_ashare_next_open")

    assert source["strategyMode"] == "SOURCE_REPLICA"
    assert source["researchOnly"] is True
    assert source["tradable"] is False
    assert source["admissionEligible"] is False
    assert source["requiredResolution"] == "daily"

    assert executable["strategyMode"] == "A_SHARE_EXECUTABLE"
    assert executable["researchOnly"] is False
    assert executable["tradable"] is True
    assert executable["admissionEligible"] is True
    assert executable["requiredResolution"] == "minute"
    assert executable["defaultUniverse"] == "A_SHARE_L3P_50"
    assert set(executable["requiredAdmissionGates"]) == {
        "ashare_intraday_data_coverage",
        "ashare_no_same_bar_signal_fill",
        "ashare_t_plus_one",
        "ashare_partial_fill_volume_cap",
    }

    source_code = render_python_template("GapBuySourceReplicaAlgorithm", source["key"])
    executable_code = render_python_template("GapBuyAshareNextOpenAlgorithm", executable["key"])
    compile(source_code, "gap_buy_source_replica.py", "exec")
    compile(executable_code, "gap_buy_ashare_next_open.py", "exec")

    assert "GAP_SOURCE_REPLICA research_only=true" in source_code
    assert "fill_assumption=official_open" in source_code
    assert "self.gap_states" in source_code
    assert "State mutation is deliberately last" in source_code
    assert "self.gap_pending_selection = self._gap_select(data)" in executable_code
    assert "self.time.minute == 32" in executable_code
    assert "self.ashare_execution.limit_buy" in executable_code
    assert "is_one_word_limit_down" in executable_code


def test_ashare_helper_exposes_guarded_limit_buy_contract():
    from app.services.ashare_execution import ASHARE_EXECUTION_HELPER_SOURCE

    assert "def trade_status(self, symbol):" in ASHARE_EXECUTION_HELPER_SOURCE
    assert "def limit_buy(self, symbol, quantity, limit_price, tag=\"\"):" in ASHARE_EXECUTION_HELPER_SOURCE
    assert "self._round_to_lot(abs(int(quantity)))" in ASHARE_EXECUTION_HELPER_SOURCE
    assert "self.algorithm.limit_order(" in ASHARE_EXECUTION_HELPER_SOURCE

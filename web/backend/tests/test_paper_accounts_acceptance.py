from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    spec = importlib.util.spec_from_file_location(
        "paper_accounts_acceptance_contract",
        ROOT / "scripts" / "run_paper_accounts_acceptance.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides):
    values = {"days": 21, "accounts": 2, "initial_cash": "1000000,3000000"}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_paper_accounts_acceptance_requires_21_days_and_distinct_cash():
    module = _module()

    assert module._acceptance_contract(_args()) == {
        "requiredTradingDays": 21,
        "requiredAccounts": 2,
        "initialCash": ["1000000", "3000000"],
    }
    with pytest.raises(ValueError, match="at_least_21"):
        module._acceptance_contract(_args(days=20))
    with pytest.raises(ValueError, match="distinct_initial_cash"):
        module._acceptance_contract(_args(initial_cash="1000000,1000000"))

from argparse import Namespace

from scripts import run_paper_accounts_acceptance as acceptance


def test_existing_acceptance_contract_normalizes_mysql_decimal_cash():
    contract = acceptance._acceptance_contract(
        Namespace(days=21, accounts=2, initial_cash="unused"),
        [
            {"initial_cash": "1000000.00000000"},
            {"initial_cash": "3000000.00000000"},
        ],
    )

    assert contract == {
        "requiredTradingDays": 21,
        "requiredAccounts": 2,
        "initialCash": ["1000000", "3000000"],
    }

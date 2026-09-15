from __future__ import annotations

import pytest

from app.domain.instruments import InstrumentContractError, legacy_ashare_instrument
from app.services.instrument_kernel import require_execution_certified


def test_execution_certification_rejects_delisted_instrument_at_as_of() -> None:
    instrument = legacy_ashare_instrument(
        "600000.SH",
        listed_from="1999-11-10",
        listed_to="2026-09-14",
    )

    with pytest.raises(InstrumentContractError, match="delisted"):
        require_execution_certified(instrument, as_of="2026-09-15")


def test_execution_certification_accepts_instrument_inside_lifecycle() -> None:
    instrument = legacy_ashare_instrument(
        "600000.SH",
        listed_from="1999-11-10",
        listed_to="2026-09-30",
    )

    result = require_execution_certified(instrument, as_of="2026-09-15")

    assert result["instrument"]["instrument_id"] == "CN.XSHG.EQUITY.600000"
    assert result["marketRulePack"]["rule_pack_id"] == "cn_xshg_common_stock_v1"
    assert result["lean"]["securityType"] == "Equity"

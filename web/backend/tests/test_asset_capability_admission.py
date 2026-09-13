from __future__ import annotations

import pytest

from app.services import asset_capabilities


def test_only_current_ashare_daily_equity_scope_is_execution_enabled():
    assert asset_capabilities._available_scope_state(
        asset_class="equity",
        market="china",
        venue="china",
        resolution="daily",
        data_type="trade",
    ) == ("executable", None)


@pytest.mark.parametrize(
    ("asset_class", "resolution"),
    [
        ("equity", "minute"),
        ("equity", "tick"),
        ("index", "daily"),
        ("etf", "daily"),
        ("future", "daily"),
        ("option", "daily"),
        ("convertible_bond", "daily"),
    ],
)
def test_data_ready_scope_does_not_become_executable_from_presence_alone(
    asset_class: str,
    resolution: str,
):
    assert asset_capabilities._available_scope_state(
        asset_class=asset_class,
        market="china",
        venue="china",
        resolution=resolution,
        data_type="trade",
    ) == ("data_ready", "execution_scope_not_enabled")


def test_require_executable_scope_rejects_minute_data_ready_scope(monkeypatch):
    monkeypatch.setattr(
        asset_capabilities,
        "refresh_capabilities",
        lambda: [
            {
                "asset_class": "equity",
                "market": "china",
                "venue": "china",
                "resolution": "minute",
                "data_type": "trade",
                "state": "data_ready",
                "metadata_count": 1,
                "canonical_row_count": 10,
                "executable_reason": "execution_scope_not_enabled",
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="asset_capability_not_executable:equity:minute:data_ready:execution_scope_not_enabled",
    ):
        asset_capabilities.require_executable_scope(
            {
                "assetClass": "equity",
                "market": "china",
                "venue": "china",
                "resolution": "minute",
                "dataType": "trade",
            }
        )


def test_require_executable_scope_keeps_current_daily_equity_path(monkeypatch):
    expected = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "state": "executable",
        "metadata_count": 1,
        "canonical_row_count": 10,
        "executable_reason": None,
    }
    monkeypatch.setattr(asset_capabilities, "refresh_capabilities", lambda: [expected])

    result = asset_capabilities.require_executable_scope(
        {
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
        }
    )

    assert result == expected

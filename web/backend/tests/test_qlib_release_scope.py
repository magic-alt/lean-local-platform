from __future__ import annotations

import pytest


DATA_RELEASE_A = "ds_" + "a" * 64
DATA_RELEASE_B = "ds_" + "b" * 64


def _insert_release(
    db_module,
    *,
    release_id: str = DATA_RELEASE_A,
    status: str = "active",
) -> None:
    identity_marker = "1" if release_id == DATA_RELEASE_A else "3"
    manifest_marker = "2" if release_id == DATA_RELEASE_A else "4"
    with db_module.db() as connection:
        connection.execute(
            """insert into data_releases
               (id,schema_version,profile,asset_class,market,universe,benchmark,coverage_start,coverage_end,
                as_of_time,identity_sha256,manifest_sha256,manifest_path,status,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                release_id,
                "2.0",
                "research",
                "equity",
                "china",
                "CSI300",
                "000300",
                "2020-01-01",
                "2020-12-31",
                "2026-08-14T00:00:00+08:00",
                identity_marker * 64,
                manifest_marker * 64,
                f"/tmp/{release_id}.json",
                status,
                "2026-08-14T00:00:00+08:00",
            ),
        )


def _insert_target_artifact(
    db_module,
    *,
    artifact_id: str = "art_target",
    data_release_id: str = DATA_RELEASE_A,
    artifact_type: str = "TARGET_PORTFOLIO",
    promotion_status: str = "RESEARCH_PROMOTED",
) -> None:
    from app.services.artifact_registry import register_qlib_artifacts

    artifact = {
        "schemaVersion": "2.0",
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "promotionStatus": promotion_status,
        "dataReleaseId": data_release_id,
        "universeReleaseId": "universe-csi300-v1",
        "modelReleaseId": "art_model",
        "strategyPolicyId": "art_policy",
        "gitCommit": "fixture-commit",
        "containerDigest": "sha256:" + "c" * 64,
        "asOfTime": "2026-08-14T00:00:00+08:00",
        "signalDate": "2020-01-31",
        "tradeDate": "2020-02-03",
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "payloadSha256": "3" * 64,
        "parentArtifactIds": [],
        "payloadRef": {
            "objectKey": f"qlib/fixture/{artifact_id}.json",
            "mediaType": "application/json",
            "rows": 1,
        },
        "metadata": {},
    }
    with db_module.db() as connection:
        register_qlib_artifacts(connection, [artifact])


def _parameters(**overrides):
    value = {
        "qlibTargetPortfolioArtifactId": "art_target",
        "dataReleaseId": DATA_RELEASE_A,
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "start": "2020-02-01",
        "end": "2020-11-30",
    }
    value.update(overrides)
    return value


def _request(**overrides):
    value = {
        "symbol": "SH600000",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2020-02-01",
        "end": "2020-11-30",
        "cash": 100000,
        "parameters": {
            "qlibTargetPortfolioArtifactId": "art_target",
            "dataReleaseId": DATA_RELEASE_A,
        },
    }
    value.update(overrides)
    return value


def test_matching_active_release_accepts_subset_validation_scope():
    from app import db as db_module
    from app.services.qlib_release_scope import assert_qlib_release_scope

    db_module.init_db()
    _insert_release(db_module)
    _insert_target_artifact(db_module)

    release = assert_qlib_release_scope(_parameters())

    assert release is not None
    assert release["id"] == DATA_RELEASE_A
    assert release["asset_class"] == "equity"
    assert release["market"] == "china"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"assetClass": "future"}, "asset class mismatch"),
        ({"market": "hongkong", "venue": "hongkong"}, "market mismatch"),
        ({"start": "2019-12-31"}, "starts before DataRelease coverage"),
        ({"end": "2021-01-01"}, "ends after DataRelease coverage"),
    ],
)
def test_release_scope_rejects_asset_market_and_coverage_drift(overrides, message):
    from app import db as db_module
    from app.services.qlib_release_scope import (
        QlibReleaseScopeError,
        assert_qlib_release_scope,
    )

    db_module.init_db()
    _insert_release(db_module)
    _insert_target_artifact(db_module)

    with pytest.raises(QlibReleaseScopeError, match=message):
        assert_qlib_release_scope(_parameters(**overrides))


def test_release_scope_rejects_missing_or_inactive_release():
    from app import db as db_module
    from app.services.qlib_release_scope import (
        QlibReleaseScopeError,
        assert_qlib_release_scope,
    )

    db_module.init_db()
    with pytest.raises(QlibReleaseScopeError, match="not registered"):
        assert_qlib_release_scope(_parameters())

    _insert_release(db_module, status="revoked")
    with pytest.raises(QlibReleaseScopeError, match="not active"):
        assert_qlib_release_scope(_parameters())


def test_release_scope_rejects_unknown_or_wrong_type_target_artifact():
    from app import db as db_module
    from app.services.qlib_release_scope import (
        QlibReleaseScopeError,
        assert_qlib_release_scope,
    )

    db_module.init_db()
    _insert_release(db_module)
    with pytest.raises(QlibReleaseScopeError, match="target artifact is not registered"):
        assert_qlib_release_scope(_parameters())

    _insert_target_artifact(db_module, artifact_type="VALIDATION_RESULT")
    with pytest.raises(QlibReleaseScopeError, match="Qlib TARGET_PORTFOLIO"):
        assert_qlib_release_scope(_parameters())


@pytest.mark.parametrize("status", ["CANDIDATE", "RESEARCH_REVIEW", "REJECTED"])
def test_release_scope_rejects_unpromoted_target_artifact(status):
    from app import db as db_module
    from app.services.qlib_release_scope import (
        QlibReleaseScopeError,
        assert_qlib_release_scope,
    )

    db_module.init_db()
    _insert_release(db_module)
    _insert_target_artifact(db_module, promotion_status=status)

    with pytest.raises(QlibReleaseScopeError, match="RESEARCH_PROMOTED"):
        assert_qlib_release_scope(_parameters())


def test_release_scope_rejects_target_artifact_bound_to_another_release():
    from app import db as db_module
    from app.services.qlib_release_scope import (
        QlibReleaseScopeError,
        assert_qlib_release_scope,
    )

    db_module.init_db()
    _insert_release(db_module)
    _insert_release(db_module, release_id=DATA_RELEASE_B)
    _insert_target_artifact(db_module, data_release_id=DATA_RELEASE_B)

    with pytest.raises(QlibReleaseScopeError, match="artifact/DataRelease mismatch"):
        assert_qlib_release_scope(_parameters())


def test_non_qlib_preflight_path_is_unchanged_without_target_binding():
    from app.services.qlib_release_scope import assert_qlib_release_scope

    assert assert_qlib_release_scope(
        {
            "dataReleaseId": "not-a-release",
            "assetClass": "equity",
            "market": "usa",
            "start": "2020-01-01",
            "end": "2020-02-01",
        }
    ) is None


def test_scope_mismatch_stops_before_provider_repair_or_backtest_write(monkeypatch):
    from app import db as db_module
    from app.services import backtest_preflight
    from app.services.qlib_release_scope import QlibReleaseScopeError

    db_module.init_db()
    _insert_release(db_module)
    _insert_target_artifact(db_module)
    with db_module.db() as connection:
        before = int(connection.execute("select count(*) from backtest_runs").fetchone()[0])

    def unexpected_source(*args, **kwargs):
        raise AssertionError("provider/source resolution must not run after a Qlib release-scope mismatch")

    monkeypatch.setattr(backtest_preflight, "_source", unexpected_source)
    request = _request(symbol="00700", market="hongkong", venue="hongkong")

    with pytest.raises(QlibReleaseScopeError, match="market mismatch"):
        backtest_preflight.prepare_backtest_request(request, repair=True)

    with db_module.db() as connection:
        after = int(connection.execute("select count(*) from backtest_runs").fetchone()[0])
    assert after == before


def test_artifact_release_mismatch_stops_before_provider_repair_or_backtest_write(monkeypatch):
    from app import db as db_module
    from app.services import backtest_preflight
    from app.services.qlib_release_scope import QlibReleaseScopeError

    db_module.init_db()
    _insert_release(db_module)
    _insert_release(db_module, release_id=DATA_RELEASE_B)
    _insert_target_artifact(db_module, data_release_id=DATA_RELEASE_B)
    with db_module.db() as connection:
        before = int(connection.execute("select count(*) from backtest_runs").fetchone()[0])

    def unexpected_source(*args, **kwargs):
        raise AssertionError("provider/source resolution must not run after a Qlib artifact/release mismatch")

    monkeypatch.setattr(backtest_preflight, "_source", unexpected_source)

    with pytest.raises(QlibReleaseScopeError, match="artifact/DataRelease mismatch"):
        backtest_preflight.prepare_backtest_request(_request(), repair=True)

    with db_module.db() as connection:
        after = int(connection.execute("select count(*) from backtest_runs").fetchone()[0])
    assert after == before

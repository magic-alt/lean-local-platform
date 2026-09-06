from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_real_local_data_e2e_tracks_current_research_handoff_heading():
    spec = _read("tests/e2e/specs/20-data-preview-local.spec.ts")
    assert "研究交付与结果预览" in spec
    assert 'name: "研究工作台"' not in spec


def test_required_ci_includes_actual_release_convergence_gate():
    workflow = _read(".github/workflows/ci.yml")
    assert "release-convergence:" in workflow
    assert "python scripts/verify_release_convergence.py --manage-stack" in workflow
    assert "RELEASE_CONVERGENCE: ${{ needs.release-convergence.result }}" in workflow
    assert '"Release convergence": os.environ["RELEASE_CONVERGENCE"]' in workflow


def test_nightly_and_self_hosted_certification_workflows_are_fail_closed():
    nightly = _read(".github/workflows/nightly-full-integration.yml")
    real_data = _read(".github/workflows/self-hosted-real-data-certification.yml")

    assert "schedule:" in nightly
    assert "workflow_dispatch:" in nightly
    assert "python scripts/system_verify.py --profile full" in nightly
    assert "web/runtime/audit/*.json" in nightly

    assert "schedule:" in real_data
    assert "workflow_dispatch:" in real_data
    assert "runs-on: [self-hosted, lean-real-data]" in real_data
    assert "RUN_SELF_HOSTED_REAL_DATA_CERTIFICATION" in real_data
    assert "LEAN_REAL_DATA_DIR" in real_data
    assert "--profile local-data" in real_data
    assert "--data-release-id" in real_data


def test_full_and_local_data_system_profiles_require_release_convergence():
    verifier = _read("scripts/system_verify.py")
    assert 'args.profile in {"full", "local-data"}' in verifier
    assert 'convergence_command.append("--manage-stack")' in verifier
    assert 'cert_command.extend(["--data-release-id", args.data_release_id])' in verifier

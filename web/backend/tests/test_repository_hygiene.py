import json

from scripts.check_changelog import changelog_is_present
from scripts.check_repository_hygiene import absolute_strings, hygiene_errors


def test_changelog_gate_requires_root_changelog():
    assert changelog_is_present(["CHANGELOG.md", "web/backend/app/main.py"]) is True
    assert changelog_is_present(["web/backend/app/main.py"]) is False


def test_repository_hygiene_rejects_generated_tracked_paths():
    errors = hygiene_errors(["README.md", "web/runtime/runs/job/result.json", "Data/equity/test.zip"])
    assert any("web/runtime" in error for error in errors)
    assert any("Data/equity" in error for error in errors)


def test_portable_manifest_scanner_detects_absolute_paths():
    payload = json.loads('{"source":{"local_path":"/Users/example/cache/file.pdf"}}')
    assert absolute_strings(payload) == ["$.source.local_path=/Users/example/cache/file.pdf"]
    assert absolute_strings({"source": "csindex-cache:file.pdf"}) == []

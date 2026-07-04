import os


def test_load_env_file_reads_tushare_token_without_overriding_existing_value(tmp_path, monkeypatch):
    from app.core.config import _load_env_file

    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# local provider token
TUSHARE_TOKEN="from-file"
ALPHAVANTAGE_API_KEY=from-alpha
""",
        encoding="utf-8",
    )

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    _load_env_file(env_file)
    assert os.environ["TUSHARE_TOKEN"] == "from-file"
    assert os.environ["ALPHAVANTAGE_API_KEY"] == "from-alpha"

    monkeypatch.setenv("TUSHARE_TOKEN", "from-env")
    _load_env_file(env_file)
    assert os.environ["TUSHARE_TOKEN"] == "from-env"

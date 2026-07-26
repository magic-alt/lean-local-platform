import os
import json

import pytest


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


@pytest.mark.parametrize(
    ("environment", "provider", "base_url", "model"),
    [
        ({"DEEPSEEK_API_KEY": "deepseek-key"}, "deepseek", "https://api.deepseek.com", "deepseek-v4-flash"),
        ({"ZHIPU_API_KEY": "zhipu-key"}, "zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-5.2"),
        ({"ZAI_API_KEY": "zai-key"}, "zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-5.2"),
        ({"KIMI_API_KEY": "kimi-key"}, "kimi", "https://api.moonshot.cn/v1", "kimi-k2.6"),
        ({"MOONSHOT_API_KEY": "moonshot-key"}, "kimi", "https://api.moonshot.cn/v1", "kimi-k2.6"),
        ({"OPENAI_API_KEY": "openai-key"}, "openai", "https://api.openai.com/v1", "gpt-5-mini"),
        ({"ANTHROPIC_API_KEY": "anthropic-key"}, "anthropic", "https://api.anthropic.com/v1", "claude-sonnet-4-6"),
    ],
)
def test_insights_llm_provider_is_inferred_from_api_key(environment, provider, base_url, model):
    from app.core.config import _resolve_insights_llm

    resolved = _resolve_insights_llm(environment)

    assert resolved == {
        "provider": provider,
        "api_key": next(iter(environment.values())),
        "base_url": base_url,
        "model": model,
    }


def test_insights_llm_explicit_provider_and_overrides_win():
    from app.core.config import _resolve_insights_llm

    resolved = _resolve_insights_llm(
        {
            "DEEPSEEK_API_KEY": "deepseek-key",
            "OPENAI_API_KEY": "openai-key",
            "LEAN_INSIGHTS_LLM_PROVIDER": "openai",
            "LEAN_INSIGHTS_LLM_BASE_URL": "https://gateway.example/v1",
            "LEAN_INSIGHTS_LLM_MODEL": "custom-model",
        }
    )

    assert resolved == {
        "provider": "openai",
        "api_key": "openai-key",
        "base_url": "https://gateway.example/v1",
        "model": "custom-model",
    }


def test_database_descriptor_defaults_to_mysql_without_sqlite_path(monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_URL", "mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market")
    descriptor = db_module.database_descriptor()

    assert descriptor["engine"] == "mysql"
    assert descriptor["database"] == "lean_market"
    assert "path" not in descriptor
    assert "HS300.sqlite3" not in json.dumps(descriptor)


def test_sqlite_database_url_is_rejected_outside_test_gate(monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:////tmp/lean-platform.sqlite3")
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", False)

    with pytest.raises(RuntimeError, match="SQLite is disabled"):
        db_module.database_backend()


def test_pipeline_v2_default_is_enabled():
    from app.core import config

    assert config.PAPER_ORDER_PIPELINE_V2_ENABLED is True

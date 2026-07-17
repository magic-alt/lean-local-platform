def test_mysql_alter_table_text_columns_use_mysql_compatible_types():
    from app.db import _translate_mysql_sql

    assert _translate_mysql_sql(
        "alter table paper_sessions add column mode text not null default 'legacy_replay'"
    ) == "alter table paper_sessions add column mode varchar(255) not null default 'legacy_replay'"
    assert _translate_mysql_sql(
        "alter table research_sessions add column workspace_path text"
    ) == "alter table research_sessions add column workspace_path varchar(1024)"
    assert _translate_mysql_sql(
        "alter table backtest_runs add column failure_json text"
    ) == "alter table backtest_runs add column failure_json longtext"

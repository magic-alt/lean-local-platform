from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from types import SimpleNamespace


def test_scheduled_mysql_backup_is_registered():
    from app.tasks.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule["backup-mysql-daily"]
    assert schedule["task"] == "lean_web.backup_mysql"


def test_mysql_backup_writes_checksum_and_prunes_expired_files(tmp_path, monkeypatch):
    from app.services import mysql_backup

    old = tmp_path / "lean_market-20260101T000000Z.sql"
    old.write_text("old", encoding="utf-8")
    old.with_suffix(".sql.sha256").write_text("old", encoding="utf-8")
    expired = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    os.utime(old, (expired, expired))
    monkeypatch.setenv("LEAN_DATABASE_URL", "mysql+pymysql://lean:secret@mysql:3306/lean_market")
    monkeypatch.setenv("LEAN_MYSQL_BACKUP_RETENTION_DAYS", "7")
    monkeypatch.setenv("LEAN_MYSQL_BACKUP_MAX_FILES", "1")
    monkeypatch.setattr(mysql_backup.shutil, "which", lambda name: "/usr/bin/mysqldump")

    def fake_run(command, *, stdout, stderr, env, check):
        assert "secret" not in " ".join(command)
        assert env["MYSQL_PWD"] == "secret"
        stdout.write(b"create table unit(id int);\n")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(mysql_backup.subprocess, "run", fake_run)

    result = mysql_backup.create_backup(tmp_path)

    assert result["status"] == "success"
    assert Path(result["backup"]).exists()
    assert Path(result["checksum"]).exists()
    assert old.name in result["pruned"]
    assert not old.exists()

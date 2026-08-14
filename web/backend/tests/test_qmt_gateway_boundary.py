from __future__ import annotations

from pathlib import Path


def test_qmt_gateway_has_no_database_or_broker_write_surface():
    backend = Path(__file__).resolve().parents[1]
    gateway = backend / "app" / "broker" / "qmt_gateway"
    source = "\n".join(path.read_text(encoding="utf-8") for path in gateway.glob("*.py"))

    assert "sqlite" not in source.lower()
    assert "from ...db" not in source
    assert "order_stock" not in source
    assert "cancel_order_stock" not in source
    assert "POST" not in source
    assert "@app.post" not in source
    assert "@app.put" not in source
    assert "@app.patch" not in source
    assert "@app.delete" not in source


def test_qmt_gateway_is_owned_by_platform_broker_domain():
    backend = Path(__file__).resolve().parents[1]
    assert (backend / "app" / "broker" / "qmt_gateway" / "__main__.py").is_file()
    assert not (backend / "app" / "research" / "qmt_gateway").exists()

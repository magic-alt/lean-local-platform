from pathlib import Path

from .errors import LeanWebError


def ensure_child_path(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise LeanWebError("Path escapes the project directory.")
    return target


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    slug = "-".join(part for part in slug.split("-") if part)
    if not slug:
        raise LeanWebError("Name must contain letters or numbers.")
    return slug[:80]

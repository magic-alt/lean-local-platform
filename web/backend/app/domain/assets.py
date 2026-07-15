from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import DATA_DIR, REPO_ROOT
from ..core.errors import LeanWebError


class AssetDomainError(LeanWebError, ValueError):
    pass


ASSET_CLASSES = {"equity", "crypto", "crypto_future", "future"}
RESOLUTIONS = {"daily", "hour", "minute", "second", "tick"}
DATA_TYPES = {"trade", "quote", "openinterest", "open_interest"}


@dataclass(frozen=True)
class AssetRequest:
    asset_class: str
    symbol: str
    venue: str
    resolution: str = "daily"
    data_type: str = "trade"

    @property
    def lean_data_type(self) -> str:
        return "openinterest" if self.data_type == "open_interest" else self.data_type


def asset_class_key(value: str | None = None) -> str:
    key = (value or "equity").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "stock": "equity",
        "stocks": "equity",
        "crypto-future": "crypto_future",
        "cryptofuture": "crypto_future",
        "crypto_futures": "crypto_future",
        "futures": "future",
    }
    key = aliases.get(key, key)
    if key not in ASSET_CLASSES:
        raise AssetDomainError(f"Unsupported asset class: {value!r}")
    return key


def resolution_key(value: str | None = None) -> str:
    key = (value or "daily").strip().lower()
    aliases = {"day": "daily", "d": "daily", "1d": "daily", "1h": "hour", "1m": "minute"}
    key = aliases.get(key, key)
    if key not in RESOLUTIONS:
        raise AssetDomainError(f"Unsupported resolution: {value!r}")
    return key


def data_type_key(value: str | None = None) -> str:
    key = (value or "trade").strip().lower().replace("-", "_")
    if key not in DATA_TYPES:
        raise AssetDomainError(f"Unsupported data type: {value!r}")
    return "open_interest" if key == "openinterest" else key


def venue_key(asset_class: str, value: str | None = None, market: str | None = None) -> str:
    asset_class = asset_class_key(asset_class)
    raw = (value or market or "").strip().lower().replace("-", "")
    if asset_class == "equity":
        aliases = {
            "": "usa",
            "us": "usa",
            "usa": "usa",
            "cn": "china",
            "china": "china",
            "ashare": "china",
            "a": "china",
            "hk": "hongkong",
            "hkg": "hongkong",
            "hongkong": "hongkong",
        }
        return aliases.get(raw, raw or "usa")
    if asset_class in {"crypto", "crypto_future"}:
        aliases = {"": "coinbase", "cb": "coinbase", "gdax": "coinbase"}
        return aliases.get(raw, raw or "coinbase")
    aliases = {"": "comex"}
    return aliases.get(raw, raw or "comex")


def canonical_symbol(symbol: str, asset_class: str = "equity") -> str:
    value = symbol.strip()
    if not value:
        raise AssetDomainError("Symbol is required.")
    asset_class = asset_class_key(asset_class)
    if asset_class in {"crypto", "crypto_future"}:
        cleaned = value.replace("/", "").replace("-", "").replace("_", "").upper()
    elif asset_class == "future":
        cleaned = value.replace("/", "").replace("-", "").replace("_", "").upper()
    else:
        cleaned = value.upper()
    if not all(ch.isalnum() or ch == "." for ch in cleaned):
        raise AssetDomainError(f"Invalid symbol: {symbol!r}")
    return cleaned


def asset_request(
    symbol: str,
    asset_class: str | None = None,
    venue: str | None = None,
    market: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> AssetRequest:
    klass = asset_class_key(asset_class)
    return AssetRequest(
        asset_class=klass,
        symbol=canonical_symbol(symbol, klass),
        venue=venue_key(klass, venue, market),
        resolution=resolution_key(resolution),
        data_type=data_type_key(data_type),
    )


def lean_data_paths(request: AssetRequest) -> list[Path]:
    symbol = request.symbol.lower()
    data_type = request.lean_data_type
    if request.asset_class == "equity":
        return [DATA_DIR / "equity" / request.venue / request.resolution / f"{symbol}.zip"]
    if request.asset_class == "crypto":
        base = DATA_DIR / "crypto" / request.venue / request.resolution
        if request.resolution in {"daily", "hour"}:
            return [base / f"{symbol}_{data_type}.zip"]
        return sorted((base / symbol).glob(f"*_{data_type}.zip"))
    if request.asset_class == "crypto_future":
        base = DATA_DIR / "cryptofuture" / request.venue / request.resolution
        if request.resolution in {"daily", "hour"}:
            return [base / f"{symbol}_{data_type}.zip"]
        return sorted((base / symbol).glob(f"*_{data_type}.zip"))
    base = DATA_DIR / "future" / request.venue / request.resolution
    if request.resolution in {"daily", "hour"}:
        return [base / f"{symbol}_{data_type}.zip"]
    return sorted((base / symbol).glob(f"*_{data_type}.zip"))


def has_lean_data(request: AssetRequest) -> bool:
    return any(path.exists() for path in lean_data_paths(request))


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _zip_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with zipfile.ZipFile(path) as archive:
            total = 0
            for member in archive.namelist():
                with archive.open(member) as file:
                    total += sum(1 for line in file if line.strip())
            return total
    except zipfile.BadZipFile:
        return 0


def list_local_data_files(limit: int = 1000) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    patterns = [
        ("equity", DATA_DIR / "equity", ["market", "resolution", "file"]),
        ("crypto", DATA_DIR / "crypto", ["venue", "resolution", "symbol_or_file", "file"]),
        ("crypto_future", DATA_DIR / "cryptofuture", ["venue", "resolution", "symbol_or_file", "file"]),
        ("future", DATA_DIR / "future", ["venue", "resolution", "symbol_or_file", "file"]),
    ]
    for asset_class, root, _shape in patterns:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.zip")):
            parts = path.relative_to(root).parts
            if asset_class == "equity" and len(parts) >= 3:
                venue, resolution, filename = parts[0], parts[1], parts[-1]
                symbol = path.stem.upper()
                data_type = "trade"
            elif asset_class != "equity" and len(parts) >= 3:
                venue, resolution = parts[0], parts[1]
                stem = path.stem.lower()
                data_type = "trade"
                for suffix in ("_openinterest", "_quote", "_trade"):
                    if stem.endswith(suffix):
                        data_type = suffix[1:]
                        stem = stem[: -len(suffix)]
                        break
                symbol = parts[2].upper() if len(parts) >= 4 else stem.upper()
            else:
                continue
            items.append(
                {
                    "assetClass": asset_class,
                    "symbol": symbol,
                    "venue": venue,
                    "market": venue if asset_class == "equity" else None,
                    "resolution": resolution,
                    "dataType": "open_interest" if data_type == "openinterest" else data_type,
                    "file": _relative(path),
                    "rows": _zip_rows(path) if len(items) < 200 else None,
                    "size": path.stat().st_size,
                }
            )
            if len(items) >= limit:
                return items
    return items


def list_local_symbols_for_asset(
    asset_class: str = "equity",
    venue: str | None = None,
    market: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
) -> list[str]:
    klass = asset_class_key(asset_class)
    venue_value = venue_key(klass, venue, market)
    resolution_value = resolution_key(resolution)
    data_type_value = data_type_key(data_type)
    if klass == "equity":
        root = DATA_DIR / "equity" / venue_value / resolution_value
        return sorted(path.stem.upper() for path in root.glob("*.zip")) if root.exists() else []
    root_name = "cryptofuture" if klass == "crypto_future" else klass
    root = DATA_DIR / root_name / venue_value / resolution_value
    if not root.exists():
        return []
    suffix = f"_{'openinterest' if data_type_value == 'open_interest' else data_type_value}.zip"
    if resolution_value in {"daily", "hour"}:
        return sorted(path.name[: -len(suffix)].upper() for path in root.glob(f"*{suffix}"))
    return sorted(path.name.upper() for path in root.iterdir() if path.is_dir())


def parse_lean_zip_price_series(
    request: AssetRequest,
    start_date,
    end_date,
) -> list[dict[str, Any]]:
    return [
        {"time": row["time"], "value": row["close"]}
        for row in parse_lean_zip_ohlcv_series(request, start_date, end_date)
    ]


def parse_lean_zip_ohlcv_series(
    request: AssetRequest,
    start_date,
    end_date,
) -> list[dict[str, Any]]:
    points_by_time: dict[str, dict[str, Any]] = {}
    scale = 10000 if request.asset_class == "equity" else 1
    for path in lean_data_paths(request):
        if not path.exists() or not path.is_file():
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for member in archive.namelist():
                    with archive.open(member) as file:
                        for raw_line in file:
                            line = raw_line.decode("utf-8", errors="replace").strip()
                            if not line:
                                continue
                            fields = line.split(",")
                            if len(fields) < 5:
                                continue
                            try:
                                item_date = datetime.strptime(fields[0].split()[0], "%Y%m%d").date()
                                open_price = float(fields[1]) / scale
                                high = float(fields[2]) / scale
                                low = float(fields[3]) / scale
                                close = float(fields[4]) / scale
                                volume = float(fields[5]) if len(fields) > 5 else 0.0
                            except ValueError:
                                continue
                            if start_date and item_date < start_date:
                                continue
                            if end_date and item_date > end_date:
                                continue
                            timestamp = datetime(item_date.year, item_date.month, item_date.day, 21, tzinfo=timezone.utc)
                            time_key = timestamp.isoformat()
                            points_by_time[time_key] = {
                                "time": time_key,
                                "open": open_price,
                                "high": high,
                                "low": low,
                                "close": close,
                                "volume": volume,
                            }
        except zipfile.BadZipFile:
            continue
    return [value for _, value in sorted(points_by_time.items())]

from __future__ import annotations

import time

from .symbols import symbol_key

def new_run_id(symbol: str, start: str, end: str) -> str:
    return f"{symbol_key(symbol)}-{start.replace('-', '')}-{end.replace('-', '')}-{time.strftime('%Y%m%d%H%M%S')}"

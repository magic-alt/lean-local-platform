from __future__ import annotations

import time
import uuid

from .symbols import symbol_key

def new_run_id(symbol: str, start: str, end: str) -> str:
    # The ID is also the backtest primary key, container name and run directory.
    # Seconds alone collide under experiment fan-out, so retain the readable
    # timestamp while adding cryptographically strong per-run entropy.
    return (
        f"{symbol_key(symbol)}-{start.replace('-', '')}-{end.replace('-', '')}-"
        f"{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:12]}"
    )

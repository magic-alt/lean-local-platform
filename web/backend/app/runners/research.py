from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol


class ResearchBackend(Protocol):
    name: str

    def start(
        self,
        session_id: str,
        project_dir: Path,
        port: int,
        output_callback: Callable[[str], None],
    ) -> dict[str, Any]:
        ...

    def stop(self, session_id: str) -> None:
        ...

    def remove(self, session_id: str) -> None:
        ...

    def state(self, session_id: str) -> dict[str, Any]:
        ...

    def logs(self, session_id: str, *, tail: int = 200) -> str:
        ...

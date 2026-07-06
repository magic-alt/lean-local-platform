from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..core.config import PLOT_SCRIPT, REPO_ROOT

def render_report(result_json: Path, report_html: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PLOT_SCRIPT),
            "--input",
            str(result_json),
            "--output",
            str(report_html),
        ],
        check=True,
        cwd=REPO_ROOT,
    )

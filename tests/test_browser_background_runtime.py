from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "browser-extension-background.test.cjs"


def test_browser_background_runtime_contracts_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; browser background runtime harness requires Node.js.")
    result = subprocess.run(
        [node, "--test", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

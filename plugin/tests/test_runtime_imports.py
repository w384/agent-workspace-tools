import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_provider_imports_from_plugin_runtime_root() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from provider.workspace import WorkspaceProvider"],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

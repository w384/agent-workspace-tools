import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_project_dependencies_are_valid_pep_508_requirements() -> None:
    project = tomllib.loads(
        (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    requirements = [Requirement(value) for value in project["dependencies"]]

    assert requirements[0].name == "dify-plugin"
    assert Version("0.9.1") in requirements[0].specifier
    assert Version("0.10.0") not in requirements[0].specifier

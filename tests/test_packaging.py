"""Version strings live in three places. Keep them from drifting apart."""

from __future__ import annotations

import pathlib
import re

import parlayapi_tools
from parlayapi_tools.core import ParlayAPIClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text()


def _pyproject_version() -> str:
    match = re.search(r'^version = "([^"]+)"', PYPROJECT, re.MULTILINE)
    assert match, "no version in pyproject.toml"
    return match.group(1)


def test_dunder_version_matches_pyproject():
    assert parlayapi_tools.__version__ == _pyproject_version()


def test_user_agent_reports_the_real_version():
    assert ParlayAPIClient().user_agent == (
        f"parlayapi-agent-tools/{parlayapi_tools.__version__}"
    )


def test_optional_extras_are_declared():
    for extra in ("langchain", "llamaindex", "dev"):
        assert f"{extra} = [" in PYPROJECT


def test_core_declares_no_runtime_dependencies():
    # The whole point of the stdlib only client. If a dependency creeps in
    # here, `pip install parlayapi-agent-tools` stops being free of side
    # effects for someone who only wants the raw JSON schemas.
    assert "dependencies = []" in PYPROJECT

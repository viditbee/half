"""AD-2 as a pytest, not inline YAML.

The gate previously lived only in the workflow, so nothing could test the gate
itself — and it was wrong in both directions: a dependency with no version
bound passed, while a correctly pinned one whose import name differs from its
distribution name red-built CI.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPECIFIERS = ("==", ">=", "<=", "~=", "!=", ">", "<")


def declared_dependencies() -> list[str]:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return meta.get("project", {}).get("dependencies", [])


def distribution_name(spec: str) -> str:
    """The bare name from a requirement string, markers and extras removed."""
    head = spec.split(";")[0].split("[")[0].strip()
    for token in _SPECIFIERS:
        head = head.split(token)[0]
    return head.strip()


def is_pinned(spec: str) -> bool:
    return any(token in spec.split(";")[0] for token in _SPECIFIERS)


def importable_names(distributions: set[str]) -> set[str]:
    """Import names for the given distributions, from installed metadata.

    Resolved rather than hardcoded: an earlier version special-cased
    python-telegram-bot -> telegram, which would have failed the build for the
    next dependency whose names differ.
    """
    names = set(distributions)
    for import_name, dists in packages_distributions().items():
        if {d.replace("_", "-").lower() for d in dists} & {
            d.replace("_", "-").lower() for d in distributions
        }:
            names.add(import_name)
    return names


def runtime_imports() -> set[str]:
    roots: set[str] = set()
    for path in (ROOT / "half").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("spec", declared_dependencies())
def test_every_declared_dependency_carries_a_version_bound(spec):
    """The gate is named for pinning, so it must actually check pinning."""
    assert is_pinned(spec), f"{spec!r} declares no version bound"


def test_the_runtime_imports_only_stdlib_and_declared_dependencies():
    declared = {distribution_name(s) for s in declared_dependencies()}
    allowed = importable_names(declared) | sys.stdlib_module_names | {"half"}
    leaked = sorted(runtime_imports() - allowed)
    assert not leaked, f"undeclared runtime dependency: {leaked}"


def test_an_unpinned_specifier_is_recognised_as_unpinned():
    assert not is_pinned("requests")
    assert is_pinned("requests>=2")
    assert is_pinned("requests==2.0.0")
    assert is_pinned("foo>=1; python_version<'3.13'")


def test_a_marker_or_extra_does_not_corrupt_the_name():
    assert distribution_name("foo; python_version<'3.13'") == "foo"
    assert distribution_name("foo[bar]>=1") == "foo"
    assert distribution_name("python-telegram-bot>=22.8,<23") == "python-telegram-bot"


def test_import_names_are_resolved_from_metadata_not_hardcoded():
    """python-telegram-bot installs as `telegram`; resolving from installed
    metadata generalises to the next dependency whose names differ."""
    assert "telegram" in importable_names({"python-telegram-bot"})

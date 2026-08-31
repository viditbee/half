"""AD-11 as a pytest, not inline YAML.

The gate previously lived only in the workflow, so nothing could test the gate
itself — and it drifted: it stopped calling `scan_for_secrets`, losing the
symlink and unreadable-file findings that module documents as "earned by
review", and it stopped looking at untracked files, so a stray `.env` in the
workspace would no longer fail CI.

The AD-2 gate was moved into the suite for exactly this reason, with a comment
saying the inline version was wrong. This one went the other way one commit
later.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from half.store.export import scan_for_secrets

ROOT = Path(__file__).resolve().parents[1]

#: Files whose job is to carry secret-shaped samples, so a scanner can be
#: tested at all. Deliberately a short, explicit list rather than a pattern:
#: the danger of an exemption is that it grows until it hides a real leak, so
#: `test_the_exemption_stays_small_and_justified` pins both its size and the
#: requirement that every entry actually contains samples.
SAMPLE_FILES = frozenset({
    "tests/test_scrub.py",
    "tests/test_ingest.py",
})


def _git(*args: str) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, check=True
    ).stdout
    return [ROOT / n.decode() for n in out.split(b"\0") if n]


def tracked_files() -> list[Path]:
    return [p for p in _git("ls-files", "-z") if _name(p) not in SAMPLE_FILES]


def untracked_files() -> list[Path]:
    return [p for p in _git("ls-files", "--others", "--exclude-standard", "-z")]


def _name(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            # Unscannable is a finding, never a skip.
            findings.append(f"unscannable entry: {_name(path)}")
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"unreadable: {_name(path)}: {exc}")
            continue
        for label, pattern in _patterns():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{label} at {_name(path)}:{line}")
    return findings


def _patterns():
    from half.ingest.scrub import ALL_PATTERNS

    return ALL_PATTERNS


def test_no_tracked_file_carries_secret_material():
    assert _scan(tracked_files()) == []


def test_no_untracked_file_carries_secret_material():
    """A stray .env or token cache sitting in the workspace must fail too —
    narrowing the gate to tracked files alone lost this."""
    assert _scan(untracked_files()) == []


def test_the_exemption_stays_small_and_justified():
    """An exemption that grows silently is how this class of gate rots."""
    assert len(SAMPLE_FILES) <= 3, "the sample exemption is growing"
    for name in SAMPLE_FILES:
        path = ROOT / name
        assert path.is_file(), f"exempt file does not exist: {name}"
        assert "SAMPLES" in path.read_text(encoding="utf-8") or "SECRET" in path.read_text(
            encoding="utf-8"
        ), f"{name} is exempt but carries no samples"


def test_exempt_files_are_still_scanned_for_real_credential_shapes():
    """The exemption covers synthetic samples, not everything. A real Google
    or AWS credential in a test file must still fail."""
    live_only = ("google oauth refresh token", "google api key", "aws access key id")
    for name in SAMPLE_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for label, pattern in _patterns():
            if label not in live_only:
                continue
            for match in pattern.finditer(text):
                # Samples are assembled at runtime, so a literal match here
                # means an actual credential was pasted in.
                raise AssertionError(f"{label} literal in {name}: {match.group()[:12]}…")


def test_the_gate_scans_a_plausible_number_of_files():
    """Guards against a selection bug silently scanning nothing."""
    assert len(tracked_files()) > 20


def test_the_gate_reports_a_planted_secret(tmp_path):
    planted = tmp_path / "leak.txt"
    planted.write_text("AKIA" + "IOSFODNN7EXAMPLE", encoding="utf-8")
    assert _scan([planted])


def test_an_unscannable_entry_is_a_finding_not_a_skip(tmp_path):
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "nowhere")
    assert _scan([link])


def test_scan_for_secrets_still_fails_closed_on_a_symlink(tmp_path):
    """The function the export path actually uses, kept exercised."""
    (tmp_path / "link").symlink_to(tmp_path / "nowhere")
    assert scan_for_secrets(tmp_path)

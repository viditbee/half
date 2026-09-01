"""The suite reaches no network, asserted at the socket (story 9b).

Every previous story kept the suite offline by *design* — the transport is
injected, the fake is four methods long, and nothing in a test constructs a
real client. That is a convention, and this file is what makes it a property.

**Why it has to be the whole suite and not this package.** A model port is the
first thing in Half that has a reason to open a connection, and the way the
suite stops being hermetic is not a test that calls the API on purpose. It is a
default: an SDK constructed without a transport, a module-scope client, an
integration case somebody marks ``skip`` and then unmarks, a doctest. Each of
those is invisible in review, passes on a laptop with a key in the environment,
and turns CI red only on the day the key expires — or, worse, quietly bills an
account from a build server.

So the gate is a **socket**. It runs the whole suite in a subprocess with
``connect`` — in every spelling — replaced by something that raises, and
asserts the suite still passes. Nothing above the socket has to be trusted:
not the SDK, not a transport, not a test's own good intentions.

The guard is installed through ``sitecustomize`` rather than as a pytest
plugin, deliberately: the suite spawns subprocesses of its own (the timezone
and lock cases in ``tests/test_schedule.py``), and a plugin would cover the
pytest process while leaving every child of it unwatched.
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.offline, pytest.mark.ad19]

ROOT = Path(__file__).resolve().parents[1]

#: Set on every subprocess this file starts. A nested run of this module skips
#: itself, so the gate cannot recurse **even if the ``--ignore`` below is
#: wrong** — which it was, once, and the result was a fork bomb of pytest
#: processes rather than a failing test. A path is a spelling; this is a
#: property.
GATE_ENV = "HALF_OFFLINE_GATE_RUNNING"

if os.environ.get(GATE_ENV):  # pragma: no cover - the nested run
    pytest.skip(
        "the offline gate does not run inside itself", allow_module_level=True
    )

#: Every way a Python process can start a connection. Not three spellings —
#: *the ways*: the method on the socket, the module-level helpers, and name
#: resolution, which is the one an SDK reaches first and which a guard that
#: only watched ``connect`` would let straight through.
GUARD = '''
"""Installed on sys.path for the duration of one subprocess run."""
import socket


class NetworkReached(AssertionError):
    """A test opened a socket. The suite is hermetic; something regressed."""


def _blocked(*args, **kwargs):
    raise NetworkReached(
        "the suite tried to reach the network. Every transport is injected "
        "(AD-19, story 2); a test that needs one uses a fake."
    )


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.socket.sendto = _blocked
socket.socket.sendmsg = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
socket.gethostbyname = _blocked
socket.gethostbyname_ex = _blocked
'''


def _run_suite(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the suite in a subprocess whose sockets are dead."""
    (tmp_path / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    env[GATE_ENV] = "1"
    # A key in the developer's own environment must not be what decides whether
    # this passes — and must certainly not be reachable from a test run.
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_PROFILE",
    ):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        # A gate that hangs is a gate that gets deleted. One suite run takes
        # seconds; a minute is a fault, not slowness.
        timeout=600,
    )


@pytest.mark.ad19_guarantee
def test_the_whole_suite_opens_no_socket(tmp_path):
    """The acceptance criterion: *the whole suite reaches no network*.

    Slow by the cost of one suite run, and worth it: this is the only case in
    the tree that would notice an SDK constructed for real, and it notices it
    wherever it is written rather than only in the package that owns the port.

    ``--ignore`` on this file is what stops the run recursing into itself; the
    ignored file is exactly this one, so nothing else is exempt.
    """
    relative = Path(__file__).resolve().relative_to(ROOT)
    done = _run_suite(tmp_path, f"--ignore={relative}", "tests")
    assert done.returncode == 0, (
        "the suite failed under the socket guard.\n"
        "A `NetworkReached` below means something opened a connection; anything "
        f"else is an ordinary failure.\n{done.stdout[-8000:]}\n{done.stderr[-4000:]}"
    )
    assert "NetworkReached" not in done.stdout
    assert "NetworkReached" not in done.stderr


@pytest.mark.ad19_guarantee
def test_the_socket_guard_would_notice_a_real_connection(tmp_path):
    """Non-vacuity, and the whole worth of the case above.

    A gate nobody has tried to defeat is a gate resting on nothing — the lesson
    ``tests/test_crisis.py`` records and story 9a had to relearn twice. So this
    writes a test that *does* reach out, runs it under the same guard, and
    asserts the guard stops it.
    """
    reaching = tmp_path / "test_reaching_out.py"
    reaching.write_text(
        "import socket\n"
        "def test_reaches_out():\n"
        "    socket.create_connection(('example.invalid', 80), timeout=1)\n",
        encoding="utf-8",
    )
    done = _run_suite(tmp_path, str(reaching))
    assert done.returncode != 0, "the guard let a real connection through"
    assert "NetworkReached" in done.stdout + done.stderr


@pytest.mark.ad19_guarantee
@pytest.mark.parametrize(
    "reaching",
    [
        "socket.create_connection(('example.invalid', 80))",
        "socket.getaddrinfo('example.invalid', 80)",
        "socket.gethostbyname('example.invalid')",
        "socket.socket().connect(('example.invalid', 80))",
        "socket.socket().connect_ex(('example.invalid', 80))",
    ],
    ids=["create-connection", "getaddrinfo", "gethostbyname", "connect", "connect-ex"],
)
def test_the_guard_sees_each_way_of_reaching_out(tmp_path, reaching):
    """Non-vacuity, one *way* at a time.

    Resolution is here because it is the one an SDK reaches first: a guard that
    watched only ``connect`` would let a DNS lookup — and the leak of whatever
    hostname was configured — straight through.
    """
    path = tmp_path / f"test_way_{abs(hash(reaching))}.py"
    path.write_text(
        f"import socket\ndef test_way():\n    {reaching}\n", encoding="utf-8"
    )
    done = _run_suite(tmp_path, str(path))
    assert "NetworkReached" in done.stdout + done.stderr, f"unwatched: {reaching}"


@pytest.mark.ad19_guarantee
def test_the_guard_covers_a_subprocess_the_suite_spawns(tmp_path):
    """Why ``sitecustomize`` and not a pytest plugin.

    ``tests/test_schedule.py`` runs child interpreters, and a plugin loaded into
    the pytest process would leave every one of them unwatched — which is
    exactly where an "integration" case would end up once somebody noticed the
    guard.
    """
    path = tmp_path / "test_child.py"
    path.write_text(
        "import subprocess, sys\n"
        "def test_child():\n"
        "    out = subprocess.run(\n"
        "        [sys.executable, '-c',\n"
        "         \"import socket; socket.create_connection(('example.invalid', 80))\"],\n"
        "        capture_output=True, text=True)\n"
        "    assert 'NetworkReached' in out.stderr, out.stderr\n",
        encoding="utf-8",
    )
    done = _run_suite(tmp_path, str(path))
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-2000:]


# ── in-process: importing and constructing reach nothing ─────────────────────


@pytest.fixture
def no_sockets(monkeypatch):
    """The same guard, in this process, for the cases that need to inspect."""

    def blocked(*args, **kwargs):
        raise AssertionError("a socket was opened")

    for name in (
        "connect", "connect_ex", "sendto", "sendmsg",
    ):
        monkeypatch.setattr(socket.socket, name, blocked, raising=False)
    for name in (
        "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex",
    ):
        monkeypatch.setattr(socket, name, blocked, raising=False)
    return blocked


PACKAGE_MODULES = (
    "half.model",
    "half.model.port",
    "half.model.tier",
    "half.model.budget",
    "half.model.anthropic",
    "half.model.anthropic_transport",
)


@pytest.mark.ad19_guarantee
def test_every_module_in_the_package_imports_with_no_network(tmp_path):
    """Matrix: *offline construction*. Never reaches out.

    **In a subprocess, not through ``importlib.reload``.** The first version
    reloaded each module in the pytest process, which rebinds the classes every
    later test in that process is holding — so an ``isinstance`` in another
    file could start failing depending on collection order, and hermeticity
    became an ordering accident. A fresh interpreter imports each module for
    the first time, which is also the only way to prove there is no import side
    effect that already ran.
    """
    script = (
        "import importlib, sys\n"
        f"for name in {PACKAGE_MODULES!r}:\n"
        "    assert name not in sys.modules, name\n"
        "    importlib.import_module(name)\n"
        "assert 'anthropic' not in sys.modules, "
        "'importing the package pulled in the SDK'\n"
        "print('imported')\n"
    )
    done = _run_python(tmp_path, script)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "imported" in done.stdout


def _run_python(tmp_path: Path, script: str) -> subprocess.CompletedProcess:
    """One fresh interpreter, with the socket guard installed."""
    (tmp_path / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    env[GATE_ENV] = "1"
    for name in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
        "ANTHROPIC_PROFILE",
    ):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def test_the_provider_constructs_with_no_key_and_reaches_nothing(
    no_sockets, monkeypatch
):
    """Matrix: *offline construction*. Imports and constructs, contacts nothing."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    from tests.test_model import FakeTransport, budget, tiers
    from half.model.anthropic import AnthropicProvider

    provider = AnthropicProvider(FakeTransport(), tiers=tiers(), budget=budget())
    assert provider.classifier() is not None


def test_the_sdk_transport_builds_its_client_without_contacting_anything(no_sockets):
    """Constructing a client is not a request, and this pins that it stays so.

    The key is a shape, built at runtime rather than written down, so that this
    file does not itself trip the AD-11 secret gate.
    """
    from half.model.anthropic_transport import SDKTransport

    transport = SDKTransport("sk-" + "ant-" + "B" * 40)
    assert transport is not None


def test_the_offline_gate_names_the_file_it_exempts():
    """The one exemption is this file, and it is exempt only from *itself*.

    Read off the syntax tree rather than off the text, because a check written
    as a substring count would match its own assertion and be unwriteable.
    What it asserts: the suite run passes exactly one ``--ignore``, that
    ``--ignore`` is built from this file's own path, and nothing anywhere in
    this module quietly deselects with ``-k`` or ``--deselect``.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    # Only the arguments actually handed to a suite run are inspected. Scanning
    # the whole module would match this case's own assertions, which is how a
    # self-referential guard becomes unwriteable.
    arguments: list[ast.expr] = [
        argument
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_suite"
        for argument in node.args[1:]
    ]

    deselecting = {
        node.value
        for argument in arguments
        for node in ast.walk(argument)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and (node.value.startswith("--deselect") or node.value == "-k")
    }
    assert not deselecting, f"the gate quietly deselects with {deselecting}"

    ignores = [
        argument
        for argument in arguments
        if isinstance(argument, ast.JoinedStr)
        and isinstance(argument.values[0], ast.Constant)
        and argument.values[0].value == "--ignore="
    ]
    assert len(ignores) == 1, f"{len(ignores)} things are exempt from the gate"
    named = {n.id for n in ast.walk(ignores[0]) if isinstance(n, ast.Name)}
    assert named == {"relative"}, named


@pytest.mark.ad19_guarantee
def test_the_implementation_module_is_free_of_the_sdk_entirely(tmp_path):
    """Why the transport is its own module.

    While ``SDKTransport`` lived at the bottom of ``anthropic.py``, the
    no-SDK-import assertion could cover the port, the tier table and the budget
    but not the file that matters, so the offline property there rested on a
    lazy import plus one AST check. Now every module in the package but one is
    provably SDK-free, in a fresh interpreter rather than by reading source.
    """
    script = (
        "import sys, half.model.anthropic\n"
        "assert 'anthropic' not in sys.modules\n"
        "import half.model.anthropic_transport\n"
        "assert 'anthropic' not in sys.modules, "
        "'importing the transport module built a client'\n"
        "print('clean')\n"
    )
    done = _run_python(tmp_path, script)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "clean" in done.stdout


@pytest.mark.ad19_guarantee
def test_the_gate_cannot_run_inside_itself(tmp_path):
    """The fork bomb, closed by a property rather than by a path.

    The first version of this file passed ``--ignore=test_model_offline.py``
    when the file is at ``tests/test_model_offline.py``. The ignore matched
    nothing, the subprocess ran this module again, and each run started another
    — the suite never finished. A path is a spelling; the environment marker is
    what makes the recursion impossible.
    """
    (tmp_path / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    env[GATE_ENV] = "1"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(Path(__file__).resolve())],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    # 5 is pytest's "nothing was collected", which is what a module that skips
    # itself entirely produces. 0 would mean it ran.
    assert done.returncode in (0, 5), done.stdout[-2000:]
    assert "skipped" in done.stdout, done.stdout[-2000:]

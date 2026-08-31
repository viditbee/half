"""Secret detection — one case per shape, plus the failure modes."""

from __future__ import annotations

import pytest

from half.ingest.scrub import ALL_PATTERNS, REDACTION, decode, scrub, scrub_bytes

# Values kept apart from the phrasings that give them meaning. A template
# carries the keyword but no value; a value carries no keyword. Neither half
# trips a pattern on its own, so no tracked file contains a secret-shaped
# literal — which the repository's own AD-11 gate would otherwise flag, along
# with every other scanner anyone points at this repo.
_VALUES = {
    "digits": "483920",
    "dashed": "ABCD-EFGH-IJKL",
    "opaque": "abc123defghijkl",
    "short": "hunter2xyz",
    "b64": "dXNlcjpwYXNz",
}

_TEMPLATES = {
    "one-time code": "Your verification code is {digits}",
    "recovery code": "recovery code: {dashed}",
    "magic link": "https://acme.test/reset?token={opaque}",
    "credential query parameter": "https://x.test/a?auth={opaque}",
    "basic auth in url": "https://user:{short}@internal.test/x",
    "authorization basic": "Authorization: Basic {b64}",
    "plaintext password": "my password is {short}",
}


def _join(*parts: str) -> str:
    return "".join(parts)


SAMPLES = {
    "google oauth refresh token": _join("1/", "/0", "abcdefghijklmnopqrstuvwxyz012345"),
    "google api key": _join("AIza", "0123456789abcdefghijklmnopqrstuvwxy"),
    "bearer/access token field": _join('{"access', '_token": "abc123"}'),
    "client secret field": _join('{"client', '_secret": "shhh"}'),
    "authorization header": _join("Authorization: ", "Bearer abc.def.ghi"),
    "private key block": _join("-----BEGIN ", "RSA PRIVATE KEY-----"),
    "aws access key id": _join("AKIA", "IOSFODNN7EXAMPLE"),
    "anthropic api key": _join("sk-", "ant-", "abcdefghijklmnopqrstuvwxyz0123"),
    "slack token": _join("xoxb-", "1234567890-", "abcdefghij"),
    "github token": _join("ghp_", "abcdefghijklmnopqrstuvwxyz01"),
    "stripe key": _join("sk_", "live_", "abcdefghijklmnop12"),
    "private key body": _join("MII", "A" * 45),
    **{label: text.format(**_VALUES) for label, text in _TEMPLATES.items()},
}


@pytest.mark.parametrize("label", [label for label, _ in ALL_PATTERNS])
def test_every_pattern_has_a_sample_that_trips_it(label):
    """Parametrizing over the tuple fails loudly when a pattern is added
    without a sample — the gap that let seven of eight go unexercised in the
    store's export scanner."""
    assert label in SAMPLES, f"no sample for pattern {label!r}"
    result = scrub(SAMPLES[label])
    assert label in result.labels


@pytest.mark.parametrize("label", sorted(SAMPLES))
def test_the_secret_value_never_survives_redaction(label):
    """Parametrized over labels, not values: a value in a test id ends up in
    pytest's on-disk node-id cache, which is a secret-shaped string written to
    disk by the suite that exists to stop exactly that."""
    result = scrub(SAMPLES[label])
    assert REDACTION.format(label=label) in result.text


def test_ordinary_text_is_untouched():
    assert scrub("lunch at 1pm?").text == "lunch at 1pm?"
    assert scrub("lunch at 1pm?").labels == {}


def test_a_body_that_is_only_a_secret_is_marked_empty():
    assert scrub(SAMPLES["aws access key id"]).empty_after_redaction


def test_a_body_with_surrounding_text_is_not_marked_empty():
    assert not scrub("here is the key " + SAMPLES["aws access key id"]).empty_after_redaction


def test_several_secrets_in_one_body_are_all_removed():
    body = f"{SAMPLES['aws access key id']} and {SAMPLES['anthropic api key']}"
    result = scrub(body)
    assert set(result.labels) == {"aws access key id", "anthropic api key"}


def test_labels_record_kinds_and_counts_never_values():
    result = scrub(f"{SAMPLES['aws access key id']} {SAMPLES['aws access key id']}")
    assert result.labels == {"aws access key id": 2}
    assert all(isinstance(v, int) for v in result.labels.values())


# -- fails closed -------------------------------------------------------------

def test_undecodable_bytes_are_treated_as_a_finding_not_skipped():
    """A single invalid byte must not disable detection for a whole body —
    a credential in a binary blob is exactly the shape a keyring dump takes."""
    result = scrub_bytes(b"\xff\xfe junk " + SAMPLES["aws access key id"].encode())
    assert "undecodable content" in result.labels
    assert result.empty_after_redaction


def test_undecodable_bytes_still_have_their_secrets_detected():
    result = scrub_bytes(b"\xff\xfe " + SAMPLES["aws access key id"].encode())
    assert "aws access key id" in result.labels


def test_clean_utf8_decodes_without_a_finding():
    text, clean = decode("lunch at 1pm?".encode())
    assert clean and text == "lunch at 1pm?"


def test_every_pattern_label_has_a_sample():
    """The parametrized test is generated from ALL_PATTERNS, so deleting a
    pattern removes its case silently. This pins the label set."""
    assert {label for label, _ in ALL_PATTERNS} == set(SAMPLES)

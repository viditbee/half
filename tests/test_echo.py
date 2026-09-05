"""The forward that echoed — containment as the union-find's declared axis.

Story 18. Forwarding an email to yourself crossed CAP-3's admission floor of two
independent supports with **one** message that travelled, because the content
axis is a byte digest and a forward is never byte-identical. The rule that
closes it is containment: a forward *contains* the original, so the forward
declares the original's handle and the two are one voice.

**Every case here names the row it is.** The rows that must fire are cheap to
get right and prove almost nothing on their own; the rows that must *not* fire
are the rule. So the confounds — a shared legal footer, one payment template,
one calendar invite twice — are acceptance criteria here rather than extra
coverage, and the mailbox where every message carries the same footer carries
its own counterexample the way story 17's percolation sweep does.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from half.context.build import runs
from half.derive.particular import MAX_SOURCES
from half.derive.revealed import DOINGS, MIN_INDEPENDENT, Candidate, Run
from half.errors import TokenGrowthLimitError
from half.ingest import echo
from half.ingest.independence import (
    ORIGIN_AXIS,
    SAME_MOMENT_FIELDS,
    independent_groups,
    origin_of,
    unions_the_origin,
)
from half.ingest.scrub import scrub
from half.text import MAX_INPUT_CHARS, MAX_TERMS
from tests.mailshapes import (
    DISCLAIMER,
    FOOTER_LINE,
    REJECTED_FLOOR,
    SEPARATOR,
    forwarded,
    quoted,
    under_a_footer,
)
from tests.test_revealed import SCRIPTS, SECOND_SCRIPTS

TRAVELS = DOINGS[0].label
PAYS = DOINGS[1].label

#: One notice, in nine writing systems. **Not translations of one another** in
#: any way anything reads — nothing on this path knows what language a body is
#: in — but each is a plausible renewal notice in its own script, long enough to
#: be evidence and written the way that script is written.
#:
#: Three of them are scriptio continua (Japanese, Chinese, Thai), three carry
#: combining marks (Devanagari, Arabic, Hebrew), one glues its particles onto
#: the noun (Korean), one is written in Ge'ez syllables (Amharic), and one is
#: the Latin the rest of the suite would have been written in alone.
#:
#: **Amharic is here because it was missing.** ``tests/test_revealed.py``'s
#: ``SCRIPTS`` carries it and this table did not, so every script that file
#: exercises through the reader was exercised against containment *except*
#: Ge'ez — a divergence nothing would have reported.
#: ``test_the_script_fixtures_do_not_diverge`` now holds the two tables to that
#: relationship rather than to whoever edits one of them next.
ORIGINALS: dict[str, str] = {
    "latin":
        "Your subscription to the reading service renews on 1 October for 499 "
        "rupees. The card ending 4242 will be charged automatically on that "
        "date.",
    "japanese":
        "ご購読の更新日は10月1日です。登録のクレジットカードから四百九十九円が自動的に"
        "引き落とされます。変更をご希望の場合は設定画面をご確認ください。",
    "chinese":
        "您的订阅将于十月一日续订，费用为四百九十九元。系统将自动从您登记的银行卡中扣款。"
        "如需更改，请前往设置页面。",
    "thai":
        "การสมัครสมาชิกของคุณจะต่ออายุในวันที่หนึ่งตุลาคมเป็นจำนวนสี่ร้อยเก้าสิบเก้าบาท"
        "ระบบจะหักเงินจากบัตรที่ลงทะเบียนไว้โดยอัตโนมัติ",
    "devanagari":
        "आपकी सदस्यता एक अक्तूबर को नवीनीकृत होगी और चार सौ निन्यानबे रुपये आपके "
        "पंजीकृत कार्ड से स्वतः काट लिए जाएंगे। बदलाव के लिए सेटिंग देखें।",
    "arabic":
        "سيتم تجديد اشتراكك في الأول من أكتوبر بمبلغ أربعمائة وتسعة وتسعين. سيتم "
        "خصم المبلغ تلقائيا من البطاقة المسجلة لديك. لتغيير ذلك يرجى زيارة الإعدادات.",
    "hebrew":
        "המנוי שלך יתחדש באחד באוקטובר בסכום של ארבע מאות תשעים ותשע. הסכום ייגבה "
        "אוטומטית מהכרטיס הרשום אצלך. לשינוי יש להיכנס להגדרות.",
    "korean":
        "구독은 십월 일일에 갱신되며 사백구십구원이 등록된 카드에서 자동으로 결제됩니다. "
        "변경을 원하시면 설정 화면을 확인해 주세요.",
    "amharic":
        "የንባብ አገልግሎት ምዝገባዎ በጥቅምት አንድ ቀን ይታደሳል። አራት መቶ ዘጠና ዘጠኝ ብር "
        "ከተመዘገበው ካርድዎ በራስ ሰር ይቀነሳል። ለመቀየር ቅንብሮችን ይመልከቱ።",
}

#: The scripts with no spaces between words. ``half.context.build.runs`` is
#: whitespace-based, so these are the three the wrong tokenizer would have lost
#: in silence — the whole reason the tokenizer is a case rather than a sentence.
UNSPACED = ("japanese", "chinese", "thai")

#: The scripts whose words carry combining marks, where a tokenizer that treats
#: a matra as a boundary shatters a word into bare consonants.
COMBINING = ("devanagari", "arabic", "hebrew")

#: A run of three consecutive words, concatenated: the split
#: ``half.derive.particular`` uses to catch a quotation, and the one the first
#: draft of story 18 named for this rule. Kept here so the tokenizer choice is
#: pinned by a suite that fails against it rather than by a paragraph.
BY_RUNS = staticmethod(lambda text: runs(text, length=3))


def a_code(*digits: int) -> str:
    """A one-time code, assembled rather than written.

    CAP-13 redacts a code at ingestion, so two cases below need one — and a
    six-digit literal next to the word *code* is precisely what
    ``scan_for_secrets`` looks for, which would make this file a finding in the
    AD-11 gate. Built from separate integers so no run of digits appears in the
    source at all.
    """
    return "".join(str(digit) for digit in digits)


def a_sign_in_notice(code: str, *, browser: str, system: str, city: str) -> str:
    """A security notice of the kind everybody's mailbox is full of."""
    return (f"Your sign-in verification code is {code}. It expires in ten "
            f"minutes. Requested from {browser} on {system} in {city}.")


def a_run(*bodies: str, label: str = TRAVELS, hold: bool = True) -> Run:
    """A run with one candidate per body, through the shipped path.

    Each body is asked for its declaration **before** its candidate is built and
    held **after**, which is the order ``Revealed.observe`` uses and the order
    the whole rule depends on: a key derived after ``add`` lands where nothing
    counts it.
    """
    run = Run()
    for index, body in enumerate(bodies):
        scrubbed = scrub(body)
        candidate = Candidate(
            label=label, source_id=f"m{index}", thread_id=f"t{index}",
            sender=f"p{index}@x", digest=f"d{index}",
            independence_key=run.declares(label, scrubbed),
        )
        run.add(candidate)
        if hold:
            run.hold(candidate, scrubbed)
    return run


def voices(run: Run, label: str = TRAVELS) -> int:
    """What the union-find makes of everything gathered for ``label``."""
    return independent_groups(
        candidate.identity() for candidate in run.supports(label)
    )


# ═════════════════════════════════════════════════════════════════════════════
# the rows that must fire
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_a_forward_is_one_voice():
    """**Matrix row one: the defect.** The original is held, its forward
    arrives, and they are one support rather than two.

    Two things at once, and both matter. The count is one — so CAP-3's floor is
    not crossed — and ``ready`` is ``False``, so the run does not pay for a
    generation over a group that is one message that travelled.
    """
    original = ORIGINALS["latin"]
    run = a_run(original, forwarded(original))
    assert voices(run) == 1, "a forward was counted as a second support"
    assert not run.ready(TRAVELS), (
        "a label crossed the admission floor on one message and its forward"
    )
    assert MIN_INDEPENDENT == 2, "the floor this case is written against moved"


@pytest.mark.cap3_axes
def test_a_reply_quoting_in_full_is_one_voice():
    """**Matrix row two: the same echo, arriving as a reply.**

    A quoted reply carries the original under ``>`` prefixes. Those are not
    terms, so the original's words are contiguous inside the reply exactly as
    they are inside a forward — the rule needs no knowledge of quoting syntax,
    which is what keeps it from becoming a list of mail-client conventions.
    """
    original = ORIGINALS["latin"]
    run = a_run(original, quoted(original))
    assert voices(run) == 1
    assert not run.ready(TRAVELS)


@pytest.mark.cap3_axes
def test_a_forward_carrying_a_footer_is_one_voice():
    """**Matrix row three: wrapping is still containment.** The forward adds a
    separator in front and a long legal footer behind, and the original is still
    inside it, in order and untouched."""
    original = ORIGINALS["latin"]
    wrapped = forwarded(original) + "\n\n" + DISCLAIMER
    run = a_run(original, wrapped)
    assert voices(run) == 1
    assert not run.ready(TRAVELS)


@pytest.mark.cap3_axes
def test_a_chain_of_forwards_is_one_voice_in_any_order():
    """**Matrix row six: containment is transitive, and that is the argument.**

    A inside B inside C. Story 17 measured the *sender* percolating a mailbox
    into one group precisely because union-find is transitive across axes; the
    defence of this axis is that containment chains only with itself, and a
    chain of containments is a genuine chain of derivation.

    Asserted in every arrival order, because the arriving source is the one that
    adopts: a rule that only worked when the original came first would be a rule
    about mailbox ordering.
    """
    a = ORIGINALS["latin"]
    b = forwarded(a)
    c = "Passing this on again." + SEPARATOR + b
    orders = [(a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)]
    for order in orders:
        run = a_run(*order)
        assert voices(run) == 1, f"a chain of forwards split in order {order[0][:12]!r}"
        keys = {candidate.independence_key
                for candidate in run.supports(TRAVELS)}
        assert len(keys) == 1, "one chain of derivation declared two handles"


@pytest.mark.cap3_axes
@pytest.mark.parametrize("script", sorted(ORIGINALS))
def test_a_forward_is_one_voice_in_every_script(script):
    """**Matrix rows nine and ten: Half ships worldwide.**

    Nine writing systems, each with its original and its forward, and each one
    voice. Three are scriptio continua and three carry combining marks; a rule
    green on Latin alone would be dead for a large share of the world and
    nothing would say so.
    """
    original = ORIGINALS[script]
    assert voices(a_run(original, forwarded(original))) == 1
    assert voices(a_run(original, quoted(original))) == 1


@pytest.mark.cap3_axes
def test_two_identical_bodies_are_one_voice_however_the_digest_differs():
    """A byte digest is defeated by one invisible character; containment is not.

    The same notice twice with a zero-width space glued to the second — two
    different digests, two different threads, two different senders, and one
    voice. This is the shape ``tests/test_revealed.py``'s script case used to
    rely on for its *two* supports, which is why that fixture changed rather
    than this rule.
    """
    original = ORIGINALS["latin"]
    run = a_run(original, original + "​")
    assert voices(run) == 1


# ═════════════════════════════════════════════════════════════════════════════
# the rows that must not fire — the rule
# ═════════════════════════════════════════════════════════════════════════════


#: Pairs that share a great deal and are **not** the same evidence, each with
#: **the fraction of the smaller body's vocabulary that appears in the larger,
#: as a number in the row**.
#:
#: That fraction is the measurement which **rejected** a fractional rule, and it
#: is data here rather than a memory — which it was not until a review pointed
#: out that this docstring quoted a range no row carried and that
#: ``echo.overlap`` was never called from anywhere. Every true positive above
#: sits at exactly 1.00; these sit from 0.38 to 0.93, and the rejected floor of
#: 0.98 sat two points above the highest of them, which is what looked like
#: room. ``test_the_fractional_rule_this_one_replaced_fires_on_the_confound``
#: carries the row that goes *over* that floor, and the sweep in
#: ``tools/percolation_sim.py`` is what settled it.
#:
#: The scores are asserted to two decimal places, so a fixture edited until it
#: no longer shares a vocabulary stops being a confound loudly rather than
#: quietly becoming a pair of unrelated sentences that any rule would separate.
CONFOUNDS: tuple[tuple[str, float, str, str], ...] = (
    (
        "two one-line notes under one long legal footer", 0.93,
        "Can you send me the offsite deck before Thursday?\n\n" + DISCLAIMER,
        "The invoice for August has been approved by finance.\n\n" + DISCLAIMER,
    ),
    (
        "two payment receipts on one template", 0.89,
        "Receipt from Acme Cloud. Amount paid 1,200.00 INR. Date 3 August "
        "2026. Invoice number INV-4471. Payment method Visa ending 4242. "
        "Thank you for your business.",
        "Receipt from Acme Cloud. Amount paid 1,450.00 INR. Date 3 September "
        "2026. Invoice number INV-4788. Payment method Visa ending 4242. "
        "Thank you for your business.",
    ),
    (
        "a calendar invite and its update", 0.80,
        "Invitation: Quarterly planning review. Wednesday 9 September 2026 at "
        "14:00 IST. Location Meeting room 3. Organiser Priya Nair. Please "
        "respond yes no or maybe.",
        "Updated invitation: Quarterly planning review. Thursday 10 September "
        "2026 at 16:00 IST. Location Meeting room 5. Organiser Priya Nair. "
        "Please respond yes no or maybe.",
    ),
    (
        # **The codes are deliberately not spelled here.** CAP-13 redacts a
        # one-time code at ingestion, so by the time this rule sees the body the
        # code is gone and what has to keep two security notices apart is
        # everything around it — which is also why this file carries no
        # code-shaped literal for the secret gate to find.
        #
        # **And that is exactly why this row is not the whole of the shape.**
        # It varies the browser, the operating system and the city, so it is the
        # case where something *does* survive the redaction. Logging in twice
        # from one machine leaves nothing that differs, and
        # ``test_two_sign_in_notices_from_one_machine_are_one_voice_after_
        # redaction`` is that case, pinned as a limit rather than as a pass.
        "a sign-in notice, twice", 0.83,
        "Your verification code is in the box below. It expires in ten "
        "minutes. Requested from Chrome on Windows in Pune.",
        "Your verification code is in the box below. It expires in ten "
        "minutes. Requested from Safari on macOS in Jakarta.",
    ),
    (
        "two shipping notices on one template", 0.90,
        "Your order has shipped. Tracking number 1Z9993A. Estimated delivery "
        "12 September. Carrier Bluedart. Track your parcel from the orders page.",
        "Your order has shipped. Tracking number 4K1180B. Estimated delivery "
        "19 September. Carrier Bluedart. Track your parcel from the orders page.",
    ),
    (
        "two unrelated Thai messages", 0.50,
        "เที่ยวบินไปโตเกียวของคุณได้รับการยืนยันแล้วกรุณาเช็คอินล่วงหน้าสองชั่วโมง",
        "การสมัครสมาชิกของคุณจะต่ออายุในวันที่หนึ่งตุลาคมเป็นจำนวนสี่ร้อยเก้าสิบเก้าบาท",
    ),
    (
        "an airline and a hotel, one trip", 0.38,
        "Your flight to Delhi is confirmed. Confirmation ABC123. Departure "
        "14 September at 06:20 from Terminal 2.",
        "Reservation confirmed at the Taj Palace, New Delhi. Two nights, "
        "14 to 16 September. Booking XYZ789.",
    ),
)


@pytest.mark.cap3_axes
@pytest.mark.parametrize("name,score,one,other",
                         CONFOUNDS, ids=[row[0] for row in CONFOUNDS])
def test_a_confound_stays_two_voices(name, score, one, other):
    """**Matrix rows four and five: the cases the rule must not catch.**

    A rule like this is normally justified by what it catches. What matters is
    what it must *not*, and these are the shapes a real mailbox is full of: one
    company footer, one payment template, one calendar invite edited, one
    security code sent twice. Every one of them shares most of its words with
    its partner and none of them is the same evidence.

    **Both halves read the scrubber's output**, which they did not until a
    review noticed: ``an_echo`` was asked about the raw strings while ``voices``
    went through ``a_run``, which scrubs. So the unit half and the end-to-end
    half were comparing two different texts, and a redaction that collapsed a
    pair would have shown up in one of them and not the other — which is the
    shape of the sign-in defect recorded beside this table.
    """
    mine, theirs = scrub(one).text, scrub(other).text
    assert round(echo.overlap(mine, theirs), 2) == score, (
        f"{name} scores {echo.overlap(mine, theirs):.2f} rather than {score}; "
        "the fixture has drifted and the row no longer measures what it says"
    )
    assert not echo.an_echo(mine, theirs), f"{name} collapsed into one voice"
    assert voices(a_run(one, other)) == 2, f"{name} counted as one support"


@pytest.mark.cap3_axes
def test_the_fractional_rule_this_one_replaced_fires_on_the_confound():
    """**The rejected rule, carrying its own counterexample.**

    Story 18 was specified as containment scored *as a fraction of the smaller
    body's vocabulary*, above a floor of 0.98. This case is why it is not: the
    disclaimer confound climbs over that floor as soon as the notes under the
    footer are short, which is what a note under a footer usually is.

    Asserted by number rather than described, so that a future edit reintroducing
    a fractional floor has to delete a red case rather than a paragraph.
    """
    one = "Approved.\n\n" + DISCLAIMER
    other = "Declined.\n\n" + DISCLAIMER
    assert echo.overlap(one, other) > REJECTED_FLOOR, (
        "the confound this rule was rejected over no longer clears the floor "
        "it was rejected for clearing; the fixture has drifted"
    )
    assert not echo.an_echo(one, other), (
        "two unrelated one-line notes under one legal footer are one voice — "
        "the rule has become a similarity rule"
    )
    assert voices(a_run(one, other)) == 2


@pytest.mark.cap3_axes
def test_a_mailbox_under_one_disclaimer_counts_every_message():
    """**The outage case, and the acceptance criterion story 17 taught.**

    Forty unrelated messages, each with the same long legal footer, each from a
    different person in a different thread. The truth is forty supports. A rule
    that scored similarity returns a handful, and a handful below two is not
    restraint — it is Half going quiet everywhere and looking well-behaved while
    it does.

    The sweep in ``tools/percolation_sim.py`` runs this to a thousand messages
    and to every pair compared. This is the floor under it.

    **It ran with the holding turned off and therefore proved nothing.** The
    call used to pass ``hold=False``, so ``Run._texts`` was never filled,
    ``echo.declaring`` was handed an empty window on every message, and every
    key was ``own_key`` by construction — rebinding ``echo.inside`` to return
    ``True`` unconditionally left this case green. The holding is on now and the
    claim is true: forty voices and forty handles.
    """
    mail = [under_a_footer(i, i % 28 + 1) for i in range(40)]
    run = a_run(*mail)
    keys = {candidate.independence_key for candidate in run.supports(TRAVELS)}
    assert len(keys) == len(mail), (
        f"{len(mail)} strangers under one footer declared {len(keys)} handles"
    )
    assert voices(run) == len(mail), (
        "a shared legal footer collapsed a mailbox of strangers, which is the "
        "percolation this axis was measured to avoid"
    )


@pytest.mark.cap3_axes
def test_an_empty_body_is_its_own_voice_and_never_a_match():
    """**Matrix row eleven: empty must not match empty.**

    Vacuously, nothing is contained in nothing, and a rule that answered
    otherwise would make every unreadable body in a mailbox one support.

    **The end-to-end half is built the way a body actually arrives.**
    ``Revealed.observe`` refuses a blank body upstream, so three candidates
    built from three empty strings is a state the reader never reaches and a
    case resting on it is measuring something that cannot happen. The bodies
    here are readable and *distinct*; what makes them stand alone is the empty
    handle, which is asserted rather than assumed, and the empty bodies are kept
    for the unit half where they belong.
    """
    assert echo.own_key("") == "", "an empty body declared a handle"
    assert not echo.an_echo("", "")
    assert not echo.inside((), ()), "two empty sequences sat inside each other"
    assert not echo.inside((), ("a", "b"))
    assert not echo.an_echo("", ORIGINALS["latin"])
    # Three real bodies, each too short to declare anything: the shape the
    # union-find has to keep apart, reached the way the reader would reach it.
    run = a_run("Thanks!", "Noted, ta.", "Will do.")
    assert all(candidate.independence_key == ""
               for candidate in run.supports(TRAVELS)), (
        "a body below MIN_TERMS declared a handle, so the case below is "
        "measuring three handles rather than three absences"
    )
    assert voices(run) == 3


@pytest.mark.cap3_axes
def test_a_very_short_body_stands_for_itself():
    """**Matrix row twelve: below a length the rule declines.**

    *"See you there"* sits entirely inside *"see you there tomorrow at nine"*,
    which is total containment of something that is evidence of nothing. The
    floor is on the body rather than on the score, so it cannot be argued down
    by a fixture.

    **The bound asserted is the fixture's own.** This case used to assert
    ``MIN_TERMS >= 2``, which is the import-time guard rather than anything this
    fixture depends on: the longer body here has six distinct terms, so the case
    is green only while ``4 < MIN_TERMS <= 6``. Raising the floor to seven would
    leave it passing for the wrong reason and lowering it to five would leave it
    failing with a message about the wrong thing. Both ends are stated.
    """
    shorter, longer = "See you there", "See you there tomorrow at nine"
    assert len(frozenset(echo.units(shorter))) == 3
    assert len(frozenset(echo.units(longer))) == 6
    assert 4 < echo.MIN_TERMS <= 6, (
        f"MIN_TERMS is {echo.MIN_TERMS}; this fixture only demonstrates the "
        "floor while the longer body clears it and the shorter one does not"
    )
    assert not echo.an_echo(shorter, longer)
    assert echo.own_key("Thanks!") == ""
    run = a_run(shorter, longer)
    assert voices(run) == 2


# ═════════════════════════════════════════════════════════════════════════════
# the limits, asserted as limits
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_a_forward_past_the_held_ceiling_is_not_caught():
    """**Matrix row seven: a stated limit, not a silent gap.**

    The comparison is against the bodies still in hand, which ``MAX_SOURCES``
    caps at eight. An original that fell outside that window is not there to be
    matched, and its forward is a second support. Catching it needs a sketch per
    source compared against every candidate, which is all-pairs over a mailbox
    and collides with story 9d — so the residue is recorded rather than closed.

    Asserted so the limit is a measured boundary and not a hope: the same pair
    with the window free is one voice, and the *only* difference between the two
    halves of this case is how much unrelated mail arrived first.
    """
    original = ORIGINALS["latin"]
    filler = [f"Unrelated message {i} about item {i} on day {i + 1}, with "
              f"nothing whatever to do with any subscription notice."
              for i in range(MAX_SOURCES)]
    beyond = a_run(*filler, original, forwarded(original))
    assert beyond.holding == MAX_SOURCES, "the ceiling this case rests on moved"
    assert voices(beyond) == len(filler) + 2, (
        "a forward whose original never reached the window was collapsed "
        "anyway, so something is comparing outside the bound"
    )
    within = a_run(*filler[:2], original, forwarded(original))
    assert voices(within) == 3, (
        "the same pair inside the window is not one voice, so the case above "
        "is measuring the wrong thing"
    )


@pytest.mark.cap3_axes
def test_a_forward_read_under_another_label_is_not_caught():
    """**Matrix row eight: a stated limit.**

    Held text is kept per label, because that is the group a claim is generated
    over. An original read as *travels* and its forward read as *pays for a
    subscription* are never compared — and they are also never counted together,
    since a claim's support set is its own label's. The limit is real and its
    consequence is bounded.

    **Asserted against the answer the same pair gives under one label**, because
    *"one voice per label"* is trivially true when a label holds one candidate:
    that half of this case was green for any rule whatever, including one that
    never ran. What has to be shown is that the forward declared **its own**
    handle here and the original's under a single label — the same two bodies,
    the only difference being which label read them.
    """
    original = ORIGINALS["latin"]
    forward = forwarded(original)
    run = Run()
    for label, body in ((TRAVELS, original), (PAYS, forward)):
        scrubbed = scrub(body)
        candidate = Candidate(
            label=label, source_id=f"m_{label}", thread_id=f"t_{label}",
            sender=f"{label}@x", digest=f"d_{label}",
            independence_key=run.declares(label, scrubbed),
        )
        run.add(candidate)
        run.hold(candidate, scrubbed)
    declared = {label: run.supports(label)[0].independence_key
                for label in (TRAVELS, PAYS)}
    assert len(set(declared.values())) == 2, (
        "a body was compared against another label's held text"
    )
    assert declared[TRAVELS] == echo.own_key(scrub(original).text)
    assert declared[PAYS] == echo.own_key(scrub(forward).text), (
        "the forward adopted something; under its own label it must declare "
        "its own handle, because the original was never in its window"
    )
    # The same two bodies under one label: one voice, one handle, and the
    # forward carrying the *original's*. That is the only difference.
    together = a_run(original, forward)
    assert voices(together) == 1
    assert {c.independence_key for c in together.supports(TRAVELS)} == {
        echo.own_key(scrub(original).text)
    }


# ═════════════════════════════════════════════════════════════════════════════
# the tokenizer, pinned by the scripts it saves
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_structure
def test_the_worldwide_suite_fails_against_the_whitespace_tokenizer():
    """**The tokenizer is the story, and this is the case that says so.**

    The first draft of story 18 named ``half.context.build.runs``, which is
    whitespace-based. Run the same nine-script suite against it and Japanese,
    Chinese and Thai return *no match at all* for a forward that contains its
    original verbatim, because scriptio continua arrives as one enormous word
    and a run of three words is the whole message.

    That build would have shipped green, passed a Latin test suite, and been
    dead for a large share of the world. So the choice is pinned by a suite that
    fails against the wrong tokenizer rather than by a comment saying it would.
    """
    lost = []
    for script, original in ORIGINALS.items():
        with_terms = echo.an_echo(original, forwarded(original))
        with_runs = echo.an_echo(original, forwarded(original),
                                 split=BY_RUNS.__func__)
        assert with_terms, f"the shipped tokenizer lost {script}"
        if not with_runs:
            lost.append(script)
    assert set(lost) == set(UNSPACED), (
        f"the whitespace tokenizer lost {sorted(lost)}; the suite is supposed "
        f"to fail on exactly {sorted(UNSPACED)}, and a suite that no longer "
        "fails against the wrong tokenizer has stopped pinning the right one"
    )


@pytest.mark.cap3_structure
def test_a_word_keeps_its_marks_and_a_run_is_cut_into_clusters():
    """The tokenizer this rule takes is the one that got scripts right, and the
    two properties it was chosen for are asserted here rather than assumed.

    A Devanagari word keeps its matras — the earlier tokenizer shattered
    ``यात्रा`` into three bare consonants that collide with almost anything — and
    an unspaced run is cut into grapheme clusters rather than left whole, which
    is what gives a forward in Thai something to contain.
    """
    assert echo.units("यात्रा") == ("यात्रा",), "a matra became a word boundary"
    thai = echo.units(ORIGINALS["thai"])
    assert len(thai) > 20, "a Thai sentence arrived as one indivisible term"
    assert all(len(term) <= 4 for term in thai), (
        "a scriptio-continua run was not cut into clusters"
    )


# ═════════════════════════════════════════════════════════════════════════════
# the structural rules
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_structure
def test_no_body_and_no_fragment_of_one_travels_in_the_key():
    """**AD-13 and AD-22, as a property of the value rather than of its callers.**

    What leaves this rule is a digest: sixty-four hex characters and nothing
    else, whatever script the body was in and however long it was. So a key in a
    log line, an error, a projection or a fixture's expected output reveals
    neither the content of somebody's mail nor its size.
    """
    hexadecimal = set("0123456789abcdef")
    for script, original in ORIGINALS.items():
        key = echo.own_key(original)
        assert key.startswith(echo.PREFIX), f"{script} produced an unnamespaced key"
        body = key[len(echo.PREFIX):]
        assert len(body) == 64, f"{script} produced an odd key"
        assert set(body) <= hexadecimal, (
            f"{script}'s key carries something that is not a hex digit, so it "
            "is not only a digest"
        )
    # One-way, and the property that makes it so: two bodies differing by a
    # single character share nothing. A key is not a shortened body.
    latin = ORIGINALS["latin"]
    nudged = echo.own_key(latin.replace("499", "500"))[len(echo.PREFIX):]
    plain = echo.own_key(latin)[len(echo.PREFIX):]
    differing = sum(a != b for a, b in zip(nudged, plain))
    assert differing > len(plain) // 2, (
        "one changed number moved only a few characters of the key, so the key "
        "is tracking the body rather than digesting it"
    )
    short, long = ORIGINALS["hebrew"], latin * 3
    assert len(echo.own_key(short)) == len(echo.own_key(long)), (
        "the key's length leaks the body's"
    )


@pytest.mark.cap3_structure
def test_the_comparison_is_bounded_by_the_held_window():
    """**Story 9d's rule stands: no pass over every candidate.**

    ``declaring`` compares against exactly what it is handed and never reaches
    for more, and what it is handed is ``Run``'s held window. Counted rather
    than reasoned about: a split that records every body it was asked to read
    cannot be satisfied by a rule that consulted something the caller did not
    hand it.

    **The structural half reads the syntax tree rather than the source text.**
    It used to assert the literal string ``"for key, text in held"`` inside
    ``inspect.getsource``, which renaming either loop variable turns red for no
    reason and which a rule iterating something else entirely could satisfy by
    keeping the line. What matters is that ``held`` is what is iterated, and
    that is a name in the tree.
    """
    read: list[str] = []

    def counting(text: str) -> list[str]:
        read.append(text)
        return list(text.split())

    held = [(f"k{i}", f"Held body number {i} about item {i} on day {i + 1}.")
            for i in range(MAX_SOURCES)]
    echo.declaring(ORIGINALS["latin"], held, split=counting)
    assert len(read) <= len(held) + 2, (
        f"one declaration read {len(read)} bodies against a window of "
        f"{len(held)}; something is comparing outside the bound"
    )

    # And the window itself is the ceiling, so the two bounds are the same one.
    run = a_run(*[f"Message {i} about item {i}, day {i + 1}, nothing shared "
                  f"with any of the others at all." for i in range(MAX_SOURCES + 4)])
    assert run.holding == MAX_SOURCES, (
        "the run held more bodies than MAX_SOURCES, so the comparison is no "
        "longer bounded by the ceiling this rule leans on"
    )
    tree = ast.parse(inspect.getsource(echo.declaring))
    iterated = {node.iter.id for node in ast.walk(tree)
                if isinstance(node, ast.For) and isinstance(node.iter, ast.Name)}
    assert iterated == {"held"}, (
        f"declaring iterates {sorted(iterated)}; the one thing it may walk is "
        "the window it was handed, and anything else is a second source of "
        "bodies the caller did not bound"
    )


@pytest.mark.cap3_structure
def test_the_run_refuses_a_body_that_is_not_scrubber_output():
    """The second door out of ingestion is typed with the scrubber's own output.

    ``Run.declares`` reads a body, so it takes a ``Scrubbed`` or nothing — the
    same refusal ``Run.hold`` makes and for the same reason: *scrub first* is a
    property of the shape rather than of the call order.
    """
    run = Run()
    assert run.declares(TRAVELS, ORIGINALS["latin"]) == ""
    assert run.declares(TRAVELS, None) == ""
    assert run.declares(TRAVELS, b"bytes") == ""
    assert run.declares(TRAVELS, scrub(ORIGINALS["latin"])).startswith(
        echo.PREFIX
    )


@pytest.mark.cap3_structure
def test_the_key_is_a_constructor_argument_and_nothing_is_mutated():
    """**The third option, taken.**

    One ``Candidate`` instance is handed to ``add`` and then to ``hold``. ``add``
    appends it where ``ready`` and ``admitted`` count; ``hold`` appends it where
    nothing counts. So a ``dataclasses.replace`` inside ``hold`` would leave the
    key in the half nothing reads and the rule would be green and inert, and an
    ``object.__setattr__`` from an external caller would be a new pattern on a
    frozen type.

    The reader asks for the declaration *before* it builds the candidate. Read
    off the syntax tree rather than the behaviour, because the behaviour of the
    two wrong versions is identical to the right one everywhere except in the
    count nobody looks at twice.
    """
    from half.derive import revealed

    tree = ast.parse(Path(revealed.__file__).read_text(encoding="utf-8"))
    built = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "Candidate"]
    assert len(built) == 1, "a second Candidate construction appeared"
    supplied = {keyword.arg for keyword in built[0].keywords}
    assert "independence_key" in supplied, (
        "the declared key is not a constructor argument, so it is being set "
        "somewhere the union-find may not read"
    )
    assert Candidate.__dataclass_params__.frozen
    for method in (revealed.Run.hold, revealed.Run.declares):
        source = inspect.getsource(method)
        assert "replace(" not in source and "__setattr__" not in source, (
            f"{method.__qualname__} rebuilds or mutates a candidate; the key "
            "must be a constructor argument"
        )


@pytest.mark.cap3_structure
def test_the_declared_axis_is_the_one_the_union_find_already_read():
    """No fourth axis, no third level, and the origin left exactly where it is.

    Story 15b left ``independence_key`` as a socket in ``SAME_MOMENT_FIELDS``.
    This story filled it; it did not widen the table, move the origin, or add a
    level. The percolation guard story 17 measured into place must still refuse
    a table that unions on the origin, and must still be looking at the same
    table.
    """
    keys = {key for key, _ in SAME_MOMENT_FIELDS}
    assert keys == {"thread_id", "digest", "independence_key"}
    assert ORIGIN_AXIS == ("sender", "origin")
    assert not unions_the_origin(SAME_MOMENT_FIELDS)
    assert unions_the_origin((*SAME_MOMENT_FIELDS, ORIGIN_AXIS)), (
        "the guard no longer recognises the table that shipped an outage"
    )
    # And the key the rule produces is read at the first level and nowhere else:
    # a declared handle is a statement about the *moment*, and a source controls
    # it, so an origin built from one would be the percolation through a field
    # the sender writes.
    identity = Candidate(label=TRAVELS, source_id="m0", thread_id="t1",
                         sender="", digest="d0",
                         independence_key=echo.own_key(ORIGINALS["latin"])
                         ).identity()[1]
    assert origin_of(identity) is None, "a declared key became an origin"


@pytest.mark.cap3_structure
def test_the_origin_level_is_unchanged_by_this_axis():
    """**Matrix row thirteen: no regression on story 17's level.**

    A shop mailing eight times across eight threads is still one support, and
    eight bodies with no readable sender are still eight. Neither answer may
    move because a content axis arrived beside them.
    """
    bodies = [f"This week: {i} new routes to Delhi from {12 + i},000 rupees. "
              f"Book by Friday and travel before the month is out."
              for i in range(8)]
    newsletter = [
        (f"n{i}", {"thread_id": f"t{i}", "sender": "deals@shop.example",
                   "digest": f"d{i}",
                   "independence_key": echo.own_key(body)})
        for i, body in enumerate(bodies)
    ]
    assert independent_groups(newsletter) == 1, (
        "the newsletter story 17 collapsed is no longer one support"
    )
    blanks = [
        (f"u{i}", {"thread_id": f"t{i}", "sender": "", "digest": f"d{i}",
                   "independence_key": echo.own_key(body)})
        for i, body in enumerate(bodies)
    ]
    assert independent_groups(blanks) == 8, (
        "eight senderless messages stopped standing for themselves"
    )


@pytest.mark.cap3_structure
def test_the_rule_refuses_a_shape_that_would_collapse_a_mailbox():
    """The import-time guards, as raises rather than bare asserts.

    A guarantee ``python -O`` removes is not a guarantee, and both of these are
    one edit away from a rule that either collapses a mailbox or does nothing.
    """
    with pytest.raises(ValueError, match="distinct terms"):
        _guard_with(min_terms=1)
    with pytest.raises(ValueError, match="term boundaries"):
        _guard_with(join="x")
    # **Both halves of the separator guard**, because ``not JOIN`` is a second
    # branch and an empty separator is the shape that would make every body's
    # joined form one indistinguishable run of terms.
    with pytest.raises(ValueError, match="term boundaries"):
        _guard_with(join="")
    assert echo.JOIN == "\x00"
    assert not echo.JOIN.isalnum()
    # And the guards pass on the shipped constants, so the case above is not
    # green for a module that refuses everything — and, since each bypass above
    # is undone the moment it has been read, the module is the shipped one here.
    assert echo.MIN_TERMS == MIN_TERMS_SHIPPED
    echo._check_rule()


#: What ``echo.MIN_TERMS`` is before any case touches it, read at import.
MIN_TERMS_SHIPPED = echo.MIN_TERMS


def _guard_with(*, min_terms: int | None = None, join: str | None = None):
    """Run ``echo``'s own import-time check against a mutated constant.

    **Through ``MonkeyPatch`` rather than by hand, and scoped to this call.**
    ``MIN_TERMS`` and ``JOIN`` are ``Final`` and this rebinds them on the live
    module, which is process-global state: the hand-rolled ``try/finally`` this
    replaced restored it in *this* worker, and under ``pytest-xdist`` or any
    parallel runner the window between the two assignments is a window in which
    another case reads a rule that would collapse a mailbox. The context manager
    is the harness's own record of what was touched and it undoes it on the way
    out, including on the raise this function exists to provoke — so no bypass
    can outlive the ``with`` that asked for it, which the hand-rolled version
    could not promise across a fixture teardown.
    """
    with pytest.MonkeyPatch.context() as patch:
        if min_terms is not None:
            patch.setattr(echo, "MIN_TERMS", min_terms)
        if join is not None:
            patch.setattr(echo, "JOIN", join)
        echo._check_rule()


@pytest.mark.cap3_structure
def test_the_rule_reads_no_clock_no_network_and_writes_no_log():
    """**AD-30 and AD-22.** A fold that reaches this stays pure, and nothing
    here can put a body in a log line because nothing here logs.

    Read off the module's imports rather than its behaviour: a module that
    imports no clock, no socket and no logger cannot grow a call to one without
    this case going red.

    **The second half is structural too, and it was not.** It used to grep the
    whole file — docstrings and comments included — for ``"time."``,
    ``"random"``, ``"logging"`` and ``"open("``, so a sentence saying *"tokenize
    the same body a second time."* turned the module red, and a paragraph
    explaining why the rule reads no clock was itself a violation. It also could
    not see the thing it was for: a call reached through an alias carries none
    of those spellings. So the names are read out of the syntax tree, where a
    docstring is a string and a call is a call.
    """
    from half.ingest import echo as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    allowed = {"__future__", "collections", "typing", "hashlib", "half"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= allowed, f"the rule imports {sorted(imported - allowed)}"

    # Every name the module *uses* as code, however it was bound: a bare name,
    # the root of an attribute chain, and the callee of every call. Nothing
    # inside a string or a comment is here, and an alias cannot hide, because
    # what an alias is bound to is an import and the set above is closed.
    forbidden = {"logging", "logger", "log", "time", "datetime", "random",
                 "open", "requests", "httpx", "socket", "urllib", "print"}
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used.add(root.id)
    assert not (used & forbidden), (
        f"the rule reaches {sorted(used & forbidden)}; nothing here may read a "
        "clock, the network or the log, or a fold that reaches it stops being "
        "pure (AD-30)"
    )


@pytest.mark.cap3_structure
def test_the_same_words_in_a_different_order_are_two_bodies():
    """``half.text.sequence``'s correction, in the one place it would be re-made.

    A body's own handle is a digest of its term **sequence**. *"Prefers Delhi
    over Goa"* and *"prefers Goa over Delhi"* are not one message written twice,
    and a key built from a sorted vocabulary would have said they were.
    """
    one = "The team prefers Delhi over Goa for the autumn offsite this year."
    other = "The team prefers Goa over Delhi for the autumn offsite this year."
    assert set(echo.units(one)) == set(echo.units(other)), (
        "the fixture no longer shares a vocabulary, so it proves nothing"
    )
    assert echo.own_key(one) != echo.own_key(other)
    assert not echo.an_echo(one, other)
    assert voices(a_run(one, other)) == 2


@pytest.mark.cap3_structure
def test_a_body_past_the_tokenizer_ceiling_declines_rather_than_raising():
    """Refusing to compare costs one collapse; raising costs the run its receipts.

    The tokenizer's growth ceilings are an error rather than a truncation, which
    is right for an index and wrong here: a body arriving on the ingestion path
    must never be able to take the run down, and a rule that cannot read a body
    has simply not matched it.
    """
    from half.text import terms

    enormous = "Renewal notice. " * (MAX_INPUT_CHARS // 8)
    with pytest.raises(TokenGrowthLimitError):
        terms(enormous)
    assert echo.units(enormous) == ()
    assert echo.own_key(enormous) == ""
    assert not echo.an_echo(enormous, enormous)
    assert voices(a_run(enormous, enormous[:100])) == 2


# ═════════════════════════════════════════════════════════════════════════════
# the collapse this rule cannot see, pinned as an accepted limit
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_a_shared_block_arriving_as_its_own_message_collapses_the_mailbox():
    """**The known limit, asserted as behaviour rather than left to be found.**

    The module's safety argument is that containment chains only with itself, so
    a chain of containments is a genuine chain of derivation. That covers the
    *chain* shape and only the chain shape. The shape it does not cover is a
    **fan**: A inside B and A inside C, where B and C share nothing but A. Both
    adopt A's handle and the two become one voice.

    A is any block a mailbox repeats, and it only has to arrive as a message of
    its own — which a legal footer, a policy notice or a signature routinely
    does. The three shapes below are measured through the shipped path and the
    numbers are the ones this build produces, not the ones it should.

    **This is a recorded limit and not an xfail.** An xfail says *"we intend to
    fix this"*; four candidate fixes were measured and every one of them inverts
    on a real shape (see the module docstring and ``deferred-work.md``), so what
    is intended is that this stays visible. **The direction of harm is
    merging**: Half under-counts supports and admits *fewer* claims, which is
    the conservative direction and the opposite of the over-claiming defect this
    rule was written to close. A future edit that changes any number here has
    changed the rule and owes an explanation either way.
    """
    note_one = "Can you send me the offsite deck before Thursday?"
    note_two = "The invoice for August has been approved by finance."

    # One: the footer arrives between two notes that carry it. Truth is three.
    trio = a_run(note_one + "\n\n" + DISCLAIMER, DISCLAIMER,
                 note_two + "\n\n" + DISCLAIMER)
    assert voices(trio) == 1, (
        "the footer-only message no longer collapses the two notes around it; "
        "if that is a fix rather than a fixture edit, this case should be "
        "rewritten to assert three and the residue closed"
    )

    # Two: thirty strangers under one footer, and the footer as a message.
    # Where it lands in the arrival order is where the damage stops, because
    # the window it can reach is what it has already been compared against.
    mail = [under_a_footer(i, i % 28 + 1) for i in range(30)]
    assert voices(a_run(DISCLAIMER, *mail)) == 1, "arriving first: truth is 31"
    assert voices(a_run(*mail[:5], DISCLAIMER, *mail[5:])) == 5, (
        "arriving sixth: truth is 31, and five is the five that were already "
        "past it"
    )

    # Three: and it does not need a long footer. Eight distinct terms — one
    # over MIN_TERMS — does the same thing, which is why raising the floor is
    # not the lever it looks like.
    assert len(frozenset(echo.units(FOOTER_LINE))) == 8
    six = [under_a_footer(i, i % 28 + 1, FOOTER_LINE) for i in range(6)]
    assert voices(a_run(FOOTER_LINE, *six)) == 1, "arriving first: truth is 7"
    assert voices(a_run(*six[:3], FOOTER_LINE, *six[3:])) == 3


@pytest.mark.cap3_axes
def test_two_sign_in_notices_from_one_machine_are_one_voice_after_redaction():
    """**A second recorded limit, and CAP-13 is what causes it.**

    ``Run.declares`` compares ``Scrubbed.text``, and the scrubber replaces a
    one-time code with a fixed marker. So two sign-in notices from the same
    browser, the same operating system and the same city are *byte-identical*
    by the time this rule sees them, and collapse to one voice — two genuinely
    separate events counted once.

    The confound row above deliberately varies the browser, the system and the
    city, so it is the case where something survives the redaction and the two
    stay apart. Logging in twice from one machine is the ordinary case and it
    was not covered. It is here now, pinned with its direction: **under-count**,
    which loses a support rather than inventing one.

    Closing it would mean comparing something the scrubber removed, which is the
    one thing CAP-13 exists to prevent. Recorded rather than fixed.
    """
    first = a_sign_in_notice(a_code(4, 8, 1, 9, 2, 3),
                             browser="Chrome", system="Windows", city="Pune")
    again = a_sign_in_notice(a_code(7, 3, 0, 5, 1, 4),
                             browser="Chrome", system="Windows", city="Pune")
    assert first != again, "the fixture no longer differs before redaction"
    mine, theirs = scrub(first), scrub(again)
    assert mine.labels, "the fixture code is no longer redacted at all"
    assert mine.text == theirs.text, (
        "the two notices differ after redaction, so this case is no longer "
        "about the shape it names"
    )
    assert voices(a_run(first, again)) == 1, (
        "two sign-ins from one machine are one voice — a known under-count "
        "caused by the redaction, not by the containment rule"
    )
    # And the other direction still holds: something the redaction leaves
    # behind is enough to keep them apart.
    elsewhere = a_sign_in_notice(a_code(7, 3, 0, 5, 1, 4),
                                 browser="Safari", system="macOS",
                                 city="Jakarta")
    assert voices(a_run(first, elsewhere)) == 2


@pytest.mark.cap3_axes
def test_a_body_containing_two_held_originals_unions_with_only_the_first():
    """**A third recorded limit: ``declaring`` returns on the first match.**

    A digest mail, or a forward of a thread that quotes several messages,
    contains more than one held original. The loop returns the first key it
    matches, so the body joins that original's voice and every other original it
    contains is left standing as a separate support.

    The module's docstring used to call this a shape *"realistic mail does not
    produce"*. Realistic mail produces exactly that. The harm is again
    under-collapsing — the others are left as independent as they already
    were — so the rule is no worse than not existing for them, but the claim
    that it could not happen was false and is now a case.
    """
    first = ORIGINALS["latin"]
    second = ("Your parcel was delivered to the front desk at four o'clock on "
              "Tuesday and signed for by the building manager.")
    digest = ("Today's summary.\n\n" + first + "\n\n" + second)
    run = a_run(first, second, digest)
    assert len(run.supports(TRAVELS)) == 3
    keys = [candidate.independence_key for candidate in run.supports(TRAVELS)]
    assert keys[2] == keys[0], "the digest adopted neither original"
    assert keys[2] != keys[1], (
        "the digest adopted both originals; if the rule now unions with every "
        "match this case should assert one voice and the residue is closed"
    )
    assert voices(run) == 2, (
        "three bodies, one of which contains the other two: the truth is one "
        "voice and the rule returns two, which is the first-match limit"
    )


@pytest.mark.cap3_axes
def test_a_body_arriving_after_its_label_generated_declares_its_own_handle():
    """**The first of ``declares``' three ceilings, asserted rather than
    described.**

    A label that has generated holds no texts, so a forward arriving after its
    original's group was written declares only its own handle and collapses
    nothing. That was documented as behaviour and asserted nowhere — and a
    ceiling nothing asserts is a ceiling that can quietly move.
    """
    original = ORIGINALS["latin"]
    run = Run()
    scrubbed = scrub(original)
    candidate = Candidate(label=TRAVELS, source_id="m0", thread_id="t0",
                          sender="a@x", digest="d0",
                          independence_key=run.declares(TRAVELS, scrubbed))
    run.add(candidate)
    assert run.hold(candidate, scrubbed)
    assert run.holding == 1
    # The label generates, whatever it came to, and drops its texts in the
    # same call. This is the shipped method rather than a reconstruction.
    run.spent(TRAVELS)
    assert run.holding == 0

    forward = scrub(forwarded(original))
    assert run.declares(TRAVELS, forward) == echo.own_key(forward.text), (
        "a body arriving after the generation adopted something, so a text "
        "outlived its label's one generation"
    )
    later = Candidate(label=TRAVELS, source_id="m1", thread_id="t1",
                      sender="b@x", digest="d1",
                      independence_key=run.declares(TRAVELS, forward))
    run.add(later)
    assert not run.hold(later, forward), "a generated label held a body again"
    assert voices(run) == 2, "the ceiling is a second support, by construction"


@pytest.mark.cap3_axes
def test_an_original_displaced_at_the_ceiling_leaves_its_forward_nothing():
    """**The third ceiling, and it is not the same as the second.**

    ``Run.hold`` does not merely refuse at ``MAX_SOURCES`` — it *displaces*, so
    a source that brings independence the held ones do not have makes room by
    evicting one that brings none. An original can therefore be evicted while
    the window is full, and its forward arrives to find nothing to adopt.

    Documented nowhere until a review found it: ``declares``' docstring named
    the generation and the window and stopped there. Asserted as a measured
    boundary rather than a hope, with the *only* difference between the two
    halves being whether the held set had anything redundant to displace.
    """
    original = ORIGINALS["latin"]
    filler = [f"Unrelated message {i} about item {i} on day {i + 1}, with "
              f"nothing whatever to do with any subscription notice."
              for i in range(MAX_SOURCES)]

    def held_then(*, redundant: bool) -> Run:
        """The original, then the filler, then the forward.

        With ``redundant`` the second message shares the original's thread, so
        the held set has something whose removal costs no independence and the
        arriving eighth filler displaces the *original*. Without it every held
        source is already independent, nothing can be displaced, and the
        original stays.
        """
        run = Run()
        bodies = [original, *filler, forwarded(original)]
        for index, body in enumerate(bodies):
            scrubbed = scrub(body)
            thread = "t0" if (redundant and index == 1) else f"t{index}"
            candidate = Candidate(
                label=TRAVELS, source_id=f"m{index}", thread_id=thread,
                sender=f"p{index}@x", digest=f"d{index}",
                independence_key=run.declares(TRAVELS, scrubbed),
            )
            run.add(candidate)
            run.hold(candidate, scrubbed)
        return run

    kept = held_then(redundant=False)
    forward_key = kept.supports(TRAVELS)[-1].independence_key
    assert forward_key == kept.supports(TRAVELS)[0].independence_key, (
        "the original was not in the window at all, so this case is measuring "
        "the ceiling above rather than the displacement"
    )

    evicted = held_then(redundant=True)
    candidates = evicted.supports(TRAVELS)
    assert candidates[-1].independence_key != candidates[0].independence_key, (
        "a forward adopted an original that had been displaced out of the "
        "window; something is comparing against text the run no longer holds"
    )
    assert evicted.holding == MAX_SOURCES


@pytest.mark.cap3_axes
def test_a_forward_still_contains_its_original_after_a_secret_is_redacted():
    """**The rule reads scrubber output, so the redaction has to be stable.**

    CAP-13 rewrites a secret to a fixed marker. A forward carries the original's
    secret inside it, so both bodies are rewritten — and the containment has to
    survive that, or the one shape this module exists for would break on any
    message carrying a code. It does survive, because the marker is a constant
    and the same constant lands in both.

    The counterexample matters as much: the row above shows the same mechanism
    *merging* two notices that differ only in the redacted value. Both are
    properties of the same fixed marker and both belong here.
    """
    original = ("Your subscription renews on 1 October for 499 rupees. Your "
                "verification code is " + a_code(6, 1, 2, 9, 4, 0) +
                " and it expires in ten minutes.")
    mine = scrub(original)
    assert mine.labels, "the fixture no longer carries anything to redact"
    theirs = scrub(forwarded(original))
    assert theirs.labels, "the forward's copy of the secret was not redacted"
    assert echo.an_echo(mine.text, theirs.text), (
        "a forward stopped containing its original once both were scrubbed"
    )
    assert voices(a_run(original, forwarded(original))) == 1


# ═════════════════════════════════════════════════════════════════════════════
# the tokenizer's ceiling, on the shape it actually lands on
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_structure
def test_a_forward_over_the_ceiling_whose_original_fits_is_not_caught():
    """**The asymmetric case, which is the realistic one.**

    ``test_a_body_past_the_tokenizer_ceiling_declines_rather_than_raising``
    hands an oversized body to *both* sides, and that is the shape that does not
    happen. A forward is by construction longer than what it forwards, so the
    real case is the original fitting under ``MAX_INPUT_CHARS`` while its
    forward does not: the rule declines on the forward alone, the forward
    declares its own handle, and story 18's defect comes back for that pair with
    nothing saying so.

    Asserted as a measured boundary — the same original a few hundred characters
    shorter is one voice — so this is the ceiling and not some other refusal.
    """
    paragraph = ("Your subscription to the reading service renews on the first "
                 "of October and the registered card will be charged. ")
    original = (paragraph * 200)[:MAX_INPUT_CHARS - 40]
    assert len(original) < MAX_INPUT_CHARS
    assert len(forwarded(original)) > MAX_INPUT_CHARS, (
        "the forward fits under the ceiling, so this case is not asymmetric"
    )
    assert echo.units(original), "the original does not fit; the fixture drifted"
    assert echo.units(forwarded(original)) == (), (
        "the forward is readable, so nothing declines here"
    )
    assert not echo.an_echo(original, forwarded(original))
    assert voices(a_run(original, forwarded(original))) == 2, (
        "the defect, returning through the ceiling: one message that travelled, "
        "two independent supports"
    )

    # And the same pair inside the ceiling is one voice, which is what makes
    # the two halves differ by length and by nothing else.
    shorter = original[:MAX_INPUT_CHARS // 2]
    assert voices(a_run(shorter, forwarded(shorter))) == 1


@pytest.mark.cap3_structure
def test_the_tokenizer_ceiling_is_lower_for_a_scriptio_continua_body():
    """**Half ships worldwide, so an asymmetric ceiling is not the only
    asymmetry.**

    ``terms`` emits one grapheme cluster per character for a script written
    without word spaces, so an unspaced body reaches ``MAX_TERMS`` long before a
    Latin one of the same length reaches ``MAX_INPUT_CHARS``. Measured rather
    than asserted in prose: an unbroken Japanese, Chinese or Thai body declines
    at 6,001 characters and a Latin one is read at 8,000 — three quarters of the
    length, for the same message written in a different script.

    Nothing here is a bug in the tokenizer; the ceilings are its own and they
    are right for an index. It is recorded because the *consequence* falls
    unevenly, and a rule that quietly does less for three of the world's largest
    writing systems is exactly what this file's tokenizer case exists to refuse.
    """
    from half.text import terms

    latin = "renewal " * (MAX_INPUT_CHARS // 8)
    assert len(latin) == MAX_INPUT_CHARS
    assert len(terms(latin)) < MAX_TERMS, "Latin is bounded by the term count"

    for script, character in (("japanese", "更"), ("thai", "ก")):
        at_the_line = character * MAX_TERMS
        assert len(terms(at_the_line)) == MAX_TERMS, script
        with pytest.raises(TokenGrowthLimitError):
            terms(character * (MAX_TERMS + 1))
        assert echo.units(character * (MAX_TERMS + 1)) == (), script
    # Three quarters, stated as the ratio rather than as two numbers, so a
    # change to either ceiling moves this rather than leaving it stale.
    assert MAX_TERMS / MAX_INPUT_CHARS == 0.75


@pytest.mark.cap3_structure
def test_the_tokenizer_raises_only_the_growth_limit_into_the_ingestion_path():
    """``echo.units`` catches one class, and that has to be all there is.

    A narrow ``except`` is right — a bare ``except Exception`` would swallow a
    genuine defect as though it were an oversized body — but it is only *safe*
    while ``TokenGrowthLimitError`` is the whole of what ``half.text`` can
    raise. Anything else would leave ingestion, and a body that took the run
    down would cost every receipt behind it.

    Read off ``half/text.py``'s syntax tree rather than by trying inputs, since
    no spread of fixtures can show that nothing else is raised.
    """
    from half import text as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    raised = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            call = node.exc
            name = call.func if isinstance(call, ast.Call) else call
            raised.add(name.id if isinstance(name, ast.Name) else ast.dump(name))
    assert raised == {"TokenGrowthLimitError"}, (
        f"half.text raises {sorted(raised)}; echo.units catches only "
        "TokenGrowthLimitError, so anything else reaches the ingestion path"
    )
    # And nothing gets there by another door: every hostile shape answers
    # rather than raising.
    for hostile in ("", " ", "\x00", None, 12, b"bytes", ["a"], "﻿",
                    "a" * (MAX_INPUT_CHARS + 1), "更" * (MAX_TERMS + 1)):
        assert isinstance(echo.units(hostile), tuple)
        assert isinstance(echo.own_key(hostile), str)


# ═════════════════════════════════════════════════════════════════════════════
# the fixtures, held to what they claim
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_structure
def test_the_script_fixtures_do_not_diverge():
    """**Two tables of scripts, and one of them was a superset of the other by
    accident.**

    ``tests/test_revealed.py`` reads five writing systems through the whole
    reader; this file reads eight through the containment rule. Amharic was in
    that five and not in this eight, so Ge'ez — a script with its own syllabary
    and its own word shapes — went through the reader and was never once asked
    whether a forward of it contains its original. Nothing reported that,
    because a fixture that is missing an entry looks exactly like a fixture that
    never had one.

    Held as a relationship rather than by counting: every script the reader
    exercises must also be exercised here, in both directions of the containment
    rule. Adding one there without adding it here is now red.
    """
    assert set(SCRIPTS) <= set(ORIGINALS), (
        f"{sorted(set(SCRIPTS) - set(ORIGINALS))} is read through the reader "
        "and never through the containment rule"
    )
    assert set(SCRIPTS) == set(SECOND_SCRIPTS), (
        "the reader's two script tables have themselves diverged"
    )
    for script in SCRIPTS:
        original = ORIGINALS[script]
        assert echo.an_echo(original, forwarded(original)), script
        assert echo.an_echo(original, quoted(original)), script
        # And the reader's own pair must stay two voices, or its script case
        # would be asserting a collapse rather than two supports.
        assert not echo.an_echo(SCRIPTS[script], SECOND_SCRIPTS[script]), script


@pytest.mark.cap3_structure
def test_the_confounds_are_the_rows_they_claim_to_be():
    """**A count gate cannot tell that these rows survived.**

    ``CONFOUNDS`` is seven *must not fire* cases and they are the acceptance
    criteria of this story — the rows that fire are cheap. A CI floor counts
    collected cases, so seven confounds replaced by seven trivially-separate
    sentence pairs would keep the count and lose the whole of the argument. The
    rows are therefore held to what makes them confounds: they are named, they
    are distinct, and every one of them shares a great deal with its partner
    while being different evidence.
    """
    names = [row[0] for row in CONFOUNDS]
    assert len(names) == len(set(names)) == 7, (
        "the confound table changed size or grew a duplicate id; every row is "
        "a shape a real mailbox has and none of them is spare"
    )
    assert "two one-line notes under one long legal footer" in names, (
        "the row the shipped rule was chosen over is gone"
    )
    for name, score, one, other in CONFOUNDS:
        assert 0.30 < score < 1.0, name
        # A pair that shares almost nothing is not a confound; it is two
        # sentences any rule separates, and a table of those proves nothing.
        assert echo.overlap(scrub(one).text, scrub(other).text) >= 0.35, name
        assert one != other, name
    assert max(score for _, score, _, _ in CONFOUNDS) < REJECTED_FLOOR, (
        "a confound row now clears the rejected fractional floor on its own; "
        "the separate case that carries that row is what should say so"
    )

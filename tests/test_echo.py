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
from collections.abc import Sequence
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
from half.text import MAX_INPUT_CHARS, MAX_TERMS, terms
from tests.mailshapes import (
    DISCLAIMER,
    FOOTER_LINE,
    REJECTED_FLOOR,
    SEPARATOR,
    forwarded,
    quoted,
    under_a_footer,
)
from tests.test_revealed import (
    SCRIPTS,
    SECOND_SCRIPTS,
    a_reader,
    observe,
)
from tests.test_revealed import receipt as a_receipt

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


#: The organisation every sender in a one-company fixture belongs to. A domain
#: rather than an address, because that is what story 19 reads: *three senders
#: at one domain* is the shape a company footer has, and one address repeated
#: would be a different case — story 17's origin level would make those thirty
#: messages one support before this rule was ever asked.
ONE_COMPANY = "corp.example"


#: Domains that host many unrelated people, in the three shapes story 19's
#: matrix names: a webmail provider, an ISP and a university. Two addresses at
#: one of these are two strangers, so a block carried only there says nothing.
A_PROVIDER = "gmail.com"
AN_ISP = "btinternet.com"
A_UNIVERSITY = "cam.ac.uk"

#: A provider the shipped list does not know. The list is incomplete by nature,
#: and this is what that costs, kept as a fixture so the limit is measured
#: against a real absence rather than a hypothetical one.
AN_UNLISTED_PROVIDER = "correo-libre.example"


def a_run(*bodies: str, label: str = TRAVELS, hold: bool = True,
          at: str | None = None, senders: Sequence[str] | None = None,
          classify=echo.travelled) -> Run:
    """A run with one candidate per body, through the shipped path.

    Each body is asked for its declaration **before** its candidate is built and
    held **after**, which is the order ``Revealed.observe`` uses and the order
    the whole rule depends on: a key derived after ``add`` lands where nothing
    counts it.

    **Every body gets its own sender, and since story 19 its own organisation.**
    ``at=None`` puts each message at a domain of its own, which is what a forward
    between two people at two companies looks like and is the state story 19's
    matrix calls *many origins*. ``at=ONE_COMPANY`` puts every sender at one
    domain with a local part of its own — several people at one company, the
    state the matrix calls *one origin*, and the shape a stapled legal footer
    has.

    The senders were ``p<n>@x`` for every fixture in this file before story 19,
    which is *one* organisation: read that way, every forward case here was an
    intra-company forward and the rule would have declined on all of them. The
    distinction was invisible while nothing read the domain, and it is the whole
    of what this rule reads, so it is a parameter rather than a constant.

    ``senders`` names one per body, for the shapes neither default describes —
    a notice crossing two companies while a footer stays inside one of them.

    ``classify`` is threaded through to ``echo.declaring`` so the one case that
    proves the classifier is doing the work runs through ``Run`` rather than
    through a hand-rolled window. The hand-rolled version appended until full
    where ``Run.hold`` *displaces*, so the case that mattered most was the one
    case not measuring the shipped path.
    """
    if senders is not None and (at is not None or len(senders) != len(bodies)):
        raise AssertionError(
            "a_run was given both `senders` and `at`, or a `senders` list of a "
            "different length from the bodies. Either would leave some message "
            "at an origin the case did not choose, and the origin is the whole "
            "of what story 19's rule reads"
        )
    run = Run()
    for index, body in enumerate(bodies):
        scrubbed = scrub(body)
        if senders is not None:
            sender = senders[index]
        else:
            sender = f"p{index}@{at}" if at else f"p{index}@d{index}.example"
        candidate = Candidate(
            label=label, source_id=f"m{index}", thread_id=f"t{index}",
            sender=sender, digest=f"d{index}",
            independence_key=run.declares(label, scrubbed, origin=sender,
                                          classify=classify),
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
    """**Story 18's matrix row one: the defect.** The original is held, its
    forward arrives, and they are one support rather than two.

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
    """**Story 18's matrix row two: the same echo, arriving as a reply.**

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
    """**Story 18's matrix row three: wrapping is still containment.** The
    forward adds a separator in front and a long legal footer behind, and the original is still
    inside it, in order and untouched."""
    original = ORIGINALS["latin"]
    wrapped = forwarded(original) + "\n\n" + DISCLAIMER
    run = a_run(original, wrapped)
    assert voices(run) == 1
    assert not run.ready(TRAVELS)


@pytest.mark.cap3_axes
def test_a_chain_of_forwards_is_one_voice_in_any_order():
    """**Story 18's matrix row six: containment is transitive, and that is the
    argument.**

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
    """**Story 18's matrix rows nine and ten: Half ships worldwide.**

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
    """**Story 18's matrix rows four and five: the cases the rule must not catch.**

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
    """**Story 18's matrix row eleven: empty must not match empty.**

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
    """**Story 18's matrix row twelve: below a length the rule declines.**

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
    """**Story 18's matrix row seven: a stated limit, not a silent gap.**

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
    """**Story 18's matrix row eight: a stated limit.**

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
            sender=f"{label}@d_{label}.example", digest=f"d_{label}",
            independence_key=run.declares(label, scrubbed,
                                          origin=f"{label}@d_{label}.example"),
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
    keeping the line. What matters is that ``held`` is what is walked, and that
    is a name in the tree.

    **Story 19 made the guard's first form too narrow, so it is widened rather
    than dropped.** ``declaring`` now cuts the window into units once, before
    the loop, and walks the cut — otherwise a classification per match would
    re-tokenize the whole window per match and the cost would be quadratic in
    it. So the loop's name is no longer literally ``held``. The rule the guard
    keeps is the one it always meant: *every sequence this function walks comes
    from the window it was handed*. That is strictly more than the old form
    checked, because a comprehension over something else was invisible to it and
    is not invisible now — and it is asserted of ``carrying`` too, which is the
    second function story 19 gave a window to.
    """
    read: list[str] = []

    def counting(text: str) -> list[str]:
        read.append(text)
        return list(text.split())

    held = [(f"k{i}", f"Held body number {i} about item {i} on day {i + 1}.",
             f"p{i}@d{i}.example") for i in range(MAX_SOURCES)]
    echo.declaring(ORIGINALS["latin"], held, origin="me@mine.example",
                   split=counting)
    assert len(read) <= len(held) + 1, (
        f"one declaration read {len(read)} bodies against a window of "
        f"{len(held)}; something is comparing outside the bound, or the window "
        "is being cut more than once per arrival"
    )

    # **And a window every body matches costs the same**, which is the half
    # story 19 could have broken: a classification per match, each re-reading
    # the window, is quadratic in it. One notice and a window of forwards of it.
    read.clear()
    notice = ORIGINALS["latin"]
    carried = [(f"k{i}", f"Passing this on, note {i}." + SEPARATOR + notice,
                f"p{i}@d{i}.example") for i in range(MAX_SOURCES)]
    echo.declaring(notice, carried, origin="me@mine.example", split=counting)
    assert len(read) <= len(carried) + 1, (
        f"a window of {len(carried)} bodies that every one of them matches cost "
        f"{len(read)} readings; the window is being cut once per match"
    )

    # **The joins are bounded too, and that half was never asserted.** The cost
    # line on ``declaring`` has been wrong three times; the third time it
    # counted only tokenizations while ``carrying`` rebuilt both sides of its
    # search for every held body it looked at — up to sixty-four joins on a
    # window of eight that every body matched. Both sides are joined once when
    # the window is cut, so the bound is ``2w + 1``: the cut, the arriving body,
    # and one per *furniture* match, since a travelling match returns.
    def joins(senders, whom) -> int:
        window = [(f"k{i}", f"Passing this on, note {i}." + SEPARATOR + notice,
                   sender) for i, sender in enumerate(senders)]
        counted: list[int] = []
        with pytest.MonkeyPatch.context() as patch:
            real = echo._joined
            patch.setattr(echo, "_joined",
                          lambda written: (counted.append(1), real(written))[1])
            echo.declaring(notice, window, origin=whom)
        return len(counted)

    travelling = joins([f"p{i}@d{i}.example" for i in range(MAX_SOURCES)],
                       "me@elsewhere.example")
    furniture = joins([f"p{i}@{ONE_COMPANY}" for i in range(MAX_SOURCES)],
                      f"me@{ONE_COMPANY}")
    assert travelling == MAX_SOURCES + 2, (
        f"a window of {MAX_SOURCES} whose first match travels cost "
        f"{travelling} joins; it is the cut, the arriving body and one block"
    )
    assert furniture == 2 * MAX_SOURCES + 1, (
        f"a window of {MAX_SOURCES} where every match is furniture cost "
        f"{furniture} joins, not {2 * MAX_SOURCES + 1}; something is rebuilding "
        "a joined form the window already carries"
    )

    # And the window itself is the ceiling, so the two bounds are the same one.
    run = a_run(*[f"Message {i} about item {i}, day {i + 1}, nothing shared "
                  f"with any of the others at all." for i in range(MAX_SOURCES + 4)])
    assert run.holding == MAX_SOURCES, (
        "the run held more bodies than MAX_SOURCES, so the comparison is no "
        "longer bounded by the ceiling this rule leans on"
    )
    for function, window in ((echo.declaring, "held"), (echo.carrying, "window")):
        assert _walks_only(function, window), (
            f"{function.__name__} walks something that did not come from "
            f"{window!r}; the one thing it may read is the window it was "
            "handed, and anything else is a second source of bodies the caller "
            "did not bound"
        )


def _walks_only(function, window: str) -> bool:
    """Whether every sequence ``function`` walks comes from ``window``.

    A ``for`` loop and every comprehension count as walking, because the reason
    the first form of this guard needed widening is that ``declaring`` now reads
    its window in a comprehension — and a guard blind to comprehensions is a
    guard a rewrite walks straight through.

    **Three narrowings a review asked for, each closing a way to pass while
    reading something else.**

    * A name is licensed only by an assignment whose value is a comprehension
      over an already-licensed name **and** whose element expression calls
      nothing but names this module already exposes. Without that,
      ``[fetch_more_bodies(x) for x in held]`` licensed its target and the
      guard said yes to a second source of bodies.
    * Licences are collected in **source order** and a walk may only use a name
      licensed on an earlier line. ``ast.walk`` is breadth-first, so an
      assignment textually *after* a loop used to license it.
    * ``DictComp`` counts on both sides. It was in neither set, so a dict
      comprehension over something else was invisible.

    The structural half is the weaker half and says so: what actually bounds the
    reading is the counting split above, which fails on anything that reaches
    for a body the caller did not hand over, however it spells it.
    """
    from half.ingest import echo as module

    tree = ast.parse(inspect.getsource(function))
    exposed = {name for name in vars(module) if not name.startswith("__")}
    comprehensions = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)

    def source(node) -> str | None:
        """The name a walked iterable came from, or ``None`` if it is not one."""
        return node.id if isinstance(node, ast.Name) else None

    def only_calls_exposed(node) -> bool:
        """Whether the element expression calls nothing this module does not own."""
        return all(
            isinstance(call.func, ast.Name) and call.func.id in exposed
            for call in ast.walk(node) if isinstance(call, ast.Call)
        )

    def element(comprehension):
        return (comprehension.value if isinstance(comprehension, ast.DictComp)
                else comprehension.elt)

    licensed: list[tuple[int, str]] = [(0, window)]
    for node in sorted(ast.walk(tree), key=lambda n: getattr(n, "lineno", 0)):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        value = node.value
        if not isinstance(value, comprehensions):
            continue
        allowed = {name for line, name in licensed if line <= node.lineno}
        drawn = {source(generator.iter) for generator in value.generators}
        if not drawn <= allowed or not only_calls_exposed(element(value)):
            continue
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target])
        for target in targets:
            if source(target) is not None:
                licensed.append((node.lineno, source(target)))

    walked: list[tuple[int, str | None]] = [
        (node.lineno, source(node.iter))
        for node in ast.walk(tree) if isinstance(node, ast.For)
    ]
    walked += [
        (node.lineno, source(generator.iter))
        for node in ast.walk(tree) if isinstance(node, comprehensions)
        for generator in node.generators
    ]
    if not walked:
        return False
    return all(
        name is not None
        and any(line <= at for line, licensed_name in licensed
                if licensed_name == name)
        for at, name in walked
    )


@pytest.mark.cap3_structure
def test_the_window_guard_rejects_the_shapes_it_exists_to_reject():
    """**A guard nothing has ever failed is a guard nobody has tested.**

    ``_walks_only`` reads a syntax tree, and the first version of it said yes to
    three shapes it was written to refuse. So the four shapes are fed to it
    directly here — a comprehension that fetches bodies from somewhere else, a
    licence granted on a line *after* the walk it would license, a dict
    comprehension over an unrelated name, and a plain walk over one — and each
    must come back rejected, with the two shipped functions coming back accepted
    so the predicate is not simply refusing everything.
    """
    holes = {
        "a second source of bodies": (
            "def declaring(body, held, *, origin):\n"
            "    window = [fetch_more_bodies(x) for x in held]\n"
            "    for entry in window:\n        pass\n"
        ),
        "a licence granted after the walk": (
            "def declaring(body, held, *, origin):\n"
            "    for entry in window:\n        pass\n"
            "    window = [x for x in held]\n"
        ),
        "a dict comprehension over something else": (
            "def declaring(body, held, *, origin):\n"
            "    other = {k: v for k, v in somewhere_else}\n"
            "    for entry in other:\n        pass\n"
        ),
        "a walk over an unlicensed name": (
            "def declaring(body, held, *, origin):\n"
            "    for entry in somewhere_else:\n        pass\n"
        ),
    }
    for name, text in holes.items():
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(inspect, "getsource", lambda _f, _t=text: _t)
            assert not _walks_only(object(), "held"), (
                f"the window guard accepts {name}, so a rewrite reading "
                "something the caller never handed over would pass it"
            )
    assert _walks_only(echo.declaring, "held")
    assert _walks_only(echo.carrying, "window")


@pytest.mark.cap3_structure
def test_the_run_refuses_a_body_that_is_not_scrubber_output():
    """The second door out of ingestion is typed with the scrubber's own output.

    ``Run.declares`` reads a body, so it takes a ``Scrubbed`` or nothing — the
    same refusal ``Run.hold`` makes and for the same reason: *scrub first* is a
    property of the shape rather than of the call order.
    """
    run = Run()
    whom = "a@one.example"
    assert run.declares(TRAVELS, ORIGINALS["latin"], origin=whom) == ""
    assert run.declares(TRAVELS, None, origin=whom) == ""
    assert run.declares(TRAVELS, b"bytes", origin=whom) == ""
    assert run.declares(TRAVELS, scrub(ORIGINALS["latin"]),
                        origin=whom).startswith(
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
    """**Story 18's matrix row thirteen: no regression on story 17's level.**

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
# the block that never leaves one company — story 19's rows
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_a_footer_arriving_as_its_own_message_no_longer_collapses_the_mailbox():
    """**A footer alone, then the notes carrying it — and the defect they close.**

    Story 18's safety argument was that containment chains only with itself, so
    a chain of containments is a genuine chain of derivation. That covers the
    *chain* shape and only the chain shape. The shape it did not cover is a
    **fan**: A inside B and A inside C, where B and C share nothing but A. Both
    adopted A's handle and the two became one voice — and A is any block a
    mailbox repeats, needing only to arrive as a message of its own, which a
    legal footer, a policy notice or a signature routinely does.

    **The three shapes below are the ones story 18 measured, with the numbers it
    recorded named beside the ones this build produces**, because the whole
    point of the fix is which of the two you get. Every sender is a different
    person at one company, which is what a stapled footer's carriers are.

    The rule is not about what the block looks like. It is about who carries it:
    a footer never leaves the organisation that staples it, and a forwarded
    original travels between senders, which is what forwarding *is*.
    """
    note_one = "Can you send me the offsite deck before Thursday?"
    note_two = "The invoice for August has been approved by finance."

    # One: the footer arrives between two notes that carry it. Story 18: one.
    trio = a_run(note_one + "\n\n" + DISCLAIMER, DISCLAIMER,
                 note_two + "\n\n" + DISCLAIMER, at=ONE_COMPANY)
    assert voices(trio) == 3, (
        "the footer-only message still collapses the two notes around it; "
        "story 18 counted one voice here and the truth is three"
    )

    # Two: thirty strangers under one footer, and the footer as a message.
    # Story 18: one when it arrives first, five when it arrives sixth — the
    # damage stopping where the block landed in the arrival order.
    mail = [under_a_footer(i, i % 28 + 1) for i in range(30)]
    assert voices(a_run(DISCLAIMER, *mail, at=ONE_COMPANY)) == 31, (
        "arriving first: story 18 counted one voice for thirty-one messages"
    )
    assert voices(a_run(*mail[:5], DISCLAIMER, *mail[5:], at=ONE_COMPANY)) == 31, (
        "arriving sixth: story 18 counted five"
    )

    # Three: and it never needed a long footer. Eight distinct terms — one over
    # MIN_TERMS — did the same thing, which is why raising the floor was never
    # the lever it looked like.
    assert len(frozenset(echo.units(FOOTER_LINE))) == 8
    six = [under_a_footer(i, i % 28 + 1, FOOTER_LINE) for i in range(6)]
    assert voices(a_run(FOOTER_LINE, *six, at=ONE_COMPANY)) == 7, (
        "arriving first: story 18 counted one"
    )
    assert voices(a_run(*six[:3], FOOTER_LINE, *six[3:], at=ONE_COMPANY)) == 7, (
        "mid-stream: story 18 counted three"
    )


@pytest.mark.cap3_axes
def test_the_same_mailbox_collapses_again_with_the_classifier_switched_off():
    """**The mutation guard: this suite must fail without the classifier.**

    A fix that cannot be switched off cannot be shown to be doing anything. The
    classifier is a parameter of ``declaring`` — and, since a review found this
    case rebuilding the window by hand, of ``Run.declares`` and ``a_run`` too —
    for the same reason the tokenizer is one: so a case can run **the shipped
    path** with it disabled and watch story 18's numbers come back.

    *Disabled* means the honest thing: a classifier answering *"it travelled"*
    for every block, which is exactly what story 18 did by never asking.

    **It runs through ``Run`` now, and that is the point of the rewrite.** The
    first version appended to a list until it was full, where ``Run.hold``
    *displaces* — so the one case proving the fix works was the one case not
    measuring the window the product has.
    """
    def always(homes):
        """Story 18's classifier: every block travelled, because none was asked."""
        return True

    mail = [under_a_footer(i, i % 28 + 1) for i in range(30)]
    shipped = a_run(DISCLAIMER, *mail, at=ONE_COMPANY)
    switched_off = a_run(DISCLAIMER, *mail, at=ONE_COMPANY, classify=always)

    def handles(run: Run) -> int:
        return len({c.independence_key for c in run.supports(TRAVELS)})

    assert handles(shipped) == 31
    assert voices(shipped) == 31
    assert handles(switched_off) == 1, (
        "the footer no longer collapses the mailbox even with the classifier "
        "answering yes to everything, so this suite is not measuring the "
        "classifier and would stay green if it were deleted"
    )
    assert voices(switched_off) == 1

    # And the row the classifier must *not* change: a genuine forward across
    # two organisations is one voice either way, so the case above cannot be
    # satisfied by a build that stopped collapsing anything.
    original = ORIGINALS["latin"]
    for rule in (echo.travelled, always):
        pair = a_run(original, forwarded(original), classify=rule,
                     senders=("billing@svc.example", "asst@work.example"))
        assert voices(pair) == 1, "a real forward moved when the classifier did"


@pytest.mark.cap3_axes
def test_one_notice_and_eight_forwards_from_eight_origins_are_one_voice():
    """**The viral forward: the inversion that killed two candidate rules.**

    A viral forward is the shape that inverts a frequency discount and a
    fan-refusal alike: at eight copies of one notice the forwarded body itself
    starts to look like boilerplate, so any rule that fires on *how often a
    block is seen* switches its defence off exactly when the truth is one voice.

    Origin-crossing does not invert on it, because eight carriers at eight
    organisations is the most travelling a block can do. One voice, and the
    ``ready`` half matters as much: the run must not pay for a generation over
    one message that was passed around.
    """
    notice = ORIGINALS["latin"]
    carried = [f"Passing this on, {i}." + SEPARATOR + notice for i in range(8)]
    run = a_run(notice, *carried)
    assert len(run.supports(TRAVELS)) == 9, "nine messages, nine candidates"
    assert voices(run) == 1, (
        "one notice and eight forwards of it from eight organisations counted "
        "as more than one support"
    )
    assert not run.ready(TRAVELS)
    keys = {candidate.independence_key for candidate in run.supports(TRAVELS)}
    assert len(keys) == 1, "one notice being passed on declared nine handles"


@pytest.mark.cap3_axes
def test_an_original_and_several_forwards_of_it_are_one_voice():
    """**An original, then forwards of it — the row story 18 must keep.**

    The plural is the row: two people forward one notice onward, each wrapping
    it differently, and all three are one derivation. It is separate from the
    viral row because eight carriers is a stress shape and two is the ordinary
    one, and a rule can be right about the first while wrong about the second.

    Asserted in two arrival orders, because the arriving body is the one that
    adopts and a rule that only worked when the original came first would be a
    rule about mailbox ordering.

    **The third order is story 18's recorded first-match limit and is asserted
    as one**, so that a reader does not mistake it for a story 19 defect. With
    the original arriving *last*, it is contained in two held forwards that do
    not contain each other, and ``declaring`` returns on the first — leaving the
    second forward standing as its own support. Nothing about the origin is
    involved; see
    ``test_a_body_containing_two_held_originals_unions_with_only_the_first``.
    """
    original = ORIGINALS["latin"]
    one = "FYI, see below." + SEPARATOR + original
    other = "Passing this on." + SEPARATOR + original + "\n\nThanks."
    at = {original: "billing@svc.example", one: "asst@work.example",
          other: "ops@third.example"}
    for order in ((original, one, other), (one, original, other)):
        senders = tuple(at[body] for body in order)
        run = a_run(*order, senders=senders)
        assert voices(run) == 1, f"three forwards split in order {senders}"
        assert len({c.independence_key
                    for c in run.supports(TRAVELS)}) == 1
    last = a_run(one, other, original,
                 senders=tuple(at[body] for body in (one, other, original)))
    assert voices(last) == 2, (
        "the original arriving behind both forwards is story 18's first-match "
        "limit; if it is one voice now that limit is closed and its own case "
        "should say so"
    )


@pytest.mark.cap3_axes
def test_a_forward_and_a_footer_are_two_blocks_classified_apart():
    """**Both blocks present at once, and each classified on its own carriers.**

    A forward wraps the original and the forwarder's own company staples its
    legal footer to it, so one message carries two shared blocks: one that
    travelled between two companies and one that never left the second. The two
    must be classified apart, or a forward carrying a footer would be decided by
    whichever block happened to match first.

    Four messages, and the senders are the whole fixture: the notice comes from
    a billing service, the forward and the two footer-carrying messages all come
    from the company that forwarded it. So the notice's carriers cross an
    organisation and the footer's do not. The truth is **three** voices, which
    is what this asserts — the name of this case used to say *one voice* while
    the body asserted three.
    """
    notice = ORIGINALS["latin"]
    wrapped = forwarded(notice) + "\n\n" + DISCLAIMER
    stapled = ("Reminder: the quarterly return is due on Friday.\n\n"
               + DISCLAIMER)
    run = a_run(notice, wrapped, DISCLAIMER, stapled,
                senders=("billing@svc.example", "asst@work.example",
                         "legal@work.example", "hr@work.example"))
    keys = [candidate.independence_key for candidate in run.supports(TRAVELS)]
    assert keys[1] == keys[0], (
        "the forward stopped adopting the notice once a footer arrived beside "
        "it, so the two blocks are being decided as one"
    )
    assert len({keys[0], keys[2], keys[3]}) == 3, (
        "the footer-only message or the message carrying it adopted something; "
        "a block that never leaves one company is that company's furniture"
    )
    assert voices(run) == 3, (
        "the truth is three voices — the notice and its forward as one, and "
        "the two messages the footer is stapled to standing for themselves"
    )


@pytest.mark.cap3_axes
def test_a_furniture_match_before_a_travelling_one_is_stepped_over():
    """**The step-over, pinned. Returning on the first match is not enough.**

    The window is walked in arrival order, so an ordinary mailbox puts a
    *furniture* match in front of a *travelling* one whenever the footer arrived
    before the mail that carries it — which is what a footer does. A rule that
    returned on the first containment match would hand the forward the footer's
    key and leave the original standing as a second support: the over-claiming
    direction, reached through the ordering rather than through the rule.

    The same four bodies as the case above, reordered so the footer is held
    first. Review demonstrated that replacing the step-over with an
    unconditional early return left the whole suite green; this is the case that
    stops that being true, and it asserts the **key** as well as the count,
    because both orderings happen to answer three voices in some arrangements.
    """
    notice = ORIGINALS["latin"]
    wrapped = forwarded(notice) + "\n\n" + DISCLAIMER
    stapled = ("Reminder: the quarterly return is due on Friday.\n\n"
               + DISCLAIMER)
    run = a_run(DISCLAIMER, notice, wrapped, stapled,
                senders=("legal@work.example", "billing@svc.example",
                         "asst@work.example", "hr@work.example"))
    keys = [candidate.independence_key for candidate in run.supports(TRAVELS)]
    footer_key, notice_key, forward_key, stapled_key = keys
    assert forward_key == notice_key, (
        "the forward adopted the footer it was compared against first instead "
        "of the notice it is actually a forward of; the loop is returning on "
        "the first containment match rather than the first travelling one"
    )
    assert forward_key != footer_key
    assert stapled_key not in {footer_key, notice_key}, (
        "the message the footer is merely stapled to adopted something"
    )
    assert voices(run) == 3, (
        "the truth is three: the notice with its forward, the footer alone, "
        "and the reminder that merely carries the footer"
    )


@pytest.mark.cap3_axes
def test_a_forward_inside_one_company_is_not_caught():
    """**The limit this leaves, and it is the serious one.**

    A forward that never leaves one organisation looks exactly like that
    organisation's furniture, because on the only signal that works it *is* the
    same shape: one block, carriers all at one domain. Half counts it as two
    supports where the truth is one.

    **The direction of harm is OVER-CLAIMING**, which is the direction story 18
    was written to close and the opposite of the residue story 18 left. That
    makes it the more serious of the two and it is recorded here rather than
    buried: a claim can now be admitted on one message that travelled, provided
    it never left the building.

    Asserted against the same two bodies from two organisations, so the only
    difference between one voice and two is who carried them.
    """
    original = ORIGINALS["latin"]
    inside_one = a_run(original, forwarded(original), at=ONE_COMPANY)
    assert voices(inside_one) == 2, (
        "an intra-company forward is one voice again; if that is a fix rather "
        "than a fixture edit, this case should assert one and the residue is "
        "closed"
    )
    assert {c.independence_key for c in inside_one.supports(TRAVELS)} == {
        echo.own_key(scrub(original).text),
        echo.own_key(scrub(forwarded(original)).text),
    }, "the two declared something other than their own handles"

    # The same pair across two organisations: one voice. The bodies are
    # identical; only the senders differ.
    assert voices(a_run(original, forwarded(original))) == 1

    # And it crosses CAP-3's floor, which is what makes it over-claiming rather
    # than merely wrong: two supports is exactly what admits a claim.
    assert MIN_INDEPENDENT == 2
    assert inside_one.ready(TRAVELS), (
        "the intra-company forward no longer crosses the admission floor, so "
        "the direction of this residue is not what this case says it is"
    )


# ═════════════════════════════════════════════════════════════════════════════
# a domain is not an organisation — the regression review measured
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
@pytest.mark.parametrize("place", [A_PROVIDER, AN_ISP, A_UNIVERSITY],
                         ids=["webmail", "an ISP", "a university"])
def test_a_forward_between_two_people_at_one_provider_is_one_voice(place):
    """**The regression review found, and it must not come back.**

    Two people at ``gmail.com`` are not one company. The first build of this
    rule read any domain as an organisation, so an ordinary forward between two
    such addresses was that "organisation's" furniture, refused to collapse, and
    became **two supports from one message** — story 18's over-claiming defect,
    handed back for what is plausibly the commonest sender population in a
    personal mailbox. Measured then: ``gmail.com`` 2 voices, ``outlook.com`` 2,
    one university 2, where the truth is 1.

    A webmail provider, an ISP and a university are the same shape for this
    rule: many unrelated people at one domain, so a block carried only there has
    been shown to stay nowhere and the rule declines — which is story 18's
    answer and the merging direction.

    **The control is in the case rather than in a sibling**, because a build
    that declined on everything would pass the row above and fail the product:
    the same two bodies at one *company* still count as two, which is the
    recorded limit and the proof that this row is a discrimination and not a
    switch-off.
    """
    original = ORIGINALS["latin"]
    together = a_run(original, forwarded(original),
                     senders=(f"alice@{place}", f"bob@{place}"))
    assert voices(together) == 1, (
        f"a forward between two people at {place} counted as two supports; a "
        "domain that hosts many unrelated people is not an organisation"
    )
    assert len({c.independence_key
                for c in together.supports(TRAVELS)}) == 1
    assert not together.ready(TRAVELS), (
        "one message that travelled crossed CAP-3's admission floor"
    )

    # The control: one company, the same two bodies, still two — so this row
    # cannot be passed by a rule that declines everywhere.
    assert voices(a_run(original, forwarded(original), at=ONE_COMPANY)) == 2


@pytest.mark.cap3_axes
def test_a_forward_on_a_provider_absent_from_the_list_is_not_caught():
    """**What the list's incompleteness costs, pinned as a limit.**

    ``SHARED_DOMAINS`` cannot be complete — there is no register of every
    webmail provider, ISP and workplace-shaped domain on earth — so a forward
    between two people at a provider it does not know is read as an
    intra-company forward and counts as two supports.

    **The direction is OVER-CLAIMING**, the same as the intra-company limit and
    for the same reason: it is that limit, reached through a gap in the data
    rather than through the rule. It is recorded rather than hidden, and it is
    the reason the list leans permissive: a domain wrongly *on* it merely
    merges, and merging is the side to be wrong on.

    Asserted with the same pair at a **listed** provider as the control, so the
    case says which of the two things it is measuring.
    """
    original = ORIGINALS["latin"]
    assert not echo.shared(AN_UNLISTED_PROVIDER), (
        "the fixture provider is on the list now; pick one that is not, or the "
        "case has stopped measuring the incompleteness"
    )
    unlisted = a_run(original, forwarded(original),
                     senders=(f"alice@{AN_UNLISTED_PROVIDER}",
                              f"bob@{AN_UNLISTED_PROVIDER}"))
    assert voices(unlisted) == 2, (
        "a forward on an unlisted provider is one voice; if the list grew to "
        "cover it, pick another absent one — this residue closes only when the "
        "rule stops depending on a list"
    )
    assert unlisted.ready(TRAVELS), "the direction of this residue is not over-claiming"

    listed = a_run(original, forwarded(original),
                   senders=(f"alice@{A_PROVIDER}", f"bob@{A_PROVIDER}"))
    assert voices(listed) == 1, (
        "the control is failing, so the case above is measuring the rule "
        "rather than the list"
    )


@pytest.mark.cap3_structure
def test_the_shared_list_is_worldwide_and_names_origins_and_never_text():
    """**The Never list forbids a pattern list for *text*, and this is not one.**

    A disclaimer, a separator, a quote marker and a signature exist in every
    language, and matching them is the failure this whole approach was chosen to
    avoid. ``gmail.com`` is a fact about the world and is spelled ``gmail.com``
    in every language on earth. So the entries are asserted to be domains and
    nothing else — no spaces, no scripts, no words — which is the property that
    makes the list data rather than a rule about language.

    **And it is asserted to be worldwide**, because a list of Western providers
    alone would be its own defect: Half ships everywhere, and a rule that only
    knows ``gmail.com`` and ``yahoo.com`` leaves the commonest sender population
    of most of the world reading as a company.
    """
    for entry in echo.SHARED_DOMAINS:
        assert entry == entry.strip().lower(), entry
        assert " " not in entry and echo.AT not in entry, entry
        assert echo.DOT in entry, entry
        assert echo._a_domain(entry), entry
    # A provider from each of the regions the spec names, so that deleting a
    # continent's worth of entries fails rather than passes quietly.
    for region, provider in (
        ("China", "qq.com"), ("Korea", "naver.com"), ("Japan", "nifty.com"),
        ("Russia", "mail.ru"), ("Germany", "web.de"), ("France", "orange.fr"),
        ("Italy", "libero.it"), ("Czechia", "seznam.cz"), ("Poland", "wp.pl"),
        ("Brazil", "uol.com.br"), ("India", "rediffmail.com"),
        ("South Africa", "webmail.co.za"), ("Australia", "bigpond.com"),
        ("the Emirates", "emirates.net.ae"), ("Israel", "walla.co.il"),
    ):
        assert echo.shared(provider), (
            f"{provider} ({region}) is no longer read as a shared domain; a "
            "list that only knows the West is a rule that works for the West"
        )


@pytest.mark.cap3_structure
def test_a_family_of_country_variants_is_matched_without_enumerating_it():
    """**The country-variant rule, and the cost of it, both asserted.**

    ``hotmail`` and ``yahoo`` ship a domain per country and nobody will keep a
    list of them current — and a missing entry is the over-claiming direction.
    So the family is matched on its first label and the country part is not read
    at all, which also covers a subdomain of one.

    The cost is real and is asserted rather than left as a footnote: a company
    whose domain *begins* with one of those labels reads as shared and declines.
    That is the merging direction, which is the side to be wrong on, and a
    future edit that narrows the rule owes an answer for the country variants.
    """
    for variant in ("hotmail.co.uk", "hotmail.fr", "yahoo.co.jp",
                    "yahoo.com.br", "yahoo.com.tr", "outlook.de",
                    "live.co.uk", "mail.yahoo.com", "gmx.at"):
        assert echo.shared(variant), variant
    # The academic shape, in the three spellings it takes worldwide.
    for campus in ("mit.edu", "cs.stanford.edu", "cam.ac.uk", "u-tokyo.ac.jp",
                   "usp.edu.br", "iitb.ac.in", "univie.ac.at"):
        assert echo.shared(campus), campus
    # And what the shape must not swallow: an ordinary company, a top level on
    # its own, and a domain that merely contains the letters.
    for company in ("corp.example", "acme.co", "edu.example", "ac.example",
                    "education.example", "yahoo-partners.example"):
        assert not echo.shared(company), company
    # The stated cost, pinned so it is a decision and not a surprise.
    assert echo.shared("live.example.com"), (
        "the first-label rule no longer over-reaches; if that is deliberate, "
        "the country variants need another answer, because they are the "
        "over-claiming direction and this is the merging one"
    )


# ═════════════════════════════════════════════════════════════════════════════
# the declines, and the parsing behind them
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_an_origin_that_cannot_be_read_declines_rather_than_agreeing():
    """**Story 17's blank-origin rule, arriving at a second level.**

    A missing origin is not an identity, and it is not agreement either. Were
    blankness agreement, a mailbox whose ``from`` headers could not be read
    would classify every block as one organisation's furniture and hand story
    18's defect back **as a split** — which admits claims rather than
    withholding them, the direction CAP-3 exists to prevent.

    So an origin this cannot read declines, and declining means story 18's
    answer: the voices stay merged. Every shape that cannot be read is here,
    including the ones that are not blank at all — a sender with no ``@``, which
    is a name rather than an address; two addresses in one header, where picking
    either would be a guess; and trailing text, which is a header this rule was
    never handed.
    """
    unreadable = ("", "   ", None, "Billing Team", "@nolocal.example",
                  "nolocal@", b"a@corp.example", 17,
                  "a@corp.example (Legal)", "a@x.example, b@y.example",
                  "a@nodot", "a@corp..example")
    for origin in unreadable:
        assert echo.domain(origin) is None, repr(origin)
        assert echo.organisation(origin) is None, repr(origin)
        assert echo.travelled(("one.example", echo.organisation(origin))), (
            f"{origin!r} was read as agreement with one.example, so a mailbox "
            "with unreadable senders would split rather than merge"
        )
    # Through the shipped path: a forward whose sender cannot be read is still
    # one voice with its original, because the rule declined to classify it.
    original = ORIGINALS["latin"]
    run = a_run(original, forwarded(original),
                senders=("billing@svc.example", ""))
    keys = {candidate.independence_key for candidate in run.supports(TRAVELS)}
    assert len(keys) == 1, (
        "a forward with an unreadable sender declared its own handle; blankness "
        "was treated as agreement and the pair split"
    )


@pytest.mark.cap3_axes
def test_one_carrier_is_nothing_to_classify_from():
    """**Below two carriers the rule has no question to ask.**

    A block seen once has not been shown to stay anywhere. There is no answer to
    *"does this leave the organisation"* from a single carrier, so the rule
    declines and story 18's answer stands unchanged — which merges, the
    direction that withholds claims rather than admitting them.

    Unreachable from ``declaring``, where a containment match always puts at
    least the arriving body and the body it matched in the carrier set. It is a
    guard on the predicate rather than a shape in the mail, and it is asserted
    here so that a future caller reaching it gets the conservative answer rather
    than whatever falls out of an empty set.

    **The predicate reads resolved organisations, not raw origins**, because
    ``declaring`` resolves each held body's once per arrival rather than once
    per match. A caller that forgets is read as unresolved and declines, rather
    than being answered confidently on two addresses that share a company —
    which is the last row here and the one that would be silently wrong.
    """
    assert echo.travelled(()) is True
    assert echo.travelled(("one.example",)) is True
    assert echo.travelled((None,)) is True
    # Two carriers is where the question starts being answerable, and both
    # answers are here so neither is the default.
    assert echo.travelled(("one.example", "two.example")) is True
    assert echo.travelled(("one.example", "one.example")) is False
    # An unresolved value declines rather than being compared as a string.
    assert echo.travelled(("a@one.example", "b@one.example")) is True
    assert echo.travelled(("one.example", None)) is True


@pytest.mark.cap3_axes
def test_a_block_carried_twice_by_one_address_is_one_support_either_way():
    """**One sender repeated is not two carriers, and it does not matter.**

    A block carried by two bodies from the *same* address — an automated system
    that sends a notice and later a digest containing it — resolves to one
    organisation, so this rule answers *furniture* and the two declare separate
    handles.

    That answer is invisible, and the case exists to say so rather than to leave
    a reader wondering. Story 17's second level maps each voice to its single
    origin, and both bodies carry the same one, so the two answer to the same
    handle and count as **one** support whatever this rule declared. The
    classifier can neither help nor hurt where the origin is identical, which is
    why the discriminator never had to distinguish *two carriers* from *one
    sender twice*.
    """
    notice = ORIGINALS["latin"]
    digest = "Today's summary.\n\n" + notice
    one_sender = a_run(notice, digest,
                       senders=("noreply@shop.example", "noreply@shop.example"))
    keys = [c.independence_key for c in one_sender.supports(TRAVELS)]
    assert keys[0] != keys[1], (
        "one address carrying a block twice classified as travelling; if that "
        "is a fix, the count below is unchanged either way and this case "
        "should say which answer it now pins"
    )
    assert voices(one_sender) == 1, (
        "two bodies from one address stopped being one support; story 17's "
        "origin level is what makes this rule's answer here invisible"
    )
    # And with the classifier switched off, so the two share a handle: still
    # one support. The number does not move, which is the whole claim.
    def always(homes):
        return True

    both = a_run(notice, digest, classify=always,
                 senders=("noreply@shop.example", "noreply@shop.example"))
    assert len({c.independence_key for c in both.supports(TRAVELS)}) == 1
    assert voices(both) == 1


@pytest.mark.cap3_structure
def test_the_domain_is_the_at_tail_and_the_display_name_is_the_only_parsing():
    """**The whole of the derivation, and what it is honest about parsing.**

    Three people at one company are one organisation with three addresses, which
    is why the full address cannot be the unit: story 19's discriminator would
    answer *"three origins, it travelled"* for a footer that never left the
    building. So the part after the last ``@`` is taken — and beyond that, only
    a display name is handled.

    **Calling that "one character" was wrong and the docstring said so for a
    while.** Every real ``From:`` header is ``Billing <billing@svc.example>``,
    so declining on the bracket form would turn this rule off for most of a
    mailbox, which is the over-claiming direction. The brackets are parsed, and
    so is a trailing root dot; nothing else is.

    ``normalized`` is ``half.ingest.independence``'s own, so the two agree on
    casefolding under NFC — and on nothing else, since that module compares
    whole addresses and this one compares the tail.
    """
    assert echo.domain("billing@service.example") == "service.example"
    # Story 17's address-spelling row, at the second level: casefolded under NFC.
    assert echo.domain("A@X.Com") == echo.domain("a@x.com")
    # The two things that are parsed, named.
    assert echo.domain("Billing <billing@service.example>") == "service.example"
    assert echo.domain('"Doe, John" <john@corp.example>') == "corp.example"
    assert echo.domain("a@corp.example.") == echo.domain("a@corp.example"), (
        "a trailing root dot reads as a second organisation, so one company "
        "spelled two ways would look like a block that travelled"
    )
    # Nothing else is: a subdomain is a different string, and that is the
    # conservative direction — it makes a block look like it travelled, which
    # merges, rather than like furniture, which splits.
    assert echo.domain("a@mail.corp.example") != echo.domain("b@corp.example")
    # And no plus-address parsing: the local part is never read at all.
    assert echo.domain("a+tag@corp.example") == "corp.example"
    # Worldwide: an internationalised domain is a string like any other, and no
    # script is special-cased. This is not decoration — the obvious spelling of
    # the shape check rejects a Devanagari matra, and answered None here.
    assert echo.domain("संपर्क@उदाहरण.भारत") == "उदाहरण.भारत"
    assert echo.domain("بريد@مثال.مصر") == "مثال.مصر"


@pytest.mark.cap3_structure
def test_an_organisation_is_the_domain_unless_the_domain_is_shared():
    """``organisation`` is ``domain`` with the shared exclusion, and no more.

    Split from ``domain`` because they answer different questions and both are
    load-bearing: one reads a header, the other decides whether what it read is
    a company. A build that folded them would have no way to say that
    ``gmail.com`` is a perfectly readable domain which is nevertheless nobody's
    organisation.
    """
    assert echo.organisation("a@corp.example") == "corp.example"
    assert echo.domain(f"a@{A_PROVIDER}") == A_PROVIDER
    assert echo.organisation(f"a@{A_PROVIDER}") is None, (
        "a webmail provider resolved to an organisation, which is the "
        "regression that made an ordinary forward two supports"
    )
    assert echo.organisation(f"a@{A_UNIVERSITY}") is None
    assert echo.organisation(f"a@{AN_ISP}") is None
    # And the two causes of None are the same answer on purpose: *this tells us
    # nothing*. A caller that needed to tell them apart would ask `domain`.
    assert echo.organisation("Billing Team") is None


@pytest.mark.cap3_structure
def test_two_spellings_of_one_internationalised_domain_are_two_organisations():
    """**A recorded limit in the merging direction, and its unpleasant sibling.**

    Nothing here converts between an internationalised domain's Unicode form and
    its ASCII ``xn--`` form, so one company spelled both ways reads as two
    organisations. A block carried across the two then looks like it travelled
    and **merges**, which is the conservative side, so it is recorded rather
    than fixed: converting needs ``encodings.idna``, which this module may not
    import and which implements the older standard — the one whose folding is
    the problem in the next paragraph.

    **The sibling runs the other way and is why this case is here.**
    ``normalized`` casefolds, and ``str.casefold`` maps ``ß`` to ``ss``. So an
    internationalised domain spelled with an eszett folds together with a
    different company spelled ``ss`` — two organisations read as **one**, which
    makes a block between them look confined and *splits* it. That is the
    over-claiming direction. It is accepted knowingly: the alternative is a
    second normalisation idea in this module, which is the drift the shared
    ``normalized`` exists to close, and the shape needs two real companies whose
    domains differ only by that fold.
    """
    assert echo.domain("a@bücher.example") != echo.domain("a@xn--bcher-kva.example"), (
        "an A-label and its U-label now agree; if that is a fix, the residue "
        "is closed and this case should assert equality"
    )
    # Merging, because two organisations means the block travelled.
    assert echo.travelled((echo.domain("a@bücher.example"),
                           echo.domain("b@xn--bcher-kva.example"))) is True
    # And the fold that runs the other way, pinned with its direction.
    assert echo.domain("a@straße.example") == echo.domain("b@strasse.example"), (
        "the eszett fold is gone; if that is a fix, the over-claiming residue "
        "is closed and this case should assert inequality"
    )
    assert echo.travelled((echo.domain("a@straße.example"),
                           echo.domain("b@strasse.example"))) is False, (
        "two domains that casefold together are one organisation, so a block "
        "between them is furniture and splits — the over-claiming direction"
    )


@pytest.mark.cap3_structure
def test_containment_is_directional_and_a_shorter_body_is_never_a_carrier():
    """``contains`` asked in one direction, which is what ``carrying`` needs.

    ``inside`` answers *"are these two the same evidence"* and is symmetric.
    ``contains`` answers *"is this body a carrier of that block"* and is not: a
    held body shorter than the block is not a carrier of it however much they
    share. Swapping the two arguments at ``carrying``'s call site left the whole
    suite green until this case existed.
    """
    longer = echo.units("Note four. " + ORIGINALS["latin"])
    shorter = echo.units(ORIGINALS["latin"])
    assert echo.contains(longer, shorter)
    assert not echo.contains(shorter, longer), (
        "a longer body sat inside a shorter one, so the direction is not being "
        "read and every body in the window would count as a carrier"
    )
    assert echo.inside(longer, shorter) and echo.inside(shorter, longer)
    # The guards, each its own branch: nothing contains nothing, and a sequence
    # cannot contain one longer than itself.
    assert not echo.contains((), ())
    assert not echo.contains((), shorter)
    assert not echo.contains(shorter, ())
    assert not echo.contains(shorter, shorter + ("extra",))
    # Whole-term boundaries at the ends, which is what the sentinels are for.
    assert echo.contains(("gratis", "aid"), ("gratis",))
    assert not echo.contains(("gratis", "aid"), ("rat",))
    # And through ``carrying``: the carriers of a block are the bodies it is in.
    window = [echo._cut("k0", ORIGINALS["latin"], "a@one.example", terms),
              echo._cut("k1", "Note four. " + ORIGINALS["latin"],
                        "b@two.example", terms),
              echo._cut("k2", "Something else entirely, about a parcel.",
                        "c@three.example", terms)]
    assert echo.carrying(shorter, window) == ("one.example", "two.example"), (
        "the carrier set is not the bodies the block is in"
    )
    assert echo.carrying(longer, window) == ("two.example",)


# ═════════════════════════════════════════════════════════════════════════════
# the production path, and the residues nothing pinned
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.cap3_axes
def test_the_arriving_origin_reaches_the_classifier_through_observe():
    """**The production call site, which nothing asserted.**

    Every other case in this file reaches ``Run.declares`` itself and hands it an
    ``origin``, so none of them covers ``Revealed.observe`` — the one call site
    the product uses. Review demonstrated the consequence: changing
    ``origin=receipt.sender`` to ``origin=""`` there left the **whole suite
    passing**, with story 19 switched off in production and nothing noticing.

    That is the worst shape a gap can take, because the blanked build is not
    obviously broken — a blank origin declines, declining merges, and merging is
    story 18's answer, which most of this file asserts.

    So the shape here is one only the live origin can answer: a footer arriving
    alone and two notes carrying it, all from one company. With the origin
    reaching the classifier the block is furniture and there are **three**
    supports; with it blank the rule declines, all three adopt the footer's
    handle, and there is **one**.

    The cross-organisation forward is the control, read through the same call
    site, so the case cannot be satisfied by a build that stopped collapsing.
    """
    note = "Note {}: please look at item {} before the review.".format
    bodies = [DISCLAIMER,
              note(1, 1) + "\n\n" + DISCLAIMER,
              note(2, 2) + "\n\n" + DISCLAIMER]
    reader, _, _, _ = a_reader()
    run = observe(
        reader,
        [a_receipt(index, thread=f"t{index}", sender=f"p{index}@{ONE_COMPANY}")
         for index in range(len(bodies))],
        texts=bodies,
    )
    assert len(run.supports(TRAVELS)) == 3, "the reader did not read three bodies"
    assert voices(run) == 3, (
        "the footer collapsed two notes read through Revealed.observe. The "
        "arriving body's origin is not reaching the classifier at the one call "
        "site the product uses — every other case in this file passes `origin` "
        "itself and cannot see that"
    )

    # The control, through the same call site: a genuine forward across two
    # organisations is still one voice.
    original = ORIGINALS["latin"]
    crossing = observe(
        reader,
        [a_receipt(0, thread="t_sub", sender="billing@svc.example"),
         a_receipt(1, thread="t_fwd", sender="asst@work.example")],
        texts=[original, forwarded(original)],
    )
    assert voices(crossing) == 1, (
        "the control failed, so the row above is measuring a build that "
        "collapses nothing rather than one that reads the origin"
    )


@pytest.mark.cap3_axes
def test_a_carrier_past_the_tokenizer_ceiling_is_a_carrier_the_rule_cannot_see():
    """**A residue in the over-claiming direction, pinned like its siblings.**

    ``echo.units`` yields nothing for a body past ``MAX_INPUT_CHARS`` or
    ``MAX_TERMS``, and ``carrying`` skips a body that declared nothing. So an
    oversized held body that genuinely carries the block is not counted among
    its carriers: the organisation set is smaller than the truth, and *one
    organisation* — the splitting answer — becomes likelier than it should be.

    Here that is the whole difference. A block, one oversized carrier at another
    company, and one ordinary carrier at the block's own: the truth is that the
    block travelled, and the rule cannot see the carrier that proves it, so the
    ordinary carrier splits off. Asserted against the identical mailbox with the
    oversized body a few hundred characters shorter, which is one voice.
    """
    block = ORIGINALS["latin"]
    padding = ("The registered card will be charged on the stated date and a "
               "receipt will follow by electronic mail. ")
    huge = "FYI." + SEPARATOR + block + "\n\n" + padding * 200
    assert len(huge) > MAX_INPUT_CHARS
    assert echo.units(huge) == (), "the oversized carrier is readable; no residue"
    small = "FYI." + SEPARATOR + block + "\n\n" + padding
    assert echo.units(small), "the control body does not fit either"

    people = (f"legal@{ONE_COMPANY}", "asst@work.example", f"hr@{ONE_COMPANY}")
    blind = a_run(block, huge, block + "\n\nSee the note above.",
                  senders=people)
    assert voices(blind) == 3, (
        "the oversized carrier is being counted; if that is a fix, the residue "
        "is closed and this case should assert two"
    )
    seeing = a_run(block, small, block + "\n\nSee the note above.",
                   senders=people)
    assert voices(seeing) == 1, (
        "the control is failing, so the row above is measuring something other "
        "than the ceiling"
    )


@pytest.mark.cap3_structure
def test_no_origin_and_no_domain_travels_in_a_declared_key():
    """**AD-13 and AD-22 over the field story 19 added to the comparison.**

    The rule now reads an origin. What leaves it is still a digest and never a
    text — but nothing said so about the *origin*, and a key that carried a
    domain would put the sender of somebody's mail into a projection, a log line
    and a fixture's expected output.

    Every key this file can produce, across the shapes that reach the classifier
    on both of its branches, is asserted to be the prefix plus sixty-four hex
    digits and to contain no ``@`` and none of the fixture domains.
    """
    original = ORIGINALS["latin"]
    domains = (ONE_COMPANY, A_PROVIDER, AN_ISP, A_UNIVERSITY, "svc.example",
               "work.example", AN_UNLISTED_PROVIDER)
    runs = [
        a_run(DISCLAIMER, under_a_footer(1, 2), at=ONE_COMPANY),
        a_run(original, forwarded(original),
              senders=(f"a@{A_PROVIDER}", f"b@{A_PROVIDER}")),
        a_run(original, forwarded(original),
              senders=("billing@svc.example", "asst@work.example")),
        a_run(original, forwarded(original), at=ONE_COMPANY),
    ]
    hexadecimal = set("0123456789abcdef")
    seen = 0
    for run in runs:
        for candidate in run.supports(TRAVELS):
            key = candidate.independence_key
            assert key.startswith(echo.PREFIX), key
            body = key[len(echo.PREFIX):]
            assert len(body) == 64 and set(body) <= hexadecimal, key
            assert echo.AT not in key, "an address travelled in a declared key"
            for place in domains:
                assert place not in key, f"{place} travelled in a declared key"
            seen += 1
    assert seen == 8, "the fixtures stopped producing the keys this reads"


@pytest.mark.cap3_structure
def test_the_rejected_rules_skeleton_still_agrees_with_the_shipped_rule():
    """**The sweep's anti-drift probe, as a gate rather than as a print.**

    ``tools/percolation_sim.py`` runs the two rejected containment rules through
    a skeleton of ``declaring``, and a copy of ``declaring`` living in that file
    is exactly the drift that made the probe necessary in the first place. The
    sweep printed the number of disagreements; nothing failed on it, and no test
    or CI step runs the sweep at all.

    So the probe is asserted here. Both branches of the classifier are crossed —
    an arriving origin from outside the window's organisations, and one from
    inside — because a probe that only ever travels cannot see a skeleton that
    forgot to classify.
    """
    import tools.percolation_sim as sweep

    probe = [(echo.own_key(under_a_footer(i, i + 1)), under_a_footer(i, i + 1),
              f"p{i}@d{i}.example") for i in range(MAX_SOURCES)]
    nothing = ("", "a held body that declared nothing", "p@nowhere.example")
    checked = [under_a_footer(99, 3), "FYI\n\n" + under_a_footer(3, 4),
               "Thanks!", DISCLAIMER]
    for body in checked:
        for whom in ("me@elsewhere.example", "p3@d3.example"):
            window = [nothing, *probe]
            theirs = sweep._declaring_by(body, window, sweep.BY_SEQUENCE,
                                         origin=whom, classify=echo.travelled)
            ours = echo.declaring(body, window, origin=whom)
            assert theirs == ours, (
                f"the sweep's skeleton disagrees with echo.declaring on "
                f"{body[:24]!r} from {whom}; a second implementation of the "
                "rule has drifted from the first"
            )
    # And the same probe with the classifier off, which must disagree — a
    # cross-check that agrees under every rule is not checking anything.
    inside_one = [(echo.own_key(under_a_footer(i, i + 1)),
                   under_a_footer(i, i + 1), f"p{i}@{ONE_COMPANY}")
                  for i in range(MAX_SOURCES)]
    forward = "FYI\n\n" + under_a_footer(3, 4)
    whom = f"p9@{ONE_COMPANY}"
    assert (sweep._declaring_by(forward, inside_one, sweep.BY_SEQUENCE)
            != echo.declaring(forward, inside_one, origin=whom)), (
        "story 18's skeleton and the shipped rule agree on a block that never "
        "leaves one company, so this probe cannot tell them apart"
    )


@pytest.mark.cap3_axes
@pytest.mark.parametrize("script", sorted(ORIGINALS))
def test_the_classification_gives_the_same_answers_in_every_script(script):
    """**Scriptio continua and combining marks change nothing.**

    The block is found with ``half.text.terms`` and classified on the sender's
    domain, and neither reads a language. So the same two answers must come out
    in all nine writing systems: a footer that never leaves one company keeps
    every message its own voice, and a notice forwarded between two companies is
    one voice — the second of which is already story 18's row, asserted again
    here beside the first so the pair is measured on one fixture.

    A rule green on Latin alone would be dead for a large share of the world and
    nothing would say so.
    """
    block = ORIGINALS[script]
    assert len(frozenset(echo.units(block))) >= echo.MIN_TERMS, (
        f"the {script} block is too short to declare anything, so this row "
        "measures nothing"
    )
    # The block arriving alone in front of three messages that carry it, every
    # sender a different person at one company: every message its own voice.
    notes = [f"Note {i}.\n\n{block}" for i in range(3)]
    assert voices(a_run(block, *notes, at=ONE_COMPANY)) == 4, (
        f"a {script} block stapled by one company collapsed the messages "
        "carrying it"
    )
    # The same four bodies, each from a different company: the block travelled,
    # so they are one voice. Only the senders differ between the two runs.
    assert voices(a_run(block, *notes)) == 1, (
        f"a {script} block carried between four companies stopped being one "
        "voice"
    )


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
                          sender="a@one.example", digest="d0",
                          independence_key=run.declares(TRAVELS, scrubbed,
                                                        origin="a@one.example"))
    run.add(candidate)
    assert run.hold(candidate, scrubbed)
    assert run.holding == 1
    # The label generates, whatever it came to, and drops its texts in the
    # same call. This is the shipped method rather than a reconstruction.
    run.spent(TRAVELS)
    assert run.holding == 0

    forward = scrub(forwarded(original))
    assert run.declares(TRAVELS, forward,
                        origin="b@two.example") == echo.own_key(forward.text), (
        "a body arriving after the generation adopted something, so a text "
        "outlived its label's one generation"
    )
    later = Candidate(label=TRAVELS, source_id="m1", thread_id="t1",
                      sender="b@two.example", digest="d1",
                      independence_key=run.declares(TRAVELS, forward,
                                                    origin="b@two.example"))
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
            sender = f"p{index}@d{index}.example"
            candidate = Candidate(
                label=TRAVELS, source_id=f"m{index}", thread_id=thread,
                sender=sender, digest=f"d{index}",
                independence_key=run.declares(TRAVELS, scrubbed,
                                              origin=sender),
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

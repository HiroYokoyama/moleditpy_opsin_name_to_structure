"""Pairing OPSIN's stderr complaints with the names that caused them.

OPSIN exits 0 even when it rejects a name, and says why only on stderr. These
are the shapes it actually emits, taken from real runs.
"""

from opsin_name_to_structure import engine

UNPARSABLE = (
    "not-a-real-name-xyz is unparsable due to the following being "
    "uninterpretable: not-a-real-name-xyz"
)
SUBSTITUENT = (
    "pyridin-2-yl could be parsed but OPSIN was unsure of the meaning of the "
    "words. This error will occur, by default, if a name is just a substituent"
)
NO_ACID = '"acid" not found after ic'


def test_a_message_opening_with_the_name_is_matched_to_it():
    reasons = engine.parse_errors(UNPARSABLE, ["not-a-real-name-xyz"])
    assert reasons["not-a-real-name-xyz"].startswith("is unparsable")


def test_the_redundant_leading_name_is_trimmed():
    # The row already carries the name in its own column.
    reasons = engine.parse_errors(SUBSTITUENT, ["pyridin-2-yl"])
    assert not reasons["pyridin-2-yl"].startswith("pyridin-2-yl")
    assert "just a substituent" in reasons["pyridin-2-yl"]


def test_a_message_that_never_names_the_name_is_still_paired():
    # 'acetic' without -a yields only '"acid" not found after ic'.
    reasons = engine.parse_errors(NO_ACID, ["acetic"])
    assert reasons["acetic"] == NO_ACID


def test_several_names_each_get_their_own_reason():
    stderr = "\n".join([SUBSTITUENT, NO_ACID, UNPARSABLE])
    reasons = engine.parse_errors(
        stderr, ["pyridin-2-yl", "acetic", "not-a-real-name-xyz"]
    )
    assert "substituent" in reasons["pyridin-2-yl"]
    assert reasons["acetic"] == NO_ACID
    assert "unparsable" in reasons["not-a-real-name-xyz"]


def test_an_ambiguous_leftover_is_left_unexplained():
    """Two nameless messages and one unmatched name could pair either way.

    Showing one name another name's reason is worse than the generic message,
    so the counts have to line up before anything is paired positionally.
    """
    stderr = "\n".join([NO_ACID, "some other complaint"])
    reasons = engine.parse_errors(stderr, ["acetic"])
    assert "acetic" not in reasons


def test_no_stderr_means_no_reasons():
    assert engine.parse_errors("", ["whatever"]) == {}
    assert engine.parse_errors(None, ["whatever"]) == {}


def test_blank_lines_are_not_treated_as_messages():
    reasons = engine.parse_errors(f"\n\n{NO_ACID}\n\n", ["acetic"])
    assert reasons["acetic"] == NO_ACID


def test_a_name_with_no_message_falls_back_to_the_generic_text(monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: ([""], ""))
    (result,) = engine.convert(["nonsense"])
    assert result.error == engine.GENERIC_FAILURE


def test_the_reason_reaches_the_conversion(monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: (["", "CCO"], SUBSTITUENT))
    bad, good = engine.convert(["pyridin-2-yl", "ethanol"])
    assert "just a substituent" in bad.error
    assert good.ok


def test_a_successful_name_never_picks_up_a_reason(monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: (["CCO"], NO_ACID))
    (result,) = engine.convert(["ethanol"])
    assert result.ok and result.error == ""

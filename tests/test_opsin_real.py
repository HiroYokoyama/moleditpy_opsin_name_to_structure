"""The tier that actually starts OPSIN. Skipped when Java is absent."""

import pytest

from opsin_name_to_structure import engine

usable, reason = engine.availability()
pytestmark = pytest.mark.skipif(not usable, reason=reason or "OPSIN unavailable")


def test_known_names_convert_correctly():
    benzene, ethanol, aldehyde = engine.convert(
        ["benzene", "ethanol", "2,4-dimethoxybenzaldehyde"]
    )
    assert benzene.smiles == "c1ccccc1" and benzene.formula == "C6H6"
    assert ethanol.smiles == "CCO"
    assert aldehyde.formula == "C9H10O3"


def test_a_bad_name_fails_without_shifting_the_other_rows():
    results = engine.convert(["benzene", "definitely-not-a-chemical", "ethanol"])
    assert [r.name for r in results] == [
        "benzene",
        "definitely-not-a-chemical",
        "ethanol",
    ]
    assert results[0].ok and not results[1].ok and results[2].ok
    assert results[2].smiles == "CCO"


def test_substituent_names_need_the_radicals_option():
    (without,) = engine.convert(["pyridin-2-yl"])
    assert not without.ok

    (with_radicals,) = engine.convert(
        ["pyridin-2-yl"], engine.Options(allow_radicals=True)
    )
    assert with_radicals.ok


def test_stereochemistry_survives():
    (result,) = engine.convert(["(2R)-2-amino-3-phenylpropanoic acid"])
    assert result.ok
    assert "@" in result.smiles  # a stereocentre made it through


def test_inchikey_is_produced():
    (result,) = engine.convert(["benzene"])
    assert result.inchikey.startswith("UHOVQNZJYSORNB")


def test_the_jar_comes_from_py2opsin():
    jar = engine.jar_path()
    assert jar and "py2opsin" in jar.replace("\\", "/").lower()


def test_real_opsin_explains_each_failure_in_its_own_words():
    """The stderr contract this plugin now depends on, against the real jar.

    OPSIN exits 0 for a name it cannot read and says why only on stderr, so a
    change in either would quietly turn every reason back into boilerplate.
    """
    substituent, acid, nonsense = engine.convert(
        ["pyridin-2-yl", "acetic", "not-a-real-name-xyz"]
    )

    assert not substituent.ok and "substituent" in substituent.error
    assert not acid.ok and "acid" in acid.error
    assert not nonsense.ok and "unparsable" in nonsense.error
    # None of them should be falling back to the generic message.
    for result in (substituent, acid, nonsense):
        assert result.error != engine.GENERIC_FAILURE


def test_the_options_turn_those_same_names_into_structures():
    substituent, acid = engine.convert(
        ["pyridin-2-yl", "acetic"],
        engine.Options(allow_radicals=True, allow_acid=True),
    )
    assert substituent.ok and acid.ok
    assert acid.formula == "C2H4O2"


def test_a_partial_batch_keeps_exit_code_zero():
    # The whole per-name error design rests on this: a rejected name is not a
    # failed run, so convert() must not raise for it.
    results = engine.convert(["benzene", "not-a-real-name-xyz"])
    assert results[0].ok and not results[1].ok

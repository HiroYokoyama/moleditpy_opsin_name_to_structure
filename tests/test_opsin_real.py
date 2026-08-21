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

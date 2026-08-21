"""Engine logic, with OPSIN itself stubbed out."""

import subprocess

import pytest

from opsin_name_to_structure import engine


# --- input handling ------------------------------------------------------


def test_split_names_trims_and_drops_blanks():
    assert engine.split_names("  benzene \n\n toluene\n") == ["benzene", "toluene"]


def test_split_names_removes_duplicates_but_keeps_order():
    assert engine.split_names("b\na\nb\nc") == ["b", "a", "c"]


def test_split_names_handles_empty_input():
    assert engine.split_names("") == []
    assert engine.split_names(None) == []


# --- options -------------------------------------------------------------


def test_default_options_pass_no_flags():
    assert engine.Options().flags() == []


def test_each_option_maps_to_its_opsin_flag():
    every = engine.Options(True, True, True, True)
    assert every.flags() == ["-a", "-r", "-s", "-w"]
    assert engine.Options(allow_radicals=True).flags() == ["-r"]


# --- availability --------------------------------------------------------


def test_availability_reports_missing_java(monkeypatch):
    monkeypatch.setattr(engine, "java_path", lambda: None)
    usable, message = engine.availability()
    assert usable is False
    assert "Java" in message and "pip" in message


def test_availability_reports_missing_py2opsin(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "py2opsin":
            raise ImportError("no py2opsin")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    usable, message = engine.availability()
    assert usable is False
    assert "py2opsin" in message


def test_convert_refuses_to_run_when_unavailable(monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (False, "no java here"))
    with pytest.raises(engine.OpsinUnavailable, match="no java here"):
        engine.convert(["benzene"])


def test_convert_of_nothing_does_not_touch_opsin(monkeypatch):
    monkeypatch.setattr(
        engine, "availability", lambda: (_ for _ in ()).throw(AssertionError())
    )
    assert engine.convert([]) == []
    assert engine.convert(["", ""]) == []


# --- conversion ----------------------------------------------------------


@pytest.fixture
def available(monkeypatch):
    monkeypatch.setattr(engine, "availability", lambda: (True, ""))


def test_convert_describes_each_result(available, monkeypatch):
    monkeypatch.setattr(
        engine, "_run_jar", lambda names, options, timeout: ["C1=CC=CC=C1", "CCO"]
    )
    benzene, ethanol = engine.convert(["benzene", "ethanol"])
    assert benzene.ok and benzene.formula == "C6H6"
    assert benzene.smiles == "c1ccccc1"  # canonicalised by RDKit
    assert benzene.inchikey.startswith("UHOVQNZJYSORNB")
    assert ethanol.formula == "C2H6O"


def test_blank_output_becomes_a_failed_row(available, monkeypatch):
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: ["", "CCO"])
    bad, good = engine.convert(["nonsense", "ethanol"])
    assert not bad.ok and "could not interpret" in bad.error
    assert bad.name == "nonsense" and bad.smiles == ""
    assert good.ok


def test_short_output_is_padded_so_rows_stay_aligned(available, monkeypatch):
    # OPSIN prints one line per name; a truncated run must not shift results.
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: ["C1=CC=CC=C1"])
    results = engine.convert(["benzene", "ethanol", "toluene"])
    assert [r.name for r in results] == ["benzene", "ethanol", "toluene"]
    assert results[0].ok and not results[1].ok and not results[2].ok


def test_unreadable_smiles_is_reported_not_silently_dropped(available, monkeypatch):
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: ["not a smiles at all"])
    (result,) = engine.convert(["weird"])
    assert not result.ok
    assert "RDKit" in result.error


def test_timeout_becomes_a_readable_error(available, monkeypatch):
    def explode(names, options, timeout):
        raise subprocess.TimeoutExpired(cmd="java", timeout=timeout)

    monkeypatch.setattr(engine, "_run_jar", explode)
    with pytest.raises(engine.OpsinUnavailable, match="did not finish"):
        engine.convert(["benzene"], timeout=5)


def test_falls_back_to_py2opsin_when_the_jar_is_missing(available, monkeypatch):
    monkeypatch.setattr(engine, "_run_jar", lambda n, o, t: None)
    monkeypatch.setattr(engine, "_run_py2opsin", lambda names, options: ["CCO"])
    (result,) = engine.convert(["ethanol"])
    assert result.formula == "C2H6O"


def test_options_reach_the_runner(available, monkeypatch):
    seen = {}

    def capture(names, options, timeout):
        seen["flags"] = options.flags()
        return ["C1=CC=CC=C1"]

    monkeypatch.setattr(engine, "_run_jar", capture)
    engine.convert(["benzene"], engine.Options(allow_radicals=True))
    assert seen["flags"] == ["-r"]


# --- the jar we do not ship ----------------------------------------------


def test_jar_is_found_inside_py2opsin_not_in_this_repo():
    jar = engine.jar_path()
    if jar is None:
        pytest.skip("py2opsin is not installed")
    assert jar.lower().endswith(".jar")
    assert "py2opsin" in jar.replace("\\", "/").lower()


def test_repo_ships_no_java(tmp_path):
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    offenders = [
        p
        for p in repo.rglob("*")
        if p.suffix.lower() in {".jar", ".java", ".class"} and ".git" not in p.parts
    ]
    assert not offenders, f"this plugin must not ship Java: {offenders}"

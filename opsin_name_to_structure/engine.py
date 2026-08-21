"""Turn IUPAC names into structures with OPSIN, shipping no Java of our own.

The OPSIN jar lives inside the pip-installable ``py2opsin`` package, so this
plugin never carries one. We locate that jar and drive it directly rather than
calling ``py2opsin()``, for three reasons: its subprocess call has no timeout,
it writes its scratch file into the current working directory, and on Windows
it flashes a console window. If the jar cannot be found we fall back to
``py2opsin()`` itself.

OPSIN emits one output line per input line, leaving a blank line where a name
did not parse, so a whole batch goes through a single JVM start.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple

try:
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
except ImportError:  # pragma: no cover - the host always provides rdkit
    Chem = None
    CalcMolFormula = None

#: A hung JVM must not wedge the editor; OPSIN answers in well under a second.
DEFAULT_TIMEOUT = 120

JAVA_MISSING = (
    "Java was not found on this system.\n\n"
    "OPSIN is a Java program, and Java cannot be installed with pip. "
    "Install a Java runtime (for example Temurin or Microsoft OpenJDK), "
    "make sure the 'java' command works in a terminal, then reopen this window."
)
PY2OPSIN_MISSING = (
    "The py2opsin package is not installed.\n\n"
    "Install it with:  pip install py2opsin\n"
    "(The Plugin Installer can also install plugin dependencies for you.)"
)


class Options(NamedTuple):
    """The four OPSIN switches worth exposing."""

    allow_acid: bool = False
    allow_radicals: bool = False
    allow_bad_stereo: bool = False
    wildcard_radicals: bool = False

    def flags(self) -> List[str]:
        out = []
        if self.allow_acid:
            out.append("-a")
        if self.allow_radicals:
            out.append("-r")
        if self.allow_bad_stereo:
            out.append("-s")
        if self.wildcard_radicals:
            out.append("-w")
        return out


class Conversion(NamedTuple):
    """One name and what OPSIN made of it."""

    name: str
    smiles: str = ""
    formula: str = ""
    inchi: str = ""
    inchikey: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.smiles) and not self.error


class OpsinUnavailable(RuntimeError):
    """Raised when Java or py2opsin is missing; the message is user-facing."""


def java_path() -> Optional[str]:
    """Path to the java executable, or None."""
    return shutil.which("java")


def jar_path() -> Optional[str]:
    """The OPSIN jar inside the installed py2opsin package, if present."""
    try:
        import py2opsin
    except ImportError:
        return None
    package_dir = os.path.dirname(os.path.abspath(py2opsin.__file__))
    for root, _dirs, files in os.walk(package_dir):
        for name in sorted(files):
            if name.lower().endswith(".jar"):
                return os.path.join(root, name)
    return None


def availability() -> Tuple[bool, str]:
    """(usable, message). The message is empty when everything is present."""
    try:
        import py2opsin  # noqa: F401
    except ImportError:
        return False, PY2OPSIN_MISSING
    if java_path() is None:
        return False, JAVA_MISSING
    return True, ""


def split_names(text: str) -> List[str]:
    """One name per line, blanks dropped, order kept, duplicates removed."""
    seen = set()
    names = []
    for line in (text or "").splitlines():
        name = line.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _no_window() -> Any:
    """Keep a console window from flashing up on Windows."""
    if sys.platform != "win32":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return info


def _run_jar(
    names: Sequence[str], options: Options, timeout: int
) -> Optional[List[str]]:
    """Drive the jar directly. Returns one line per name, or None if we can't."""
    jar = jar_path()
    java = java_path()
    if not jar or not java:
        return None

    scratch = os.path.join(tempfile.gettempdir(), f"opsin_names_{uuid.uuid4().hex}.txt")
    try:
        with open(scratch, "w", encoding="utf-8") as handle:
            handle.write("\n".join(names) + "\n")
        result = subprocess.run(
            [java, "-jar", jar, "-osmi", *options.flags(), scratch],
            capture_output=True,
            text=True,
            timeout=timeout,
            startupinfo=_no_window(),
            check=False,
        )
    finally:
        try:
            os.remove(scratch)
        except OSError:
            pass

    # A blank line marks a name OPSIN rejected, so the rows stay aligned.
    return result.stdout.splitlines()


def _run_py2opsin(names: Sequence[str], options: Options) -> List[str]:
    """Fallback: py2opsin's own entry point (no timeout of its own)."""
    from py2opsin import py2opsin

    scratch = os.path.join(tempfile.gettempdir(), f"opsin_names_{uuid.uuid4().hex}.txt")
    output = py2opsin(
        list(names),
        allow_acid=options.allow_acid,
        allow_radicals=options.allow_radicals,
        allow_bad_stereo=options.allow_bad_stereo,
        wildcard_radicals=options.wildcard_radicals,
        tmp_fpath=scratch,
    )
    if isinstance(output, str):
        output = output.splitlines()
    return list(output)


def _describe(name: str, smiles: str) -> Conversion:
    """Attach formula and InChI, derived locally so the JVM runs only once."""
    if not smiles:
        return Conversion(name=name, error="OPSIN could not interpret this name.")
    if Chem is None:
        return Conversion(name=name, smiles=smiles)

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return Conversion(
            name=name,
            smiles=smiles,
            error="OPSIN returned a structure RDKit could not read.",
        )
    try:
        inchi = Chem.MolToInchi(mol) or ""
        inchikey = Chem.InchiToInchiKey(inchi) if inchi else ""
    except (ValueError, RuntimeError):
        inchi, inchikey = "", ""
    return Conversion(
        name=name,
        smiles=Chem.MolToSmiles(mol),
        formula=CalcMolFormula(mol) if CalcMolFormula else "",
        inchi=inchi,
        inchikey=inchikey or "",
    )


def convert(
    names: Sequence[str],
    options: Optional[Options] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Conversion]:
    """Convert names to structures. Raises OpsinUnavailable if OPSIN can't run."""
    names = [n for n in names if n]
    if not names:
        return []

    usable, message = availability()
    if not usable:
        raise OpsinUnavailable(message)

    options = options or Options()
    try:
        lines = _run_jar(names, options, timeout)
        if lines is None:
            lines = _run_py2opsin(names, options)
    except subprocess.TimeoutExpired as exc:
        raise OpsinUnavailable(
            f"OPSIN did not finish within {timeout} seconds."
        ) from exc

    # zip() would silently drop names if a runner ever returned a short list,
    # so pad here, where names and lines are actually paired.
    lines = list(lines) + [""] * max(0, len(names) - len(lines))
    return [_describe(name, line.strip()) for name, line in zip(names, lines)]

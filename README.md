# OPSIN Name to Structure

[![Tests](https://github.com/HiroYokoyama/moleditpy_opsin_name_to_structure/actions/workflows/tests.yml/badge.svg)](https://github.com/HiroYokoyama/moleditpy_opsin_name_to_structure/actions/workflows/tests.yml)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

Type a systematic IUPAC name, get the structure in the 2D editor of
[MoleditPy](https://github.com/HiroYokoyama/python_molecular_editor).

Names are parsed **on your own computer** by
[OPSIN](https://github.com/dan2097/opsin), so there is no network call and no
database lookup — it understands any name the nomenclature rules allow, including
ones no database has ever indexed:

```
(2R)-2-amino-3-phenylpropanoic acid
4-[(1E)-2-phenylethenyl]pyridine
2,4-dimethoxybenzaldehyde
```

Paste a whole list, one name per line, and convert them in one go.

## Java, and what this plugin does *not* ship

OPSIN is a Java program. This repository contains **no jar and no Java source** —
the OPSIN jar comes from the pip-installable
[`py2opsin`](https://pypi.org/project/py2opsin/) package, which is declared as a
normal plugin dependency.

A **Java runtime (JRE) is still required** and cannot be installed with pip. If
`java` is not on your PATH the window opens, disables Convert and tells you what
to install, rather than failing halfway through a batch. Install Java afterwards
and simply reopen the window — it looks again rather than staying disabled for
the rest of the session.

## Install

1. Install a Java runtime (Temurin, Microsoft OpenJDK, or your distribution's
   `default-jre`) and check that `java -version` works in a terminal.
2. Install the plugin from the
   [latest release](https://github.com/HiroYokoyama/moleditpy_opsin_name_to_structure/releases)
   or with the **Plugin Installer** plugin, which will also install `py2opsin`.
3. Restart MoleditPy, or use **Plugins → Reload All Plugins**.

## Use

**Plugins → OPSIN Name to Structure...**

- One name per line; blank lines and duplicates are ignored.
- **Convert** (or **Ctrl+Enter**) parses the whole batch with a single JVM start.
- Every name gets a row — successes *and* failures — so nothing disappears
  quietly. A failed row carries **OPSIN's own reason**, not a generic message:
  `pyridin-2-yl` says it is just a substituent, `acetic` says `"acid" not found
  after ic`. That usually tells you which option to tick.
- The first column is the line the name came in on, so the table reads in the
  order you typed it. Click any header to sort; click **#** to get back.
- **Load to 2D Editor** (or double-click a row) puts that structure on the canvas.
- **Copy SMILES / InChI / InChIKey** for every selected row, one per line.
- **Export CSV...** writes the whole table, failures and their reasons included.

### Options

| Option | What it does |
|---|---|
| Allow radicals | Accept names that are only a substituent, e.g. `pyridin-2-yl` |
| Allow acids without "acid" | Accept `acetic` as `acetic acid` |
| Allow uninterpretable stereo | Ignore stereo OPSIN cannot read instead of failing the name |
| Wildcard radicals | Represent open valences as `*` wildcard atoms |

## Scope

OPSIN is a one-way parser: **name → structure**. There is no reverse mode, and no
pip-installable structure → name engine works on current Python (the only
candidate pins `tensorflow==2.10.1`, which has no wheels for Python 3.11+).

For the other direction, and for trade names and CAS numbers that are lookups
rather than grammar, use the **PubChem Name Resolver** and **PubChem Structure
Identifier** plugins, which query PubChem online. This plugin is the offline
complement to those.

## Development

```bash
pip install pytest pytest-cov PyQt6 rdkit py2opsin
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

`tests/test_opsin_real.py` starts the real OPSIN and is skipped when Java is
absent; CI installs a JDK and fails the job if that tier skips. `tests/test_api.py`
validates every host API call against the main app when the two repos are
checked out as siblings.

## License

GPL-3.0. See [LICENSE](LICENSE). OPSIN itself is MIT licensed and is distributed
via `py2opsin`, not by this repository.

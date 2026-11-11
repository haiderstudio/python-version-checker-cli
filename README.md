# python-version-checker-cli

Check Python files parse under the minimum version in pyproject.toml, fail CI on newer syntax.

[![CI](https://github.com/haiderstudio/python-version-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/python-version-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`python_version_checker` reads the minimum Python version
from your `pyproject.toml` (`requires-python`) and checks
every Python file parses under that version:

- Code that uses a 3.12 feature while the project declares
  Python 3.9 passes every local test (the author runs 3.12)
  and breaks on the server, in CI, or on a teammate's machine
  with a bare SyntaxError. This tool catches that before it
  ships: it parses each file with
  `ast.parse(source, feature_version=(x, y))` for the declared
  minimum, reports every file that uses newer syntax with its
  file and line, and exits 1 when any problem is found — so it
  can fail a CI run. A clean folder exits 0.
- The minimum version comes from `requires-python` in the
  nearest `pyproject.toml` at or above the checked path.
  `--target 3.9` sets the version directly and wins over
  `pyproject.toml`, so a project without one can still be
  checked.
- **With no `requires-python` and no `--target`, the tool
  stops with exit 2 and says so plainly.** There is no
  version to check against, and defaulting to the running
  version would pass every file and prove nothing. Add
  `requires-python` to `pyproject.toml` or pass `--target`,
  for example `--target 3.9`.
- A single file can be checked, or a whole folder walked
  recursively for `.py` files (`--no-recursive` stops at the
  top level). `.git`, `__pycache__`, `.venv`, `venv`, `.tox`,
  and `node_modules` folders are never walked, and directory
  links are never followed, so a link cycle cannot loop the
  check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude 'test_*'`. It can be repeated. A file passed
  directly on the command line is always checked, even if it
  matches an exclude pattern.
- `--stdin` checks Python source from standard input.
- `--json` prints the result as machine-readable JSON (the
  summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never edits a
  file, sends nothing anywhere, and needs no API key. Python
  standard library only — the check is one `ast` call.

## What it does NOT do

- It does not check code that parses fine but only runs on a
  newer version. An `int | str` annotation parses under
  Python 3.9 and only fails at run time, and a call to a
  library function added in 3.11 parses under every version.
  Those are not syntax, so no parser check can catch them —
  this tool only catches syntax the parser rejects under the
  target version.
- It does not check type annotations, imports, or library
  calls — only syntax.
- It does not fix, rewrite, or convert any file. A file using
  newer syntax is reported; changing it is your job.
- It does not install or switch Python versions. It checks
  source against a version number; running that version is
  your job.

## Who it is for

Anyone shipping Python to more than one machine: a developer
whose laptop runs 3.12 while the server runs 3.9, a team
adding a CI step that fails the build when someone lands a
`match` statement in a 3.9 project, or a library author who
promises an old minimum version and wants proof the code
keeps it. A version slip is invisible in the file itself —
this catches it before it goes live.

## How this differs from similar tools

The exact name `python-version-checker-cli` matches 0
repositories on GitHub (checked Nov 10, 2026), and the wider
field is noise: `python version checker` matches 209
repositories, and the top ones are about checking some other
thing's version — a serial-number checker written in Python,
an Android Play Market version checker, an MCP server with a
version-checker tool inside, a macOS firmware version
checker, and a pre-commit hook that checks a package does
not refer to different versions of itself. No rival checks
Python source against `requires-python`. This tool does that
one job: a Python standard-library-only CLI that reads the
declared minimum from `pyproject.toml`, parses every file
under that version, and exits 1 for CI — no install beyond
Python, no website, no network.

## Install

Python standard library only — no packages to download. You need
Python 3.8 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/python-version-checker-cli.git
cd python-version-checker-cli
python3 src/python_version_checker.py examples/good.py
```

```
examples/good.py: OK
OK — 1 file(s) checked against Python 3.9 (requires-python in examples/pyproject.toml), all parse under that version.
```

## Usage

Check one file — the target comes from `requires-python` in
the nearest `pyproject.toml` (here `>=3.9`):

```
python3 src/python_version_checker.py examples/good.py
```

```
examples/good.py: OK
OK — 1 file(s) checked against Python 3.9 (requires-python in examples/pyproject.toml), all parse under that version.
```

Check a file that uses a `match` statement, which needs
Python 3.10:

```
python3 src/python_version_checker.py examples/uses_match.py
```

```
FAIL examples/uses_match.py:12: Pattern matching is only supported in Python 3.10 and greater
Checked 1 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 1 problem(s) in 1 file(s).
```

Check a file that uses a `type` statement, which needs
Python 3.12:

```
python3 src/python_version_checker.py examples/uses_type_statement.py
```

```
FAIL examples/uses_type_statement.py:4: Type statement is only supported in Python 3.12 and greater
Checked 1 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 1 problem(s) in 1 file(s).
```

Check a whole folder:

```
python3 src/python_version_checker.py examples/
```

```
examples/good.py: OK
FAIL examples/uses_match.py:12: Pattern matching is only supported in Python 3.10 and greater
FAIL examples/uses_type_statement.py:4: Type statement is only supported in Python 3.12 and greater
examples/no_version/sample.py: OK
Checked 4 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 2 problem(s) in 2 file(s).
```

The same folder against Python 3.12 — everything passes:

```
python3 src/python_version_checker.py --target 3.12 examples/
```

```
examples/good.py: OK
examples/uses_match.py: OK
examples/uses_type_statement.py: OK
examples/no_version/sample.py: OK
OK — 4 file(s) checked against Python 3.12 (--target 3.12), all parse under that version.
```

A project with no `requires-python` stops with exit 2, and
says what to do:

```
python3 src/python_version_checker.py examples/no_version/
```

```
error: no requires-python found and no --target given — there is no version to check against. Add requires-python to pyproject.toml or pass --target, for example --target 3.9.
```

Check one file from standard input:

```
echo 'match x:
    case 1:
        pass' | python3 src/python_version_checker.py --stdin --target 3.9
```

```
FAIL <stdin>:3: Pattern matching is only supported in Python 3.10 and greater
Checked 1 file(s) against Python 3.9 (--target 3.9), 1 problem(s) in 1 file(s).
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/python_version_checker.py --json examples/uses_match.py
```

```
{
  "files": [
    {
      "file": "examples/uses_match.py",
      "problems": [
        {
          "line": 12,
          "reason": "Pattern matching is only supported in Python 3.10 and greater"
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "files_with_problems": 1,
    "problems": 1,
    "skipped": 0,
    "target": "3.9",
    "target_source": "requires-python in examples/pyproject.toml"
  }
}
```

Exit codes: 0 when every checked file parses under the target
version, 1 when any file uses newer syntax (or cannot be read
or parsed at all), 2 for a usage problem (no `requires-python`
and no `--target`, a bad `--target` value, a missing path, or
no Python files to check).

## Examples

### 1. A project folder against its own declared minimum

`examples/` holds a `pyproject.toml` with
`requires-python = ">=3.9"` and four Python files. Two pass,
two fail — a `match` statement and a `type` statement:

```
python3 src/python_version_checker.py examples/
```

```
examples/good.py: OK
FAIL examples/uses_match.py:12: Pattern matching is only supported in Python 3.10 and greater
FAIL examples/uses_type_statement.py:4: Type statement is only supported in Python 3.12 and greater
examples/no_version/sample.py: OK
Checked 4 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 2 problem(s) in 2 file(s).
```

### 2. The same folder, checked against 3.12 instead

`--target` wins over `pyproject.toml`, so the same four files
all pass:

```
python3 src/python_version_checker.py --target 3.12 examples/
```

```
examples/good.py: OK
examples/uses_match.py: OK
examples/uses_type_statement.py: OK
examples/no_version/sample.py: OK
OK — 4 file(s) checked against Python 3.12 (--target 3.12), all parse under that version.
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks one good file (pass), then the `match`
file (fail, on purpose), then the whole `examples/` folder
(fail, on purpose — it picks up the `match` file and the
`type` statement file), then the same folder against 3.12
(pass). Its full output is in
`examples/sample-output.md`, ending with `OK — 4 file(s)
checked against Python 3.12 (--target 3.12), all parse under
that version.` The failing runs exit 1, which is the
expected result — the script ends with exit 0 so it can be
run as a demo.

## How it is tested

Tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_python_version_checker.py
```

The tests cover: target parsing (`3.9` to `3.14`, bad values
rejected), `requires-python` specs (`>=3.9`, `>=3.9,<3.13`,
`~=3.10`, `==3.11.*`, single and double quotes, no version),
finding the nearest `pyproject.toml` by walking up, the
syntax check itself (`match` needs 3.10, `type` statement
needs 3.12, `except*` needs 3.11, walrus needs 3.8, a real
syntax error, empty source, and the honest limit that an
`int | str` annotation parses under 3.9), file checks
(unreadable files, missing files, input files left
unchanged), the CLI (exit 0/1/2, `--target` winning over
`pyproject.toml`, no `requires-python` stopping with exit 2,
bad targets, missing paths, folder walks skipping `.git` and
`__pycache__`, `--no-recursive`, `--exclude`, a direct file
checked even if excluded, no Python files, `--stdin` good
and bad, `--json` output, `--version`, bad flags), the bundled
examples (sample output compared byte-for-byte against a
fresh run, and the README-quoted outputs checked against
it), and hygiene checks (no placeholder text, no absolute
paths, stdlib imports only, `.env` first in `.gitignore`, CI
file runs the test file).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking code against a declared Python version is not new —
the similar tools named above (version checkers for other
things) are listed in "How this differs" — but every line of
code here is original, and the tool builds on nothing but
Python's standard library.

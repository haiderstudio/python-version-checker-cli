#!/usr/bin/env python3
"""Check Python files parse under the minimum version in pyproject.toml.

Run: python3 src/python_version_checker.py examples/
     python3 src/python_version_checker.py --target 3.9 examples/
     python3 src/python_version_checker.py --target 3.11 src/

The problem is quiet: code that uses a 3.12 feature while the
project declares Python 3.9 passes every local test (the author
runs 3.12) and breaks on the server, in CI, or on a teammate's
machine with a bare SyntaxError. This tool reads the minimum
version from pyproject.toml (requires-python), then parses every
Python file with ast.parse(source, feature_version=(x, y)) for
that version. A file that uses newer syntax fails the parse, and
the tool reports it with its file and line and exits 1, so it
can fail a CI run. A clean folder exits 0.

The minimum version comes from requires-python in pyproject.toml,
or from --target, which wins over pyproject.toml. With no
requires-python anywhere and no --target, the tool stops with
exit 2 and says so plainly: there is no version to check
against, and guessing the running version would pass every file
and prove nothing. A single file can also be checked, and a
folder is walked recursively for .py files.

It never rewrites a file. It is report-only and runs fully
offline: it sends nothing anywhere and needs no API key.

What it catches: syntax the parser rejects under the target
version — match statements (3.10), the type statement (3.12),
except* (3.11), assignment expressions (3.8), positional-only
parameters (3.8), and the like. What it does NOT catch: code
that parses fine but only runs on a newer version — for
example, an int | str annotation parses under 3.9 and only
fails at run time, and a call to a library function added in
3.11 parses under every version. Those are not syntax, so no
parser check can catch them.

Exit codes: 0 when every checked file parses under the target
version, 1 when any file uses newer syntax (or cannot be read
or parsed at all), 2 for a usage or input problem (a missing
path, a bad flag, a bad --target value, no requires-python and
no --target, or no Python files to check).

Python standard library only.
"""

import argparse
import ast
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

VERSION = "1.0.0"

REQUIRES_PYTHON_RE = re.compile(
    r"""requires-python\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)
VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
TARGET_RE = re.compile(r"^(\d+)\.(\d+)$")
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".tox", "node_modules"}


def display_path(path):
    """Return path as given, or relative to the working folder if absolute.

    The report must never print an absolute local path: a README
    quoting the output would carry one, and the same run on
    another machine would print a different one.
    """
    text = str(path)
    try:
        return str(Path(text).relative_to(Path.cwd()))
    except ValueError:
        return text


def parse_target(text):
    """Return a (major, minor) tuple for "3.9", or None if it is not one."""
    match = TARGET_RE.match(text.strip())
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2))
    if major != 3 or minor < 6 or minor > 14:
        return None
    return (major, minor)


def format_version(version):
    """Return "3.9" for (3, 9)."""
    return "%d.%d" % version


def minimum_from_spec(spec):
    """Return the lowest version in a requires-python spec, or None.

    ">=3.9,<3.13" gives (3, 9); "~=3.10" gives (3, 10);
    "==3.11.*" gives (3, 11); ">=3.8" gives (3, 8). A spec
    with no version number in it gives None.
    """
    versions = []
    for match in VERSION_RE.finditer(spec):
        versions.append((int(match.group(1)), int(match.group(2))))
    if not versions:
        return None
    return min(versions)


def read_requires_python(pyproject_path):
    """Return the target version from a pyproject.toml, or None.

    The file is read as plain text and the requires-python line
    is found with a regular expression, so this works on any
    Python version — tomllib only exists from 3.11 on. A file
    with no requires-python line gives None.
    """
    try:
        text = pyproject_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = REQUIRES_PYTHON_RE.search(text)
    if not match:
        return None
    return minimum_from_spec(match.group(1))


def find_pyproject(start):
    """Return the nearest pyproject.toml at or above start, or None.

    start may be a file or a folder. The search walks up from
    the folder holding it, and stops at the filesystem root.
    """
    folder = start if start.is_dir() else start.parent
    folder = folder.resolve()
    while True:
        candidate = folder / "pyproject.toml"
        if candidate.is_file():
            return candidate
        if folder.parent == folder:
            return None
        folder = folder.parent


def collect_files(paths, recursive, excludes):
    """Return (files, skipped) for the given paths.

    A .py file is checked as given. A folder is walked for .py
    files, skipping .git, __pycache__, .venv, venv, .tox, and
    node_modules, and never following directory links. A file
    passed directly is always checked, even if it matches an
    exclude pattern. A file with no .py ending that is passed
    directly is still parsed as Python.
    """
    files = []
    skipped = 0
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            if recursive:
                for root, dirs, names in os.walk(path, followlinks=False):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                    for name in sorted(names):
                        if not name.endswith(".py"):
                            continue
                        candidate = Path(root) / name
                        if any(
                            fnmatch.fnmatch(candidate.name, pat)
                            or fnmatch.fnmatch(str(candidate), pat)
                            for pat in excludes
                        ):
                            skipped += 1
                            continue
                        files.append(candidate)
            else:
                for name in sorted(os.listdir(path)):
                    candidate = path / name
                    if candidate.is_file() and name.endswith(".py"):
                        if any(
                            fnmatch.fnmatch(candidate.name, pat)
                            or fnmatch.fnmatch(str(candidate), pat)
                            for pat in excludes
                        ):
                            skipped += 1
                            continue
                        files.append(candidate)
            continue
        return None, None
    return files, skipped


def check_source(source, target):
    """Return a list of (line, reason) problems for one source string.

    ast.parse with feature_version raises SyntaxError on syntax
    newer than the target, and the error carries the line.
    """
    try:
        ast.parse(source, feature_version=target)
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [(line, exc.msg or "does not parse")]
    return []


def check_file(path, target):
    """Return a list of (line, reason) problems for one file."""
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [(0, "cannot read file (not valid UTF-8)")]
    except OSError as exc:
        return [(0, "cannot read file (%s)" % exc.strerror)]
    return check_source(source, target)


def check_stdin(target):
    """Return a list of (line, reason) problems for standard input."""
    try:
        data = sys.stdin.buffer.read()
    except OSError as exc:
        return [(0, "cannot read standard input (%s)" % exc.strerror)]
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return [(0, "cannot read standard input (not valid UTF-8)")]
    return check_source(source, target)


def build_parser():
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="python_version_checker",
        description=(
            "Check Python files parse under the minimum version "
            "declared in pyproject.toml (requires-python)."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Python files or folders to check (default: current folder)",
    )
    parser.add_argument(
        "--target",
        metavar="VERSION",
        default=None,
        help="minimum Python version to check against, for example 3.9 "
        "(wins over requires-python in pyproject.toml)",
    )
    parser.add_argument(
        "--pyproject",
        metavar="PATH",
        default=None,
        help="pyproject.toml to read requires-python from "
        "(default: nearest one at or above the checked path)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders",
    )
    parser.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        help="skip files matching this glob (repeatable; a file passed "
        "directly is always checked)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="check Python source from standard input instead of files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as machine-readable JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + VERSION,
    )
    return parser


def main(argv=None):
    """Run the checker. Returns an exit code: 0 clean, 1 problems, 2 usage."""
    parser = build_parser()
    args = parser.parse_args(argv)

    target = None
    target_source = None
    if args.target is not None:
        target = parse_target(args.target)
        if target is None:
            print(
                "error: --target must be a Python version like 3.9 "
                "(3.6 to 3.14), got %r" % args.target,
                file=sys.stderr,
            )
            return 2
        target_source = "--target %s" % format_version(target)

    paths = args.paths or ["."]
    if args.stdin:
        if target is None:
            pyproject = None
            if args.pyproject is not None:
                pyproject = Path(args.pyproject)
                if not pyproject.is_file():
                    print(
                        "error: --pyproject file not found: %s" % args.pyproject,
                        file=sys.stderr,
                    )
                    return 2
            else:
                pyproject = find_pyproject(Path.cwd())
            if pyproject is not None:
                target = read_requires_python(pyproject)
                if target is not None:
                    target_source = "requires-python in %s" % display_path(pyproject)
        if target is None:
            print(
                "error: no requires-python found and no --target given — "
                "there is no version to check against. Add "
                "requires-python to pyproject.toml or pass --target, "
                "for example --target 3.9.",
                file=sys.stderr,
            )
            return 2
        problems = check_stdin(target)
        results = [{"file": "<stdin>", "problems": problems}]
        checked = 1
        skipped = 0
    else:
        for raw in paths:
            if not Path(raw).exists():
                print("error: path not found: %s" % raw, file=sys.stderr)
                return 2
        if target is None:
            pyproject = None
            if args.pyproject is not None:
                pyproject = Path(args.pyproject)
                if not pyproject.is_file():
                    print(
                        "error: --pyproject file not found: %s" % args.pyproject,
                        file=sys.stderr,
                    )
                    return 2
            else:
                for raw in paths:
                    found = find_pyproject(Path(raw))
                    if found is not None:
                        pyproject = found
                        break
                if pyproject is None:
                    pyproject = find_pyproject(Path.cwd())
            if pyproject is not None:
                target = read_requires_python(pyproject)
                if target is not None:
                    target_source = "requires-python in %s" % display_path(pyproject)
        if target is None:
            print(
                "error: no requires-python found and no --target given — "
                "there is no version to check against. Add "
                "requires-python to pyproject.toml or pass --target, "
                "for example --target 3.9.",
                file=sys.stderr,
            )
            return 2
        collected = collect_files(paths, not args.no_recursive, args.exclude)
        files, skipped = collected
        if files is None:
            print("error: path not found: %s" % paths, file=sys.stderr)
            return 2
        if not files:
            print(
                "error: no Python files to check in: %s" % ", ".join(paths),
                file=sys.stderr,
            )
            return 2
        results = []
        for path in files:
            results.append(
                {"file": str(path), "problems": check_file(path, target)}
            )
        checked = len(files)

    total_problems = sum(len(r["problems"]) for r in results)
    files_with_problems = sum(1 for r in results if r["problems"])

    if args.json:
        payload = {
            "files": [
                {
                    "file": r["file"],
                    "problems": [
                        {"line": line, "reason": reason}
                        for line, reason in r["problems"]
                    ],
                }
                for r in results
            ],
            "summary": {
                "checked": checked,
                "files_with_problems": files_with_problems,
                "problems": total_problems,
                "skipped": skipped,
                "target": format_version(target),
                "target_source": target_source,
            },
        }
        print(json.dumps(payload, indent=2))
        print(
            "Checked %d file(s) against Python %s (%s), "
            "%d problem(s) in %d file(s)."
            % (
                checked,
                format_version(target),
                target_source,
                total_problems,
                files_with_problems,
            ),
            file=sys.stderr,
        )
    else:
        for result in results:
            if result["problems"]:
                for line, reason in result["problems"]:
                    if line:
                        print(
                            "FAIL %s:%d: %s"
                            % (result["file"], line, reason)
                        )
                    else:
                        print("FAIL %s — %s" % (result["file"], reason))
            else:
                print("%s: OK" % result["file"])
        if total_problems == 0:
            print(
                "OK — %d file(s) checked against Python %s (%s), "
                "all parse under that version."
                % (checked, format_version(target), target_source)
            )
        else:
            print(
                "Checked %d file(s) against Python %s (%s), "
                "%d problem(s) in %d file(s)."
                % (
                    checked,
                    format_version(target),
                    target_source,
                    total_problems,
                    files_with_problems,
                )
            )

    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())

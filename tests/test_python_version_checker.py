#!/usr/bin/env python3
"""Tests for python-version-checker-cli. Standard library unittest only.

Run from the repo root: python3 tests/test_python_version_checker.py
"""

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import python_version_checker as pvc  # noqa: E402

ALLOWED_STDLIB = {
    "argparse",
    "ast",
    "fnmatch",
    "json",
    "os",
    "re",
    "sys",
    "pathlib",
}


def run_cli(argv, stdin_bytes=None):
    """Run main() in-process and capture (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    old_stdin = sys.stdin
    if stdin_bytes is not None:
        sys.stdin = _FakeStdin(stdin_bytes)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = pvc.main(argv)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 0
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


class _FakeStdin:
    """Minimal stdin with a .buffer, for --stdin tests."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


def write(path, text):
    """Write text to path, creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


MATCH_SRC = "match x:\n    case 1:\n        pass\n"
TYPE_SRC = "type X = int\n"
EXCEPT_STAR_SRC = "try:\n    pass\nexcept* ValueError:\n    pass\n"
WALRUS_SRC = "if (n := 5):\n    pass\n"
GOOD_SRC = "def greet(name):\n    return 'Hello, ' + name\n"


class TestTargetParsing(unittest.TestCase):
    def test_plain_versions(self):
        self.assertEqual(pvc.parse_target("3.9"), (3, 9))
        self.assertEqual(pvc.parse_target("3.12"), (3, 12))
        self.assertEqual(pvc.parse_target(" 3.10 "), (3, 10))

    def test_bad_targets(self):
        for bad in ("banana", "3", "3.9.1", "2.7", "3.5", "3.15", "3.x", ""):
            self.assertIsNone(pvc.parse_target(bad), bad)

    def test_format_version(self):
        self.assertEqual(pvc.format_version((3, 9)), "3.9")
        self.assertEqual(pvc.format_version((3, 12)), "3.12")


class TestRequiresPython(unittest.TestCase):
    def test_spec_forms(self):
        self.assertEqual(pvc.minimum_from_spec(">=3.9"), (3, 9))
        self.assertEqual(pvc.minimum_from_spec(">=3.9,<3.13"), (3, 9))
        self.assertEqual(pvc.minimum_from_spec("~=3.10"), (3, 10))
        self.assertEqual(pvc.minimum_from_spec("==3.11.*"), (3, 11))
        self.assertEqual(pvc.minimum_from_spec(">=3.8, <3.12"), (3, 8))
        self.assertEqual(pvc.minimum_from_spec(">3.9"), (3, 9))

    def test_spec_with_no_version(self):
        self.assertIsNone(pvc.minimum_from_spec("any"))
        self.assertIsNone(pvc.minimum_from_spec(""))

    def test_read_requires_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pyproject = write(
                folder / "pyproject.toml",
                '[project]\nrequires-python = ">=3.9"\n',
            )
            self.assertEqual(pvc.read_requires_python(pyproject), (3, 9))
            plain = write(folder / "plain.toml", '[project]\nname = "x"\n')
            self.assertIsNone(pvc.read_requires_python(plain))
            self.assertIsNone(
                pvc.read_requires_python(folder / "missing.toml")
            )

    def test_read_requires_python_single_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pyproject = write(
                folder / "pyproject.toml",
                "[project]\nrequires-python = '>=3.10'\n",
            )
            self.assertEqual(pvc.read_requires_python(pyproject), (3, 10))

    def test_find_pyproject_walks_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "pyproject.toml", 'requires-python = ">=3.9"\n')
            deep = root / "a" / "b"
            deep.mkdir(parents=True)
            found = pvc.find_pyproject(deep / "code.py")
            self.assertEqual(found, (root / "pyproject.toml").resolve())

    def test_find_pyproject_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(pvc.find_pyproject(Path(tmp) / "code.py"))


class TestCheckSource(unittest.TestCase):
    def test_good_source_passes_every_target(self):
        for target in ((3, 8), (3, 9), (3, 12)):
            self.assertEqual(pvc.check_source(GOOD_SRC, target), [])

    def test_match_needs_310(self):
        self.assertEqual(pvc.check_source(MATCH_SRC, (3, 10)), [])
        self.assertEqual(pvc.check_source(MATCH_SRC, (3, 12)), [])
        problems = pvc.check_source(MATCH_SRC, (3, 9))
        self.assertEqual(len(problems), 1)
        self.assertIn("3.10", problems[0][1])

    def test_type_statement_needs_312(self):
        self.assertEqual(pvc.check_source(TYPE_SRC, (3, 12)), [])
        problems = pvc.check_source(TYPE_SRC, (3, 11))
        self.assertEqual(len(problems), 1)
        self.assertIn("3.12", problems[0][1])

    def test_except_star_needs_311(self):
        self.assertEqual(pvc.check_source(EXCEPT_STAR_SRC, (3, 11)), [])
        problems = pvc.check_source(EXCEPT_STAR_SRC, (3, 10))
        self.assertEqual(len(problems), 1)
        self.assertIn("3.11", problems[0][1])

    def test_walrus_needs_38(self):
        self.assertEqual(pvc.check_source(WALRUS_SRC, (3, 8)), [])
        problems = pvc.check_source(WALRUS_SRC, (3, 7))
        self.assertEqual(len(problems), 1)
        self.assertIn("3.8", problems[0][1])

    def test_real_syntax_error_is_a_problem(self):
        problems = pvc.check_source("def broken(:\n", (3, 12))
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], 1)

    def test_empty_source_passes(self):
        self.assertEqual(pvc.check_source("", (3, 9)), [])

    def test_union_annotation_parses_under_39(self):
        # Honest limit: int | str parses under 3.9 and only fails
        # at run time, so the parser cannot catch it. The tool
        # must not claim otherwise.
        self.assertEqual(
            pvc.check_source("x: int | str = 1\n", (3, 9)), []
        )


class TestCheckFile(unittest.TestCase):
    def test_good_and_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            good = write(folder / "good.py", GOOD_SRC)
            bad = write(folder / "bad.py", MATCH_SRC)
            self.assertEqual(pvc.check_file(good, (3, 9)), [])
            problems = pvc.check_file(bad, (3, 9))
            self.assertEqual(len(problems), 1)

    def test_unreadable_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            binary = folder / "bad.py"
            binary.write_bytes(b"\xff\xfe\x00bad")
            problems = pvc.check_file(binary, (3, 9))
            self.assertEqual(len(problems), 1)
            self.assertIn("UTF-8", problems[0][1])
            missing = pvc.check_file(folder / "gone.py", (3, 9))
            self.assertEqual(len(missing), 1)

    def test_input_file_is_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            target = write(folder / "bad.py", MATCH_SRC)
            pvc.check_file(target, (3, 9))
            self.assertEqual(target.read_text(encoding="utf-8"), MATCH_SRC)


class TestCli(unittest.TestCase):
    def test_single_good_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", 'requires-python = ">=3.9"\n')
            good = write(folder / "good.py", GOOD_SRC)
            code, out, _ = run_cli([str(good)])
            self.assertEqual(code, 0)
            self.assertIn(": OK", out)
            self.assertIn("Python 3.9", out)

    def test_single_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", 'requires-python = ">=3.9"\n')
            bad = write(folder / "bad.py", MATCH_SRC)
            code, out, _ = run_cli([str(bad)])
            self.assertEqual(code, 1)
            self.assertIn("FAIL %s:" % bad, out)
            self.assertIn("3.10", out)

    def test_target_wins_over_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", 'requires-python = ">=3.9"\n')
            bad = write(folder / "bad.py", MATCH_SRC)
            code, out, _ = run_cli(["--target", "3.10", str(bad)])
            self.assertEqual(code, 0)
            self.assertIn("--target 3.10", out)

    def test_no_requires_python_and_no_target_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", '[project]\nname = "x"\n')
            good = write(folder / "good.py", GOOD_SRC)
            code, _, err = run_cli([str(good)])
            self.assertEqual(code, 2)
            self.assertIn("no requires-python", err)
            self.assertIn("--target 3.9", err)

    def test_no_pyproject_at_all_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            good = write(folder / "good.py", GOOD_SRC)
            code, _, err = run_cli(
                ["--pyproject", str(folder / "nope.toml"), str(good)]
            )
            self.assertEqual(code, 2)
            self.assertIn("not found", err)

    def test_bad_target_is_exit_2(self):
        code, _, err = run_cli(["--target", "banana", "examples/good.py"])
        self.assertEqual(code, 2)
        self.assertIn("--target must be", err)

    def test_missing_path_is_exit_2(self):
        code, _, err = run_cli(["--target", "3.9", "no-such-path.py"])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_folder_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", 'requires-python = ">=3.9"\n')
            write(folder / "good.py", GOOD_SRC)
            write(folder / "sub" / "bad.py", MATCH_SRC)
            write(folder / "sub" / "note.txt", "not python\n")
            write(folder / ".git" / "hidden.py", MATCH_SRC)
            write(folder / "__pycache__" / "cached.py", MATCH_SRC)
            code, out, _ = run_cli([str(folder)])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertNotIn(".git", out)
            self.assertNotIn("__pycache__", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "pyproject.toml", 'requires-python = ">=3.9"\n')
            write(folder / "good.py", GOOD_SRC)
            write(folder / "sub" / "bad.py", MATCH_SRC)
            code, out, _ = run_cli(
                ["--target", "3.9", "--no-recursive", str(folder)]
            )
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_exclude_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "keep.py", GOOD_SRC)
            write(folder / "skip_me.py", MATCH_SRC)
            code, out, _ = run_cli(
                ["--target", "3.9", "--exclude", "skip_*", str(folder)]
            )
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_ignores_exclude(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bad = write(folder / "skip_me.py", MATCH_SRC)
            code, _, _ = run_cli(
                ["--target", "3.9", "--exclude", "skip_*", str(bad)]
            )
            self.assertEqual(code, 1)

    def test_no_python_files_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder / "note.txt", "hello\n")
            code, _, err = run_cli(["--target", "3.9", str(folder)])
            self.assertEqual(code, 2)
            self.assertIn("no Python files", err)

    def test_stdin_good_and_bad(self):
        code, out, _ = run_cli(
            ["--stdin", "--target", "3.9"], stdin_bytes=GOOD_SRC.encode()
        )
        self.assertEqual(code, 0)
        self.assertIn("<stdin>: OK", out)
        code, out, _ = run_cli(
            ["--stdin", "--target", "3.9"], stdin_bytes=MATCH_SRC.encode()
        )
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>:", out)

    def test_stdin_without_target_or_pyproject_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                code, _, err = run_cli(
                    ["--stdin"], stdin_bytes=GOOD_SRC.encode()
                )
            finally:
                os.chdir(old)
            self.assertEqual(code, 2)
            self.assertIn("no requires-python", err)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bad = write(folder / "bad.py", MATCH_SRC)
            code, out, err = run_cli(
                ["--target", "3.9", "--json", str(bad)]
            )
            self.assertEqual(code, 1)
            payload = json.loads(out)
            self.assertEqual(payload["summary"]["checked"], 1)
            self.assertEqual(payload["summary"]["problems"], 1)
            self.assertEqual(payload["summary"]["target"], "3.9")
            self.assertEqual(len(payload["files"][0]["problems"]), 1)
            self.assertIn("Checked 1 file(s)", err)

    def test_version_flag(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", out)

    def test_bad_flag_is_exit_2(self):
        code, _, _ = run_cli(["--nope"])
        self.assertEqual(code, 2)


class TestBundledExamples(unittest.TestCase):
    def test_good_example_passes(self):
        code, out, _ = run_cli(
            [str(REPO_ROOT / "examples" / "good.py")]
        )
        self.assertEqual(code, 0)
        self.assertIn("examples/good.py: OK", out)

    def test_match_example_fails_at_line_12(self):
        code, out, _ = run_cli(
            [str(REPO_ROOT / "examples" / "uses_match.py")]
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "uses_match.py:12: Pattern matching is only supported "
            "in Python 3.10 and greater",
            out,
        )

    def test_type_statement_example_fails(self):
        code, out, _ = run_cli(
            [str(REPO_ROOT / "examples" / "uses_type_statement.py")]
        )
        self.assertEqual(code, 1)
        self.assertIn("Type statement is only supported", out)

    def test_examples_folder(self):
        code, out, _ = run_cli([str(REPO_ROOT / "examples")])
        self.assertEqual(code, 1)
        self.assertIn("Checked 4 file(s)", out)
        self.assertIn("2 problem(s) in 2 file(s)", out)

    def test_examples_folder_at_312(self):
        code, out, _ = run_cli(
            ["--target", "3.12", str(REPO_ROOT / "examples")]
        )
        self.assertEqual(code, 0)
        self.assertIn("4 file(s) checked", out)

    def test_no_version_example_needs_target(self):
        code, _, err = run_cli([str(REPO_ROOT / "examples" / "no_version")])
        self.assertEqual(code, 2)
        self.assertIn("no requires-python", err)

    def test_run_example_script_matches_sample_output(self):
        script = REPO_ROOT / "examples" / "run-example.sh"
        result = subprocess.run(
            ["sh", str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        sample = (REPO_ROOT / "examples" / "sample-output.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(result.stdout, sample)

    def test_readme_quotes_real_output(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for line in (
            "examples/good.py: OK",
            "FAIL examples/uses_match.py:12: Pattern matching is only "
            "supported in Python 3.10 and greater",
            "FAIL examples/uses_type_statement.py:4: Type statement is "
            "only supported in Python 3.12 and greater",
            "Checked 4 file(s) against Python 3.9",
            "2 problem(s) in 2 file(s).",
        ):
            self.assertIn(line, readme, line)


class TestHygiene(unittest.TestCase):
    def test_no_placeholder_text(self):
        banned = ("TODO", "coming soon", "lorem")
        hits = []
        for path in REPO_ROOT.rglob("*"):
            if (
                ".git" in path.parts
                or "__pycache__" in path.parts
                or "tests" in path.parts
            ):
                continue
            if path.is_file() and path.suffix in (
                ".py",
                ".md",
                ".toml",
                ".yml",
                ".sh",
            ):
                text = path.read_text(encoding="utf-8", errors="replace")
                for word in banned:
                    if word in text:
                        hits.append("%s: %s" % (path, word))
        self.assertEqual(hits, [])

    def test_no_absolute_local_paths(self):
        hits = []
        for path in REPO_ROOT.rglob("*"):
            if (
                ".git" in path.parts
                or "__pycache__" in path.parts
                or "tests" in path.parts
            ):
                continue
            if path.is_file() and path.suffix in (
                ".py",
                ".md",
                ".toml",
                ".yml",
                ".sh",
            ):
                text = path.read_text(encoding="utf-8", errors="replace")
                if "/home/" in text or "/Users/" in text or "C:\\" in text:
                    hits.append(str(path))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        source = (REPO_ROOT / "src" / "python_version_checker.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        extra = imports - ALLOWED_STDLIB
        self.assertEqual(extra, set())

    def test_env_first_in_gitignore(self):
        lines = (REPO_ROOT / ".gitignore").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_the_test_file(self):
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("tests/test_python_version_checker.py", ci)
        self.assertIn("setup-python", ci)

    def test_no_secrets(self):
        for path in REPO_ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.is_file() and path.name == ".env":
                self.fail(".env file must not ship: %s" % path)


if __name__ == "__main__":
    unittest.main()

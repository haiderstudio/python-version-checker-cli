== good.py: parses under Python 3.9, passes ==
examples/good.py: OK
OK — 1 file(s) checked against Python 3.9 (requires-python in examples/pyproject.toml), all parse under that version.

== uses_match.py: match needs 3.10, fails against 3.9 ==
FAIL examples/uses_match.py:12: Pattern matching is only supported in Python 3.10 and greater
Checked 1 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 1 problem(s) in 1 file(s).

== examples/: the whole folder against 3.9 ==
examples/good.py: OK
FAIL examples/uses_match.py:12: Pattern matching is only supported in Python 3.10 and greater
FAIL examples/uses_type_statement.py:4: Type statement is only supported in Python 3.12 and greater
examples/no_version/sample.py: OK
Checked 4 file(s) against Python 3.9 (requires-python in examples/pyproject.toml), 2 problem(s) in 2 file(s).

== examples/ against 3.12: everything passes ==
examples/good.py: OK
examples/uses_match.py: OK
examples/uses_type_statement.py: OK
examples/no_version/sample.py: OK
OK — 4 file(s) checked against Python 3.12 (--target 3.12), all parse under that version.

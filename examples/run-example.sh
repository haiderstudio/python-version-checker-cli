#!/bin/sh
# Check the bundled examples. The failing runs exit 1 on purpose,
# so each one ends with "|| true"; the script itself ends with
# exit 0 so it can be run as a demo. Run from the repo root:
# sh examples/run-example.sh
cd "$(dirname "$0")/.."
echo "== good.py: parses under Python 3.9, passes =="
python3 src/python_version_checker.py examples/good.py || true
echo
echo "== uses_match.py: match needs 3.10, fails against 3.9 =="
python3 src/python_version_checker.py examples/uses_match.py || true
echo
echo "== examples/: the whole folder against 3.9 =="
python3 src/python_version_checker.py examples/ || true
echo
echo "== examples/ against 3.12: everything passes =="
python3 src/python_version_checker.py --target 3.12 examples/ || true

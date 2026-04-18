# dev_scripts

Ad-hoc exploration scripts, not tests.

These files were previously at `backend/test_*.py` but had 0 pytest assertions —
they print `"PASS"` / `"FAIL"` strings based on thresholds they set themselves,
but exit 0 unconditionally, so pytest would collect them and report them as
passing regardless of what they printed. That made the test suite misleading.

They are kept here for manual, interactive use during development. They are
NOT run by CI and should NOT be imported by real tests.

Real tests live in `backend/tests/` and use `unittest`/`pytest` assertions.

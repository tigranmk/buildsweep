import contextlib
import io
import json
import os
import unittest
from unittest import mock

from buildsweep.cli import main, parse_age, parse_selection, parse_size

from helpers import TempTree


def run(*argv, stdin_tty=False, answers=()):
    out, err = io.StringIO(), io.StringIO()
    replies = iter(answers)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
         mock.patch("sys.stdin.isatty", return_value=stdin_tty), \
         mock.patch("builtins.input", side_effect=lambda _p: next(replies)):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(parse_size("500"), 500)
        self.assertEqual(parse_size("10k"), 10 * 1024)
        self.assertEqual(parse_size("1.5M"), int(1.5 * 1024 ** 2))
        self.assertEqual(parse_size("2GiB"), 2 * 1024 ** 3)
        self.assertEqual(parse_size("100MB"), 100 * 1024 ** 2)

    def test_ages(self):
        self.assertEqual(parse_age("30"), 30)
        self.assertEqual(parse_age("2w"), 14)
        self.assertEqual(parse_age("6m"), 180)
        self.assertEqual(parse_age("1y"), 365)
        self.assertEqual(parse_age("12h"), 0.5)

    def test_selection(self):
        self.assertEqual(parse_selection("1,3,5-6", 6), [0, 2, 4, 5])
        self.assertEqual(parse_selection("all", 3), [0, 1, 2])
        self.assertEqual(parse_selection("3-2", 3), [1, 2])
        with self.assertRaises(ValueError):
            parse_selection("9", 3)
        with self.assertRaises(ValueError):
            parse_selection("x", 3)


class CliTests(TempTree):
    def setUp(self):
        super().setUp()
        self.old = self.project("old", ["package.json"], "node_modules", size=200_000, age_days=400)
        self.new = self.project("new", ["Cargo.toml"], "target", size=10_000, age_days=1)

    def test_report_is_default_and_changes_nothing(self):
        code, out, _ = run(self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("Found 2 folders", out)
        self.assertTrue(os.path.isdir(self.old) and os.path.isdir(self.new))

    def test_filters_by_age_and_size(self):
        _, out, _ = run(self.tmp, "--older-than", "6m")
        self.assertIn("old/node_modules", out)
        self.assertNotIn("new/target", out)
        self.assertIn("1 more did not pass", out)
        _, out, _ = run(self.tmp, "--min-size", "100k")
        self.assertNotIn("new/target", out)

    def test_only_and_skip(self):
        _, out, _ = run(self.tmp, "--only", "rust")
        self.assertIn("new/target", out)
        self.assertNotIn("node_modules", out)
        _, out, _ = run(self.tmp, "--skip", "rust")
        self.assertNotIn("new/target", out)

    def test_unknown_type_is_usage_error(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            main([self.tmp, "--only", "cobol"])
        self.assertEqual(cm.exception.code, 2)

    def test_json_output(self):
        _, out, _ = run(self.tmp, "--format", "json")
        data = json.loads(out)
        self.assertEqual(data["summary"]["folders"], 2)
        self.assertEqual({a["ecosystem"] for a in data["artifacts"]}, {"node", "rust"})

    def test_refuses_without_terminal_or_yes(self):
        code, _, err = run(self.tmp, "--action", "delete")
        self.assertEqual(code, 1)
        self.assertIn("Aborted", err)
        self.assertTrue(os.path.isdir(self.old))

    def test_delete_with_yes(self):
        code, out, _ = run(self.tmp, "--action", "delete", "--older-than", "6m", "--yes")
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.old))
        self.assertTrue(os.path.isdir(self.new))
        self.assertIn("Freed", out)

    def test_dry_run(self):
        code, out, _ = run(self.tmp, "--action", "delete", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would delete", out)
        self.assertTrue(os.path.isdir(self.old))

    def test_interactive_pick_and_confirm(self):
        # Rows are sorted by size: [1] old/node_modules, [2] new/target.
        code, out, _ = run(self.tmp, "-i", "--action", "delete",
                           stdin_tty=True, answers=["2", "y"])
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isdir(self.old))
        self.assertFalse(os.path.exists(self.new))

    def test_interactive_retries_bad_input_and_cancels(self):
        code, out, _ = run(self.tmp, "-i", stdin_tty=True, answers=["99", ""])
        self.assertEqual(code, 0)
        self.assertIn("outside 1-2", out)
        self.assertIn("Nothing removed", out)
        self.assertTrue(os.path.isdir(self.old) and os.path.isdir(self.new))

    def test_list_rules(self):
        code, out, _ = run("--list-rules")
        self.assertEqual(code, 0)
        self.assertIn("Cargo.toml", out)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest
from unittest import mock

from buildsweep import actions
from buildsweep.scanner import scan

from helpers import TempTree


class ActionTests(TempTree):
    def setUp(self):
        super().setUp()
        self.target = self.project("p", ["Cargo.toml"], "target")
        (self.artifact,) = scan([self.tmp]).artifacts

    def test_delete_removes_folder(self):
        (r,) = actions.apply_all([self.artifact], "delete")
        self.assertTrue(r.ok, r.message)
        self.assertFalse(os.path.exists(self.target))
        self.assertTrue(os.path.exists(self.p("p/Cargo.toml")))

    def test_delete_handles_read_only_files(self):
        os.chmod(self.p("p/target/blob.bin"), 0o444)
        os.chmod(self.target, 0o555)
        (r,) = actions.apply_all([self.artifact], "delete")
        self.assertTrue(r.ok, r.message)

    def test_dry_run_changes_nothing(self):
        (r,) = actions.apply_all([self.artifact], "delete", dry_run=True)
        self.assertTrue(r.ok)
        self.assertTrue(os.path.isdir(self.target))

    def test_skips_when_marker_removed_after_scan(self):
        os.remove(self.p("p/Cargo.toml"))
        (r,) = actions.apply_all([self.artifact], "delete")
        self.assertFalse(r.ok)
        self.assertIn("markers changed", r.message)
        self.assertTrue(os.path.isdir(self.target))

    @unittest.skipIf(sys.platform == "win32", "needs POSIX links/inodes")
    def test_skips_when_replaced_by_symlink(self):
        os.rename(self.target, self.p("elsewhere"))
        os.symlink(self.p("elsewhere"), self.target)
        (r,) = actions.apply_all([self.artifact], "delete")
        self.assertFalse(r.ok)
        self.assertTrue(os.path.isdir(self.p("elsewhere")))

    def test_trash_fallback_without_finder(self):
        moved = []
        with mock.patch.object(actions, "finder_available", return_value=False), \
             mock.patch.object(actions, "trash_one", side_effect=lambda p: moved.append(p) or "moved"):
            (r,) = actions.apply_all([self.artifact], "trash")
        self.assertTrue(r.ok)
        self.assertEqual(moved, [self.target])

    def test_finder_refusal_falls_back(self):
        moved = []
        with mock.patch.object(actions, "finder_available", return_value=True), \
             mock.patch.object(actions, "finder_trash", return_value="blocked"), \
             mock.patch.object(actions, "trash_one", side_effect=lambda p: moved.append(p) or "moved"), \
             mock.patch("sys.stderr"):
            (r,) = actions.apply_all([self.artifact], "trash")
        self.assertTrue(r.ok)
        self.assertEqual(moved, [self.target])


if __name__ == "__main__":
    unittest.main()

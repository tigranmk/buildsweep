import os
import sys
import unittest

from buildsweep.scanner import scan

from helpers import TempTree


class ScanTests(TempTree):
    def paths(self, result):
        return sorted(os.path.relpath(a.path, self.tmp).replace(os.sep, "/") for a in result.artifacts)

    def test_finds_artifacts_across_ecosystems(self):
        self.project("web", ["package.json"], "node_modules")
        self.project("cli", ["Cargo.toml"], "target")
        self.write("api/.venv/pyvenv.cfg")
        self.assertEqual(self.paths(scan([self.tmp])),
                         ["api/.venv", "cli/target", "web/node_modules"])

    def test_does_not_descend_into_artifacts(self):
        self.project("web", ["package.json"], "node_modules")
        self.write("web/node_modules/dep/package.json")
        self.write("web/node_modules/dep/node_modules/x/index.js")
        self.assertEqual(self.paths(scan([self.tmp])), ["web/node_modules"])

    def test_measures_size_and_files(self):
        self.project("web", ["package.json"], "node_modules", size=100_000)
        (a,) = scan([self.tmp]).artifacts
        self.assertEqual(a.files, 1)
        self.assertGreaterEqual(a.size, 100_000)

    @unittest.skipIf(sys.platform == "win32", "needs POSIX links/inodes")
    def test_hard_links_counted_once(self):
        self.project("a", ["package.json"], "node_modules", size=50_000)
        os.makedirs(self.p("b/node_modules"))
        self.write("b/package.json")
        os.link(self.p("a/node_modules/blob.bin"), self.p("b/node_modules/blob.bin"))
        total = sum(a.size for a in scan([self.tmp]).artifacts)
        self.assertLess(total, 100_000)

    def test_last_active_comes_from_source_files_not_artifact(self):
        self.project("old", ["package.json"], "node_modules", age_days=200)
        self.write("old/src/index.js", age_days=120)
        (a,) = scan([self.tmp]).artifacts
        # The artifact itself was just written; activity is the newest source file.
        self.assertAlmostEqual(a.age_days(), 120, delta=1)

    def test_git_activity_is_ignored(self):
        self.project("p", ["Cargo.toml"], "target", age_days=300)
        self.write("p/.git/FETCH_HEAD")  # fresh fetch
        (a,) = scan([self.tmp]).artifacts
        self.assertGreater(a.age_days(), 299)

    def test_folder_that_is_a_repository_is_not_an_artifact(self):
        self.project("p", ["Cargo.toml"], "target")
        os.makedirs(self.p("p/target/.git"))
        self.assertEqual(scan([self.tmp]).artifacts, [])

    @unittest.skipIf(sys.platform == "win32", "needs POSIX links/inodes")
    def test_symlinked_directories_are_not_followed(self):
        self.project("real", ["package.json"], "node_modules")
        os.makedirs(self.p("links"))
        os.symlink(self.p("real"), self.p("links/alias"))
        self.assertEqual(self.paths(scan([self.tmp])), ["real/node_modules"])

    def test_exclude_glob(self):
        self.project("keep/web", ["package.json"], "node_modules")
        self.project("skip/web", ["package.json"], "node_modules")
        self.assertEqual(self.paths(scan([self.tmp], exclude=["skip"])), ["keep/web/node_modules"])

    def test_hidden_folders_skipped_unless_asked(self):
        self.project(".config/tool", ["package.json"], "node_modules")
        self.assertEqual(scan([self.tmp]).artifacts, [])
        self.assertEqual(len(scan([self.tmp], hidden=True).artifacts), 1)

    def test_missing_root_is_reported_not_raised(self):
        result = scan([self.p("nope")])
        self.assertEqual(result.artifacts, [])
        self.assertEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()

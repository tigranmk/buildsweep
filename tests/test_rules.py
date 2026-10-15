import os
import unittest

from buildsweep.rules import RULES, match

from helpers import TempTree


class RuleMatchTests(TempTree):
    def check(self, markers, artifact, expected):
        path = self.project("proj", markers, artifact)
        rule = match(path, set(os.listdir(self.p("proj"))))
        self.assertEqual(rule.ecosystem if rule else None, expected)

    def test_node_modules_needs_package_json(self):
        self.check(["package.json"], "node_modules", "node")

    def test_node_modules_without_package_json_is_left_alone(self):
        self.check(["README.md"], "node_modules", None)

    def test_rust_target(self):
        self.check(["Cargo.toml"], "target", "rust")

    def test_maven_target(self):
        self.check(["pom.xml"], "target", "java")

    def test_plain_target_folder_is_not_an_artifact(self):
        self.check(["notes.txt"], "target", None)

    def test_dotnet_bin_matches_glob_marker(self):
        self.check(["App.csproj"], "bin", "dotnet")

    def test_bin_without_project_file_is_left_alone(self):
        self.check(["Makefile"], "bin", None)

    def test_gradle_build(self):
        self.check(["build.gradle.kts"], "build", "java")

    def test_virtualenv_needs_pyvenv_cfg_inside(self):
        self.write("proj/.venv/pyvenv.cfg")
        self.assertEqual(match(self.p("proj/.venv"), set()).ecosystem, "python")
        self.write("proj/venv/data.txt")
        self.assertIsNone(match(self.p("proj/venv"), set()))

    def test_cmake_build_needs_cache_inside(self):
        self.write("proj/build/CMakeCache.txt")
        self.assertEqual(match(self.p("proj/build"), {"build"}).ecosystem, "cmake")
        self.write("other/build/output.o")
        self.assertIsNone(match(self.p("other/build"), {"build"}))

    def test_derived_data_needs_xcode_parent(self):
        os.makedirs(self.p("Xcode/DerivedData"))
        os.makedirs(self.p("Elsewhere/DerivedData"))
        self.assertIsNotNone(match(self.p("Xcode/DerivedData"), set()))
        self.assertIsNone(match(self.p("Elsewhere/DerivedData"), set()))

    def test_every_rule_documents_how_to_restore(self):
        for r in RULES:
            self.assertTrue(r.restore, r)


if __name__ == "__main__":
    unittest.main()

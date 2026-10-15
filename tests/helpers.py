"""Shared fixtures for the test suite."""

import os
import shutil
import tempfile
import time
import unittest

DAY = 86400


class TempTree(unittest.TestCase):
    """Gives each test an isolated temporary directory and helpers to build
    fake projects in it."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="buildsweep-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, rel):
        return os.path.join(self.tmp, rel)

    def write(self, rel, data="x", age_days=None):
        """Create a file; `age_days` back-dates its modification time."""
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(data)
        if age_days is not None:
            t = time.time() - age_days * DAY
            os.utime(path, (t, t))
        return path

    def project(self, rel, markers, artifact, size=4096, age_days=0):
        """A project folder with marker files (all `age_days` old) and an
        artifact folder holding one file of `size` bytes."""
        for m in markers:
            self.write(os.path.join(rel, m), age_days=age_days)
        self.write(os.path.join(rel, artifact, "blob.bin"), "a" * size)
        return self.p(os.path.join(rel, artifact))

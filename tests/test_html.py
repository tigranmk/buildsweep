import io
import json
import os
import re
import unittest

from buildsweep.html_report import write_html
from buildsweep.scanner import scan

from test_cli import run
from helpers import TempTree


def embedded_data(page):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


class HtmlReportTests(TempTree):
    def test_page_embeds_every_artifact(self):
        self.project("web", ["package.json"], "node_modules")
        self.project("cli", ["Cargo.toml"], "target")
        out = io.StringIO()
        write_html(scan([self.tmp]).artifacts, out, roots=[self.tmp])
        data = embedded_data(out.getvalue())
        self.assertEqual(sorted(a["shown"] for a in data["artifacts"]),
                         ["cli/target", "web/node_modules"])
        self.assertTrue(all(a["href"].startswith("file://") for a in data["artifacts"]))

    def test_hostile_folder_name_cannot_break_out(self):
        name = "x</script><img src=y onerror=alert(1)>&"
        self.project(name, ["package.json"], "node_modules")
        out = io.StringIO()
        write_html(scan([self.tmp]).artifacts, out, roots=[self.tmp])
        page = out.getvalue()
        self.assertNotIn("<img", page)
        self.assertEqual(page.count("</script>"), 2)  # data block + app script only
        (a,) = embedded_data(page)["artifacts"]
        self.assertIn(name, a["path"])  # still round-trips intact

    def test_empty_report(self):
        out = io.StringIO()
        write_html([], out, roots=[self.tmp])
        self.assertIn("No build or dependency folders found", out.getvalue())


class HtmlCliTests(TempTree):
    def test_writes_file_with_output_option(self):
        self.project("web", ["package.json"], "node_modules")
        target = self.p("report.html")
        code, out, err = run(self.tmp, "--format", "html", "-o", target)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("Wrote", err)
        with open(target, encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("<!doctype html>"))

    def test_html_is_report_only(self):
        self.project("web", ["package.json"], "node_modules")
        code, _, err = run(self.tmp, "--format", "html", "--action", "delete", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("read-only", err)
        self.assertTrue(os.path.isdir(self.p("web/node_modules")))


if __name__ == "__main__":
    unittest.main()

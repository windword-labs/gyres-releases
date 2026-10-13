#!/usr/bin/env python3
"""Tests for mac-appcast.py: run the script as a subprocess in a temp dir."""

import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mac-appcast.py")
SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
NS = {"sparkle": SPARKLE_NS}

SIG = "dGVzdHNpZ25hdHVyZQ=="  # base64("testsignature")


class MacAppcastTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.feed = os.path.join(self.dir.name, "appcast.xml")

    def run_script(self, *extra):
        cmd = [sys.executable, SCRIPT, "--feed", self.feed,
               "--out", self.feed, "--title", "Gyres Mac",
               "--link", "https://example.com/feed",
               "--short-version", "0.1.0",
               "--url", "https://example.com/app.zip",
               "--length", "1234", "--ed-signature", SIG] + list(extra)
        return subprocess.run(cmd, capture_output=True, text=True)

    def insert(self, version, *extra):
        r = self.run_script("--version", str(version), *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def versions(self):
        root = ET.parse(self.feed).getroot()
        return [int(e.text) for e in root.findall(".//sparkle:version", NS)]

    def test_fresh_feed(self):
        self.insert(3)
        root = ET.parse(self.feed).getroot()
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.get("version"), "2.0")
        chan = root.find("channel")
        self.assertEqual(chan.findtext("title"), "Gyres Mac")
        self.assertEqual(chan.findtext("link"), "https://example.com/feed")
        self.assertEqual(chan.findtext("description"), "Gyres Mac")
        self.assertEqual(chan.findtext("language"), "en")
        self.assertEqual(self.versions(), [3])

    def test_second_insert_sorted_descending(self):
        self.insert(1)
        self.insert(5)
        self.assertEqual(self.versions(), [5, 1])

    def test_same_version_replaces(self):
        self.insert(7, "--short-version", "0.1.0")
        self.insert(7, "--short-version", "0.2.0")
        self.assertEqual(self.versions(), [7])
        root = ET.parse(self.feed).getroot()
        titles = [t.text for t in root.findall(".//item/title")]
        self.assertEqual(titles, ["Gyres Mac 0.2.0"])

    def test_keep_trims_lowest(self):
        for v in (1, 2, 3):
            self.insert(v)
        self.insert(4, "--keep", "2")
        self.assertEqual(self.versions(), [4, 3])

    def test_sparkle_prefix_no_ns0(self):
        self.insert(9, "--release-notes-url", "https://example.com/notes.html")
        with open(self.feed, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("sparkle:", text)
        self.assertNotIn("ns0", text)

    def test_parses_and_enclosure_attributes(self):
        self.insert(11, "--minimum-system-version", "13.0",
                    "--pub-date", "Mon, 06 Oct 2025 12:00:00 +0000")
        root = ET.parse(self.feed).getroot()
        item = root.find(".//item")
        self.assertEqual(item.findtext("sparkle:version", namespaces=NS), "11")
        self.assertEqual(item.findtext("sparkle:shortVersionString", namespaces=NS),
                         "0.1.0")
        self.assertEqual(item.findtext("sparkle:minimumSystemVersion", namespaces=NS),
                         "13.0")
        self.assertEqual(item.findtext("pubDate"),
                         "Mon, 06 Oct 2025 12:00:00 +0000")
        enc = item.find("enclosure")
        self.assertEqual(enc.get("url"), "https://example.com/app.zip")
        self.assertEqual(enc.get("length"), "1234")
        self.assertEqual(enc.get("type"), "application/octet-stream")
        self.assertEqual(enc.get("{%s}edSignature" % SPARKLE_NS), SIG)

    def test_rejects_non_https_url(self):
        r = self.run_script("--version", "1", "--url", "http://example.com/app.zip")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_rejects_non_integer_version(self):
        r = self.run_script("--version", "abc")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())

    def test_rejects_bad_base64_signature(self):
        r = self.run_script("--version", "1", "--ed-signature", "not!!valid")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.strip())


if __name__ == "__main__":
    unittest.main()

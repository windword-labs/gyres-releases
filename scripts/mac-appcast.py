#!/usr/bin/env python3
"""Insert one release into a Sparkle 2 appcast (RSS 2.0) and write the result.

This maintains the Gyres Mac Sparkle feeds kept on the appcast branch of this
repo.  The ed25519 signature is produced by Sparkle's `sign_update` on the
macOS build job; this script never sees a key.

Python 3 standard library only.
"""

import argparse
import base64
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from datetime import datetime, timezone

SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"

def spark(name):
    return f"{{{SPARKLE_NS}}}{name}"

ET.register_namespace("sparkle", SPARKLE_NS)


class BadArgs(Exception):
    pass


def parse_args(argv):
    p = argparse.ArgumentParser(description="Insert a release into a Sparkle appcast.")
    p.add_argument("--feed", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--link", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--short-version", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--length", required=True)
    p.add_argument("--ed-signature", required=True)
    p.add_argument("--minimum-system-version", default="14.0")
    p.add_argument("--release-notes-url")
    p.add_argument("--pub-date")
    p.add_argument("--keep", default=10)
    args = p.parse_args(argv)

    if not args.link.startswith("https://"):
        raise BadArgs("--link must be an https URL")
    if not args.url.startswith("https://"):
        raise BadArgs("--url must start with https://")
    try:
        version = int(args.version)
        if version <= 0:
            raise ValueError
    except ValueError:
        raise BadArgs("--version must be a positive integer")
    try:
        length = int(args.length)
        if length <= 0:
            raise ValueError
    except ValueError:
        raise BadArgs("--length must be a positive integer")
    try:
        keep = int(args.keep)
        if keep <= 0:
            raise ValueError
    except ValueError:
        raise BadArgs("--keep must be a positive integer")
    if not args.ed_signature:
        raise BadArgs("--ed-signature must not be empty")
    try:
        base64.b64decode(args.ed_signature, validate=True)
    except Exception:
        raise BadArgs("--ed-signature must be valid base64")
    if args.pub_date is None:
        args.pub_date = format_datetime(datetime.now(timezone.utc))

    args.version = version
    args.length = length
    args.keep = keep
    return args


def item_version(item):
    v = item.find(spark("version"))
    if v is None or not v.text:
        return None
    try:
        return int(v.text)
    except ValueError:
        return None


def load_items(feed_path):
    """Return (existing items as dicts, warns about dropped items)."""
    if not os.path.exists(feed_path):
        return []
    root = ET.parse(feed_path).getroot()
    items = []
    for item in root.findall("./channel/item"):
        v = item_version(item)
        if v is None:
            print("warning: dropping item without a parsable sparkle:version",
                  file=sys.stderr)
            continue
        items.append({"version": v, "element": item})
    return items


def new_item(args):
    item = ET.Element("item")
    ET.SubElement(item, "title").text = f"{args.title} {args.short_version}"
    ET.SubElement(item, "pubDate").text = args.pub_date
    ET.SubElement(item, spark("version")).text = str(args.version)
    ET.SubElement(item, spark("shortVersionString")).text = args.short_version
    ET.SubElement(item, spark("minimumSystemVersion")).text = (
        args.minimum_system_version)
    if args.release_notes_url:
        ET.SubElement(item, spark("releaseNotesLink")).text = (
            args.release_notes_url)
    ET.SubElement(item, "enclosure", {
        "url": args.url,
        "length": str(args.length),
        "type": "application/octet-stream",
        spark("edSignature"): args.ed_signature,
    })
    return item


def build_root(args, items):
    root = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = args.title
    ET.SubElement(channel, "link").text = args.link
    ET.SubElement(channel, "description").text = args.title
    ET.SubElement(channel, "language").text = "en"
    for it in items:
        channel.append(it["element"])
    return root


def write_atomically(out_path, root):
    ET.indent(root)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not data.endswith(b"\n"):
        data += b"\n"
    directory = os.path.dirname(os.path.abspath(out_path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, out_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def main(argv):
    try:
        args = parse_args(argv)
    except BadArgs as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    items = load_items(args.feed)
    items = [it for it in items if it["version"] != args.version]
    items.append({"version": args.version, "element": new_item(args)})
    items.sort(key=lambda it: it["version"], reverse=True)
    items = items[: args.keep]

    root = build_root(args, items)
    write_atomically(args.out, root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

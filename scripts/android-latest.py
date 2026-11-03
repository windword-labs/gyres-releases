#!/usr/bin/env python3
"""Write android/latest.json for the Gyres Android update check.

{"version", "versionCode", "url", "sha256", "published"}; served as
www.gyres.app/android/latest.json by the site Worker. Never lowers versionCode.
Python 3 standard library only.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--version-code", required=True, type=int)
    p.add_argument("--url", required=True)
    p.add_argument("--sha256", required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r"\d+\.\d+\.\d+", a.version):
        print("error: --version must be X.Y.Z", file=sys.stderr)
        return 2
    if a.version_code <= 0:
        print("error: --version-code must be positive", file=sys.stderr)
        return 2
    if not a.url.startswith("https://"):
        print("error: --url must be https", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[0-9a-f]{64}", a.sha256):
        print("error: --sha256 must be 64 lowercase hex", file=sys.stderr)
        return 2
    if os.path.exists(a.out):
        try:
            with open(a.out) as f:
                old = json.load(f).get("versionCode", 0)
        except (ValueError, OSError):
            old = 0
        if isinstance(old, int) and old > a.version_code:
            print(f"error: existing versionCode {old} is newer than {a.version_code}", file=sys.stderr)
            return 1
    doc = {
        "version": a.version,
        "versionCode": a.version_code,
        "url": a.url,
        "sha256": a.sha256,
        "published": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    d = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Notify the Grok Bot webhook of a stable desktop or Gyres Mac release.

Stdlib only. Reads GITHUB_EVENT_PATH as JSON, or GETs a tag from the GitHub
API on workflow_call. Never interpolates release text into a shell. The
webhook URL is fixed here; URLs in events or API JSON are ignored.
"""

import http.client
import json
import os
import re
import sys
from urllib.parse import quote, urlparse

EXPECTED_REPOSITORY = "windword-labs/gyres-releases"
WEBHOOK_URL = (
    "https://api2.cursor.sh/automations/webhook/"
    "838531b3-2323-58c4-8bfd-c4fa0525e42f"
)
GITHUB_API_HOST = "api.github.com"
GITHUB_API_PREFIX = f"/repos/{EXPECTED_REPOSITORY}/releases/tags/"
WEBHOOK_TIMEOUT_SEC = 8
BODY_MAX_CHARS = 4000
NAME_MAX_CHARS = 200
SECRET_ENV = "GYRES_BOT_WEBHOOK_KEY"
STABLE_TAG = re.compile(
    r"^(mac-)?v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
RELEASE_ACTIONS = frozenset({"published", "released"})


def is_stable_tag(tag):
    return isinstance(tag, str) and bool(STABLE_TAG.fullmatch(tag))


def bound_text(value, limit):
    if not isinstance(value, str) or value == "":
        return None
    if len(value) <= limit:
        return value
    return value[:limit]


def source_sha(value):
    if isinstance(value, str) and SHA_RE.fullmatch(value):
        return value.lower()
    return None


def probe_payload():
    return {
        "action": "probe",
        "repository": {"full_name": EXPECTED_REPOSITORY},
    }


def release_payload(event, sha):
    rel = event["release"]
    tag = rel["tag_name"]
    html_url = rel.get("html_url")
    expected_html = f"https://github.com/{EXPECTED_REPOSITORY}/releases/tag/{tag}"
    if html_url != expected_html:
        html_url = expected_html
    out = {
        "action": event["action"],
        "repository": {"full_name": EXPECTED_REPOSITORY},
        "release": {
            "id": rel["id"],
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "html_url": html_url,
        },
    }
    created = rel.get("created_at")
    published = rel.get("published_at")
    if isinstance(created, str):
        out["release"]["created_at"] = created
    if isinstance(published, str):
        out["release"]["published_at"] = published
    name = bound_text(rel.get("name"), NAME_MAX_CHARS)
    if name is not None:
        out["release"]["name"] = name
    body = bound_text(rel.get("body"), BODY_MAX_CHARS)
    if body is not None:
        out["release"]["body"] = body
    target = rel.get("target_commitish")
    if isinstance(target, str) and target != "":
        out["release"]["target_commitish"] = target[:64]
    sha = source_sha(sha)
    if sha is not None:
        out["source_sha"] = sha
    return out


def classify(event_name, event):
    if event_name == "workflow_dispatch":
        return "probe", probe_payload()
    if event_name != "release":
        return "skip", "event"
    if not isinstance(event, dict):
        return "error", "event is not an object"
    if event.get("action") not in RELEASE_ACTIONS:
        return "skip", "action"
    repo = event.get("repository")
    if not isinstance(repo, dict) or repo.get("full_name") != EXPECTED_REPOSITORY:
        return "skip", "repository"
    rel = event.get("release")
    if not isinstance(rel, dict):
        return "error", "release is not an object"
    if rel.get("draft") is not False:
        return "skip", "draft"
    if rel.get("prerelease") is not False:
        return "skip", "prerelease"
    if not isinstance(rel.get("id"), int):
        return "error", "release.id"
    if not is_stable_tag(rel.get("tag_name")):
        return "skip", "tag"
    return "notify", release_payload(event, None)


def webhook_target():
    parsed = urlparse(WEBHOOK_URL)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api2.cursor.sh"
        or parsed.path != (
            "/automations/webhook/838531b3-2323-58c4-8bfd-c4fa0525e42f"
        )
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        raise RuntimeError("refusing unexpected webhook URL")
    return parsed.hostname, parsed.path


def send_post(hostname, path, body, headers, timeout):
    conn = http.client.HTTPSConnection(hostname, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp.read()
        return status
    finally:
        conn.close()


def github_get(path, token, timeout=WEBHOOK_TIMEOUT_SEC):
    if not path.startswith(GITHUB_API_PREFIX):
        raise RuntimeError("refusing unexpected GitHub API path")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gyres-releases-notify",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    conn = http.client.HTTPSConnection(GITHUB_API_HOST, timeout=timeout)
    try:
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read()
        return status, raw
    finally:
        conn.close()


def fetch_release_event(tag, token, getter=github_get):
    if not is_stable_tag(tag):
        return "skip", "tag"
    path = GITHUB_API_PREFIX + quote(tag, safe="")
    try:
        status, raw = getter(path, token)
    except TimeoutError:
        print("github api failed: timeout", file=sys.stderr)
        return "error", "github api"
    except OSError:
        print("github api failed: network or timeout", file=sys.stderr)
        return "error", "github api"
    if status != 200:
        print(f"github api failed: HTTP {status}", file=sys.stderr)
        return "error", "github api"
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        print("github api failed: invalid JSON", file=sys.stderr)
        return "error", "github api"
    if not isinstance(data, dict):
        print("github api failed: invalid JSON", file=sys.stderr)
        return "error", "github api"
    return classify(
        "release",
        {
            "action": "published",
            "repository": {"full_name": EXPECTED_REPOSITORY},
            "release": data,
        },
    )


def post_webhook(payload, key, sender=send_post):
    hostname, path = webhook_target()
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
        "X-Automation-Key": key,
    }
    try:
        status = sender(hostname, path, body, headers, WEBHOOK_TIMEOUT_SEC)
    except TimeoutError:
        print("webhook failed: timeout", file=sys.stderr)
        return 1
    except OSError:
        print("webhook failed: network or timeout", file=sys.stderr)
        return 1
    if status != 200:
        print(f"webhook failed: HTTP {status}", file=sys.stderr)
        return 1
    print("webhook accepted (HTTP 200); receiver woke, processing is independent")
    return 0


def load_event(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("event is not an object")
    return data


def run(env=None, sender=send_post, github_getter=github_get):
    env = os.environ if env is None else env
    event_name = env.get("GITHUB_EVENT_NAME", "")
    tag = env.get("RELEASE_TAG", "")
    # Reusable workflows keep the caller's event_name (repository_dispatch for
    # the desktop/Mac publish jobs). A non-empty RELEASE_TAG is the caller.
    if event_name == "workflow_dispatch" and not tag:
        kind, payload = "probe", probe_payload()
    elif tag:
        kind, payload = fetch_release_event(
            tag, env.get("GITHUB_TOKEN", ""), getter=github_getter
        )
    elif event_name == "release":
        path = env.get("GITHUB_EVENT_PATH", "")
        if not path:
            print("missing GITHUB_EVENT_PATH", file=sys.stderr)
            return 1
        try:
            event = load_event(path)
        except (OSError, ValueError, json.JSONDecodeError):
            print("invalid GITHUB_EVENT_PATH", file=sys.stderr)
            return 1
        kind, payload = classify(event_name, event)
    else:
        kind, payload = "skip", "event"

    if kind == "notify":
        sha = source_sha(env.get("SOURCE_SHA")) or source_sha(env.get("GITHUB_SHA"))
        if sha:
            payload["source_sha"] = sha
        else:
            payload.pop("source_sha", None)

    if kind == "error":
        print(payload, file=sys.stderr)
        return 1
    if kind == "skip":
        print(f"skip: {payload}")
        return 0

    key = env.get(SECRET_ENV, "")
    if not isinstance(key, str) or key.strip() == "":
        print(
            f"missing repository secret {SECRET_ENV}",
            file=sys.stderr,
        )
        return 1

    if kind == "probe":
        print("notifying probe")
    else:
        rel = payload["release"]
        print(f"notifying {payload['action']} id={rel['id']}")
    return post_webhook(payload, key, sender=sender)


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Local tests for notify_stable_release.py. Never POSTs to the live webhook."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import notify_stable_release as n  # noqa: E402
WORKFLOW = os.path.join(
    os.path.dirname(SCRIPT_DIR),
    ".github",
    "workflows",
    "notify-stable-release.yml",
)
WEBHOOK_PATH = (
    "/automations/webhook/838531b3-2323-58c4-8bfd-c4fa0525e42f"
)
FAKE_KEY = "test-sender-key-not-real"


def event(
    tag,
    *,
    action="published",
    draft=False,
    prerelease=False,
    release_id=42,
    body="notes",
    html_url=None,
    extra_release=None,
    full_name="windword-labs/gyres-releases",
):
    if html_url is None:
        html_url = (
            f"https://github.com/windword-labs/gyres-releases/releases/tag/{tag}"
        )
    rel = {
        "id": release_id,
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": html_url,
        "created_at": "2026-11-15T00:00:00Z",
        "published_at": "2026-11-15T00:01:00Z",
        "name": f"Gyres {tag}",
        "body": body,
        "target_commitish": "abc",
        "assets": [{"name": "secret.bin", "url": "https://evil.example/a"}],
        "upload_url": "https://uploads.github.com/repos/x/y/releases/1/assets",
        "tarball_url": "https://evil.example/tarball",
        "zipball_url": "https://evil.example/zipball",
    }
    if extra_release:
        rel.update(extra_release)
    return {
        "action": action,
        "release": rel,
        "repository": {"full_name": full_name},
        "webhook_url": "https://evil.example/steal",
    }


class TagFilterTest(unittest.TestCase):
    def test_accepts_numeric_v_and_patches(self):
        for tag in (
            "v0.121.3",
            "v0.121.4",
            "v0.0.1",
            "v1.0.0",
            "v10.20.30",
        ):
            self.assertTrue(n.is_stable_tag(tag), tag)

    def test_accepts_mac_v_and_patches(self):
        for tag in ("mac-v0.14.0", "mac-v0.14.1", "mac-v1.2.3"):
            self.assertTrue(n.is_stable_tag(tag), tag)

    def test_rejects_prerelease_dev_and_unrelated(self):
        for tag in (
            "v0.121.3-rc.1",
            "v0.121.3-beta",
            "v0.121.3-alpha.1",
            "v0.121.3-dev",
            "v0.121.3rc1",
            "mac-v0.14.0-beta",
            "mac-dev-abc123.9",
            "android-v0.1.0",
            "dev-main-abc1234.1",
            "v0.121",
            "v0.121.3.0",
            "v01.2.3",
            "V0.121.3",
            "gv0.1.0",
            "latest",
            "v0.121.3\n;curl evil",
            "mac-v0",
            "",
            None,
            1,
        ):
            self.assertFalse(n.is_stable_tag(tag), tag)


class ClassifyTest(unittest.TestCase):
    def test_published_stable_notifies(self):
        kind, payload = n.classify("release", event("v0.121.3"))
        self.assertEqual(kind, "notify")
        self.assertEqual(payload["action"], "published")
        self.assertEqual(payload["release"]["tag_name"], "v0.121.3")
        self.assertEqual(payload["release"]["id"], 42)
        self.assertFalse(payload["release"]["draft"])
        self.assertFalse(payload["release"]["prerelease"])
        self.assertEqual(
            payload["repository"]["full_name"], "windword-labs/gyres-releases"
        )

    def test_released_stable_notifies(self):
        kind, payload = n.classify(
            "release", event("mac-v0.14.0", action="released")
        )
        self.assertEqual(kind, "notify")
        self.assertEqual(payload["action"], "released")
        self.assertEqual(payload["release"]["tag_name"], "mac-v0.14.0")

    def test_skips_draft_prerelease_bad_tag_and_repo(self):
        cases = [
            (event("v0.121.3", draft=True), "draft"),
            (event("v0.121.3", prerelease=True), "prerelease"),
            (event("v0.121.3-rc.1"), "tag"),
            (event("android-v0.1.0"), "tag"),
            (event("dev-main-deadbee.1"), "tag"),
            (event("v0.121.3", action="created"), "action"),
            (event("v0.121.3", full_name="evil/fork"), "repository"),
        ]
        for ev, reason in cases:
            kind, payload = n.classify("release", ev)
            self.assertEqual(kind, "skip", reason)
            self.assertEqual(payload, reason)

    def test_probe_ignores_event_body(self):
        kind, payload = n.classify("workflow_dispatch", event("v0.121.3"))
        self.assertEqual(kind, "probe")
        self.assertEqual(payload, n.probe_payload())
        self.assertNotIn("release", payload)
        self.assertEqual(payload["action"], "probe")

    def test_payload_omits_assets_and_does_not_use_event_urls(self):
        ev = event(
            "v0.121.3",
            html_url="https://evil.example/releases/tag/v0.121.3",
            extra_release={"hook": "https://evil.example"},
        )
        kind, payload = n.classify("release", ev)
        self.assertEqual(kind, "notify")
        rel = payload["release"]
        self.assertNotIn("assets", rel)
        self.assertNotIn("upload_url", rel)
        self.assertNotIn("tarball_url", rel)
        self.assertNotIn("zipball_url", rel)
        self.assertNotIn("hook", rel)
        self.assertNotIn("webhook_url", payload)
        self.assertEqual(
            rel["html_url"],
            "https://github.com/windword-labs/gyres-releases/releases/tag/v0.121.3",
        )
        dumped = json.dumps(payload)
        self.assertNotIn("evil.example", dumped)
        self.assertNotIn("secret.bin", dumped)
        self.assertNotIn("uploads.github.com", dumped)

    def test_body_and_name_are_bounded(self):
        kind, payload = n.classify(
            "release",
            event("v0.121.3", body="B" * 5000, extra_release={"name": "N" * 500}),
        )
        self.assertEqual(kind, "notify")
        self.assertEqual(len(payload["release"]["body"]), 4000)
        self.assertEqual(len(payload["release"]["name"]), 200)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.posts = []

        def sender(hostname, path, body, headers, timeout):
            self.posts.append(
                {
                    "hostname": hostname,
                    "path": path,
                    "body": body,
                    "headers": headers,
                    "timeout": timeout,
                }
            )
            return 200

        self.sender = sender
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_event(self, ev):
        path = os.path.join(self.tmp.name, "event.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ev, f)
        return path

    def env_for(self, ev, **extra):
        env = {
            "GITHUB_EVENT_NAME": "release",
            "GITHUB_EVENT_PATH": self.write_event(ev),
            "GITHUB_SHA": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            n.SECRET_ENV: FAKE_KEY,
        }
        env.update(extra)
        return env

    def run_script(self, env, sender=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = n.run(env=env, sender=sender or self.sender)
        return code, out.getvalue(), err.getvalue()

    def test_notify_posts_fixed_url_and_both_auth_headers(self):
        code, out, err = self.run_script(self.env_for(event("v0.121.3")))
        self.assertEqual(code, 0, err)
        self.assertIn("HTTP 200", out)
        self.assertEqual(len(self.posts), 1)
        post = self.posts[0]
        self.assertEqual(post["hostname"], "api2.cursor.sh")
        self.assertEqual(post["path"], WEBHOOK_PATH)
        self.assertEqual(post["timeout"], 8)
        self.assertEqual(post["headers"]["Content-Type"], "application/json")
        self.assertEqual(post["headers"]["Authorization"], "Bearer " + FAKE_KEY)
        self.assertEqual(post["headers"]["X-Automation-Key"], FAKE_KEY)
        payload = json.loads(post["body"])
        self.assertEqual(payload["release"]["tag_name"], "v0.121.3")
        self.assertEqual(
            payload["source_sha"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )
        self.assertNotIn("assets", payload["release"])

    def test_malicious_text_is_json_not_shell(self):
        nasty = '$(rm -rf /); `reboot`; "; curl https://evil.example'
        code, _, err = self.run_script(
            self.env_for(event("mac-v0.14.1", body=nasty, extra_release={
                "name": nasty,
            }))
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(self.posts[0]["body"])
        self.assertEqual(payload["release"]["body"], nasty)
        self.assertEqual(payload["release"]["name"], nasty)
        self.assertEqual(self.posts[0]["hostname"], "api2.cursor.sh")

    def test_skip_does_not_post_or_need_secret(self):
        env = self.env_for(event("android-v0.1.0"))
        env.pop(n.SECRET_ENV)
        code, out, err = self.run_script(env)
        self.assertEqual(code, 0, err)
        self.assertIn("skip:", out)
        self.assertEqual(self.posts, [])
        self.assertEqual(err, "")

    def test_missing_secret_on_notify_fails_without_posting(self):
        env = self.env_for(event("v0.121.3"))
        env[n.SECRET_ENV] = ""
        code, out, err = self.run_script(env)
        self.assertEqual(code, 1)
        self.assertIn("GYRES_BOT_WEBHOOK_KEY", err)
        self.assertNotIn(FAKE_KEY, err)
        self.assertNotIn(FAKE_KEY, out)
        self.assertEqual(self.posts, [])

    def test_probe_posts_action_probe_only(self):
        env = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            n.SECRET_ENV: FAKE_KEY,
        }
        code, out, err = self.run_script(env)
        self.assertEqual(code, 0, err)
        self.assertIn("probe", out)
        payload = json.loads(self.posts[0]["body"])
        self.assertEqual(payload["action"], "probe")
        self.assertNotIn("release", payload)
        self.assertEqual(
            payload["repository"]["full_name"], "windword-labs/gyres-releases"
        )

    def test_missing_secret_on_probe_fails(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch"}
        code, out, err = self.run_script(env)
        self.assertEqual(code, 1)
        self.assertIn("GYRES_BOT_WEBHOOK_KEY", err)
        self.assertEqual(self.posts, [])
        self.assertNotIn(FAKE_KEY, out + err)

    def test_http_failure_does_not_log_response(self):
        def http_500(hostname, path, body, headers, timeout):
            self.posts.append(body)
            return 500

        code, out, err = self.run_script(
            self.env_for(event("v0.121.3")), sender=http_500
        )
        self.assertEqual(code, 1)
        self.assertIn("HTTP 500", err)
        self.assertNotIn("Bearer", err)
        self.assertNotIn(FAKE_KEY, err)
        self.assertNotIn(FAKE_KEY, out)
        # The JSON body of the *request* is not printed either.
        self.assertNotIn("v0.121.3", err)

    def test_timeout_fails_clearly(self):
        def sender(hostname, path, body, headers, timeout):
            raise TimeoutError()

        code, out, err = self.run_script(
            self.env_for(event("v0.121.3")), sender=sender
        )
        self.assertEqual(code, 1)
        self.assertIn("timeout", err)
        self.assertNotIn(FAKE_KEY, err)

    def test_event_url_fields_cannot_redirect_post(self):
        ev = event(
            "v0.121.3",
            html_url="https://evil.example/x",
            extra_release={
                "url": "https://evil.example/api",
                "assets_url": "https://evil.example/assets",
            },
        )
        code, _, err = self.run_script(self.env_for(ev))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.posts[0]["hostname"], "api2.cursor.sh")
        self.assertEqual(self.posts[0]["path"], WEBHOOK_PATH)

    def test_stderr_and_stdout_never_contain_secret(self):
        code, out, err = self.run_script(self.env_for(event("v0.121.3")))
        self.assertEqual(code, 0)
        combined = out + err
        self.assertNotIn(FAKE_KEY, combined)
        self.assertNotIn("Bearer ", combined)
        self.assertNotIn("X-Automation-Key", combined)


class WorkflowFileTest(unittest.TestCase):
    def setUp(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            self.text = f.read()

    def test_yaml_covers_published_released_probe_and_workflow_call(self):
        self.assertIn("types: [published, released]", self.text)
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("workflow_call:", self.text)
        self.assertIn("GITHUB_TOKEN", self.text)
        self.assertNotIn("schedule:", self.text)
        self.assertNotIn("cron:", self.text)
        self.assertNotIn("repository_dispatch:", self.text)
        self.assertNotIn("PRIVATE_REPO_PAT", self.text)
        self.assertNotIn("secrets: inherit", self.text)

    def test_least_permissions_ubuntu_no_mac_concurrency(self):
        self.assertIn("contents: read", self.text)
        self.assertIn("runs-on: ubuntu-latest", self.text)
        self.assertNotIn("macos", self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("github.event.release.id", self.text)
        self.assertIn("inputs.tag", self.text)
        self.assertIn("windword-labs/gyres-releases", self.text)
        self.assertIn("inputs.tag != ''", self.text)
        self.assertIn("github.event.release.draft == false", self.text)
        self.assertIn("github.event.release.prerelease == false", self.text)

    def test_run_step_is_not_interpolated(self):
        self.assertIn("run: python3 scripts/notify_stable_release.py", self.text)
        self.assertIn(
            "GYRES_BOT_WEBHOOK_KEY: ${{ secrets.GYRES_BOT_WEBHOOK_KEY }}",
            self.text,
        )
        for line in self.text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("run:"):
                self.assertNotIn("github.event.release", stripped)
                self.assertNotIn("tag_name", stripped)
                self.assertNotIn("${{", stripped)

    def test_fixed_webhook_url_matches_docs_and_script(self):
        self.assertEqual(
            n.WEBHOOK_URL,
            "https://api2.cursor.sh/automations/webhook/"
            "838531b3-2323-58c4-8bfd-c4fa0525e42f",
        )
        hostname, path = n.webhook_target()
        self.assertEqual(hostname, "api2.cursor.sh")
        self.assertEqual(path, WEBHOOK_PATH)

    def test_checkout_is_pinned_and_does_not_persist_credentials(self):
        self.assertIn(
            "uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            self.text,
        )
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("actions/checkout@v4", self.text)


class SendPostContractTest(unittest.TestCase):
    def test_send_post_does_not_log_response_body(self):
        class FakeResp:
            status = 401
            def read(self):
                return b'{"error":"nope","header":"secret"}'

        class FakeConn:
            def __init__(self):
                self.closed = False
            def request(self, method, path, body=None, headers=None):
                self.method, self.path, self.body, self.headers = (
                    method, path, body, headers
                )
            def getresponse(self):
                return FakeResp()
            def close(self):
                self.closed = True

        fake = FakeConn()
        with mock.patch("http.client.HTTPSConnection", return_value=fake):
            status = n.send_post(
                "api2.cursor.sh", WEBHOOK_PATH, b"{}",
                {"Authorization": "Bearer " + FAKE_KEY}, 8,
            )
        self.assertEqual(status, 401)
        self.assertTrue(fake.closed)
        self.assertEqual(fake.method, "POST")


class WorkflowCallTest(unittest.TestCase):
    def setUp(self):
        self.posts = []
        self.gets = []

        def sender(hostname, path, body, headers, timeout):
            self.posts.append(
                {
                    "hostname": hostname,
                    "path": path,
                    "body": body,
                    "headers": headers,
                    "timeout": timeout,
                }
            )
            return 200

        self.sender = sender
        self.api_release = {
            "id": 99,
            "tag_name": "v0.121.3",
            "draft": False,
            "prerelease": False,
            "html_url": (
                "https://github.com/windword-labs/gyres-releases/releases/tag/v0.121.3"
            ),
            "created_at": "2026-11-15T00:00:00Z",
            "published_at": "2026-11-15T00:01:00Z",
            "name": "Gyres v0.121.3",
            "body": "Source: windword-labs/gyres@deadbeef",
            "target_commitish": "main",
            "assets": [{"name": "secret.bin", "url": "https://evil.example/a"}],
            "upload_url": "https://uploads.github.com/x",
            "url": "https://evil.example/api",
        }

    def getter(self, path, token):
        self.gets.append({"path": path, "token": token})
        return 200, json.dumps(self.api_release).encode()

    def run_script(self, env, getter=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = n.run(
                env=env,
                sender=self.sender,
                github_getter=getter or self.getter,
            )
        return code, out.getvalue(), err.getvalue()

    def env_for(self, tag="v0.121.3", event_name="workflow_call", **extra):
        env = {
            "GITHUB_EVENT_NAME": event_name,
            "RELEASE_TAG": tag,
            "SOURCE_SHA": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "GITHUB_TOKEN": "ghs_test_github_token",
            n.SECRET_ENV: FAKE_KEY,
        }
        env.update(extra)
        return env

    def test_caller_repository_dispatch_with_tag_fetches_and_posts(self):
        # Reusable workflows expose the caller's event_name, not workflow_call.
        code, out, err = self.run_script(
            self.env_for(event_name="repository_dispatch")
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.gets), 1)
        self.assertEqual(self.posts[0]["hostname"], "api2.cursor.sh")
        payload = json.loads(self.posts[0]["body"])
        self.assertEqual(payload["release"]["tag_name"], "v0.121.3")
        self.assertNotIn(FAKE_KEY, out + err)

    def test_repository_dispatch_without_tag_skips(self):
        env = self.env_for(event_name="repository_dispatch")
        env.pop("RELEASE_TAG")
        code, out, err = self.run_script(env)
        self.assertEqual(code, 0, err)
        self.assertIn("skip:", out)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.posts, [])

    def test_workflow_call_fetches_api_and_posts_fixed_webhook(self):
        code, out, err = self.run_script(self.env_for())
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.gets), 1)
        self.assertEqual(
            self.gets[0]["path"],
            "/repos/windword-labs/gyres-releases/releases/tags/v0.121.3",
        )
        self.assertEqual(self.gets[0]["token"], "ghs_test_github_token")
        self.assertEqual(self.posts[0]["hostname"], "api2.cursor.sh")
        self.assertEqual(self.posts[0]["path"], WEBHOOK_PATH)
        self.assertEqual(self.posts[0]["headers"]["Authorization"], "Bearer " + FAKE_KEY)
        self.assertEqual(self.posts[0]["headers"]["X-Automation-Key"], FAKE_KEY)
        payload = json.loads(self.posts[0]["body"])
        self.assertEqual(payload["action"], "published")
        self.assertEqual(payload["release"]["id"], 99)
        self.assertEqual(payload["release"]["tag_name"], "v0.121.3")
        self.assertEqual(
            payload["source_sha"], "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )
        dumped = json.dumps(payload)
        self.assertNotIn("evil.example", dumped)
        self.assertNotIn("secret.bin", dumped)
        self.assertNotIn("ghs_test_github_token", out + err)
        self.assertNotIn(FAKE_KEY, out + err)

    def test_workflow_call_mac_patch_tag(self):
        self.api_release["tag_name"] = "mac-v0.14.1"
        self.api_release["id"] = 100
        code, _, err = self.run_script(self.env_for("mac-v0.14.1"))
        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.gets[0]["path"],
            "/repos/windword-labs/gyres-releases/releases/tags/mac-v0.14.1",
        )
        payload = json.loads(self.posts[0]["body"])
        self.assertEqual(payload["release"]["tag_name"], "mac-v0.14.1")

    def test_workflow_call_rejects_bad_tag_without_api_or_post(self):
        for tag in (
            "v0.121.3-rc.1",
            "android-v0.1.0",
            "mac-dev-abc.1",
            "v0.121.3;curl https://evil.example",
        ):
            self.gets.clear()
            self.posts.clear()
            code, out, err = self.run_script(self.env_for(tag))
            self.assertEqual(code, 0, tag)
            self.assertIn("skip:", out)
            self.assertEqual(self.gets, [])
            self.assertEqual(self.posts, [])
            self.assertNotIn("evil.example", out + err)

    def test_workflow_call_skips_api_prerelease_and_draft(self):
        self.api_release["prerelease"] = True
        code, out, err = self.run_script(self.env_for())
        self.assertEqual(code, 0, err)
        self.assertIn("skip:", out)
        self.assertEqual(self.posts, [])

    def test_workflow_call_api_failure_does_not_log_body(self):
        def getter(path, token):
            return 404, b'{"message":"not found","token":"leak-me"}'

        code, out, err = self.run_script(self.env_for(), getter=getter)
        self.assertEqual(code, 1)
        self.assertIn("HTTP 404", err)
        self.assertNotIn("leak-me", err)
        self.assertNotIn("leak-me", out)
        self.assertEqual(self.posts, [])

    def test_workflow_call_missing_secret_fails_without_posting_secret(self):
        env = self.env_for()
        env[n.SECRET_ENV] = ""
        code, out, err = self.run_script(env)
        self.assertEqual(code, 1)
        self.assertIn("GYRES_BOT_WEBHOOK_KEY", err)
        self.assertNotIn(FAKE_KEY, err)
        self.assertNotIn("ghs_test_github_token", err)
        self.assertEqual(self.posts, [])

    def test_github_get_refuses_non_release_path(self):
        with self.assertRaises(RuntimeError):
            n.github_get("/repos/windword-labs/gyres-releases/hooks", "x")


class PublishWiringTest(unittest.TestCase):
    def read(self, name):
        path = os.path.join(
            os.path.dirname(SCRIPT_DIR), ".github", "workflows", name
        )
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_desktop_and_mac_call_reusable_notify_without_pat(self):
        desktop = self.read("build-release.yml")
        mac = self.read("build-mac-release.yml")
        android = self.read("build-android-release.yml")
        dev = self.read("build-dev-release.yml")
        for text in (desktop, mac):
            self.assertIn(
                "uses: ./.github/workflows/notify-stable-release.yml", text
            )
            self.assertIn("GYRES_BOT_WEBHOOK_KEY: ${{ secrets.GYRES_BOT_WEBHOOK_KEY }}", text)
            self.assertNotIn("secrets: inherit", text)
            self.assertIn("GH_TOKEN: ${{ github.token }}", text)
            self.assertIn("gh release create", text)
        self.assertIn("github.event_name == 'repository_dispatch'", desktop)
        self.assertIn("needs.validate.outputs.channel == 'stable'", mac)
        self.assertNotIn("notify-stable-release.yml", android)
        self.assertNotIn("notify-stable-release.yml", dev)
        self.assertNotIn("GYRES_BOT_WEBHOOK_KEY", android)
        self.assertNotIn("GYRES_BOT_WEBHOOK_KEY", dev)

    def test_publish_command_still_uses_github_token(self):
        desktop = self.read("build-release.yml")
        mac = self.read("build-mac-release.yml")
        self.assertIn(
            'gh release create "$TAG" --repo "$GITHUB_REPOSITORY" --title "Gyres $TAG"',
            desktop,
        )
        self.assertIn(
            'gh release create "$TAG" --repo "$GITHUB_REPOSITORY" "${FLAGS[@]}"',
            mac,
        )
        self.assertNotIn("PRIVATE_REPO_PAT", desktop.split("notify:")[1])
        self.assertNotIn("UPDATER_GITHUB_TOKEN", desktop.split("notify:")[1])


if __name__ == "__main__":
    unittest.main()


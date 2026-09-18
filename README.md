# gyres-releases

Public GitHub Releases for Gyres desktop. Source stays in the private [jetstream](https://github.com/windword-labs/jetstream) repo.

This repo does not contain application source. Workflows here are meant to:

1. Receive `repository_dispatch` from jetstream
2. Check out a frozen SHA of jetstream
3. Run `wails3 package` / `package:develop` on `macos-arm64`
4. Attach the `.app` to a GitHub Release

**Not wired yet:** `PRIVATE_REPO_PAT`, actual package steps, and dispatch from jetstream. The workflows currently validate the payload and print what they would do.

| Event | Channel | Intended command |
| --- | --- | --- |
| `build-dev-release` | Gyres Dev | `wails3 task package:develop` |
| `build-release` | Gyres | `wails3 package` |

Stable tags (`vX.Y.Z`) live on jetstream `main`. This repo only publishes artifacts.

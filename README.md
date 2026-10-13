# Gyres releases

Production packages are built concurrently from one frozen source commit:

| Platform | Downloads |
| --- | --- |
| macOS ARM64 | Signed and notarized app ZIP |
| Windows amd64 / ARM64 | Unsigned installer EXE and portable ZIP |
| Linux amd64 / ARM64 | Unsigned AppImage (Ubuntu 24.04 build baseline) |
| Linux amd64 / ARM64 servers | Standalone Core `gyres-core-linux-<arch>.tar.gz` for machines without a desktop |

Intel Macs are not supported. Dev packages remain macOS ARM64 only.
There are no Linux deb/rpm packages, package repositories or GPG signatures.

Individual successful builds are available as Actions artifacts immediately.
A production release is published only after every platform passes, with a
combined `SHA256SUMS`. The manual full-SHA workflow is for packaging acceptance;
it never publishes a release. Stable publication requires a matching lightweight
source tag on main.

Windows and Linux desktop packages currently use manual updates; macOS retains
automatic updates. The standalone Linux Core updates with `core update` (checked
against `SHA256SUMS`) and is restarted by its service manager. Browser CLI packaging is verified, but automatic managed Chrome
provisioning is currently macOS-only. Windows ARM64 bundles the upstream x64
browser CLI and requires Windows 11 emulation.

Secrets:

- `PRIVATE_REPO_PAT`: read the private source repository
- `UPDATER_GITHUB_TOKEN`: Contents: Read on this public repository, embedded only in macOS production builds
- `SPARKLE_ED_PRIVATE_KEY`: Gyres Mac Sparkle EdDSA private key (set by the owner)
- macOS signing: `CSC_LINK_BASE64`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`

## Gyres Mac

`build-mac-release.yml` builds the native Mac app (`apps/macos` in the source repo) on
the `xcode-27` runner: stable `mac-vX.Y.Z` Releases (never marked latest, so
`releases/latest` stays the desktop's) and Dev prereleases `mac-dev-<sha>.<run>`.
Each is Developer ID signed, notarized and EdDSA-signed for Sparkle; the publish job
adds it to `mac/appcast.xml` or `mac/appcast-dev.xml` on the `appcast` branch
(`scripts/mac-appcast.py`), which www.gyres.app serves under `/mac/`. A manual run
with a SHA is a build check that never publishes.

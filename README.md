# Gyres releases

Production packages are built concurrently from one frozen source commit:

| Platform | Downloads |
| --- | --- |
| macOS ARM64 | Signed and notarized app ZIP |
| Windows amd64 / ARM64 | Unsigned installer EXE and portable ZIP |
| Linux amd64 / ARM64 | Unsigned AppImage (Ubuntu 24.04 build baseline) |

Intel Macs are not supported. Dev packages remain macOS ARM64 only.
There are no Linux deb/rpm packages, package repositories or GPG signatures.

Individual successful builds are available as Actions artifacts immediately.
A production release is published only after every platform passes, with a
combined `SHA256SUMS`. The manual full-SHA workflow is for packaging acceptance;
it never publishes a release. Stable publication requires a matching lightweight
source tag on main.

Windows and Linux currently use manual package updates; macOS retains automatic
updates. Browser CLI packaging is verified, but automatic managed Chrome
provisioning is currently macOS-only. Windows ARM64 bundles the upstream x64
browser CLI and requires Windows 11 emulation.

Secrets:

- `PRIVATE_REPO_PAT`: read the private source repository
- `UPDATER_GITHUB_TOKEN`: Contents: Read on this public repository, embedded only in macOS production builds
- macOS signing: `CSC_LINK_BASE64`, `CSC_KEY_PASSWORD`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`

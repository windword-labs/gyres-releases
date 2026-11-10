# Gyres releases

Production packages are built concurrently from one frozen source commit:

| Platform | Downloads |
| --- | --- |
| macOS ARM64 | Signed and notarized app ZIP |
| Windows amd64 / ARM64 | Unsigned installer EXE and portable ZIP |
| Linux amd64 / ARM64 | Unsigned AppImage (Ubuntu 24.04 build baseline) |
| Linux amd64 / ARM64 packages | Unsigned `.deb` (Ubuntu 24.04+, Debian 13+) and `.rpm` (Fedora 40+), using the system GTK 4 / WebKitGTK 6.0 |
| Linux amd64 / ARM64 servers | Standalone Core `gyres-core-linux-<arch>.tar.gz` for machines without a desktop |

Intel Macs are not supported. Dev packages remain macOS ARM64 only.
The Linux `.deb` / `.rpm` files are Release assets only: no APT/YUM repositories,
no GPG signatures, no in-app updates. Install a newer package to update.

Individual successful builds are available as Actions artifacts immediately.
A production release is published only after every platform passes, with a
combined `SHA256SUMS` and `SHA256SUMS.sig`, a raw Ed25519 signature over the
exact bytes of `SHA256SUMS` (`scripts/sign-sha256sums.sh`). Before anything is
published the signature must verify with one of the public keys in
`packages/appdata/releasesig/keys` of the source at the release SHA, the keys
the updaters embed; a missing secret or a mismatch fails the run. Dev
prereleases are signed the same way. From windword-labs/gyres#2069 on, the
macOS updater and the standalone Core refuse a release without a valid
`SHA256SUMS.sig` (no override), so never publish one by hand without it.
Check a download with OpenSSL 3:

```sh
openssl pkeyutl -verify -rawin -pubin -inkey primary.pem -in SHA256SUMS -sigfile SHA256SUMS.sig
```

The manual full-SHA workflow is for packaging acceptance; it checksums and
signs (so it exercises the secret) but never publishes a release. Stable
publication requires a matching lightweight source tag on main.

Windows and Linux desktop packages currently use manual updates; macOS retains
automatic updates. The standalone Linux Core updates with `core update` (checked
against the signed `SHA256SUMS`) and is restarted by its service manager. Browser CLI packaging is verified, but automatic managed Chrome
provisioning is currently macOS-only. Windows ARM64 bundles the upstream x64
browser CLI and requires Windows 11 emulation.

Secrets:

- `PRIVATE_REPO_PAT`: read the private source repository
- `UPDATER_GITHUB_TOKEN`: Contents: Read on this public repository, embedded only in macOS production builds
- `RELEASE_ED25519_PRIVATE_KEY`: Ed25519 PEM private key that signs `SHA256SUMS` (set by the owner; its public half is `keys/primary.pem` in the source)
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

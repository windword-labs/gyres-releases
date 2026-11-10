#!/usr/bin/env bash
# Sign SHA256SUMS for a Gyres release (windword-labs/gyres#394).
#
#   RELEASE_ED25519_PRIVATE_KEY=<PEM> scripts/sign-sha256sums.sh <dir> <keys-dir>
#
# Writes <dir>/SHA256SUMS.sig, the raw 64-byte Ed25519 signature over the exact
# bytes of <dir>/SHA256SUMS, then requires one of the public keys in <keys-dir>
# (packages/appdata/releasesig/keys of the source at the release SHA, the keys
# the updaters embed) to verify it. Any failure, including a missing secret or
# a source without keys, fails the job, so nothing is published unsigned.
set -euo pipefail

dir="${1:?usage: sign-sha256sums.sh <dir> <keys-dir>}"
keys="${2:?usage: sign-sha256sums.sh <dir> <keys-dir>}"
sums="$dir/SHA256SUMS"
sig="$dir/SHA256SUMS.sig"

if [ -z "${RELEASE_ED25519_PRIVATE_KEY:-}" ]; then
  echo "::error::Set repository secret RELEASE_ED25519_PRIVATE_KEY (Ed25519 PEM private key)" >&2
  exit 1
fi
[ -s "$sums" ] || { echo "::error::$sums is missing or empty" >&2; exit 1; }
shopt -s nullglob
pubs=("$keys"/*.pem)
if [ "${#pubs[@]}" -eq 0 ]; then
  echo "::error::no public keys in $keys (the source SHA predates the releasesig keys)" >&2
  exit 1
fi

version="$(openssl version)"
echo "$version"
case "$version" in
  "OpenSSL 3."* | "OpenSSL 4."*) ;;
  *) echo "::error::OpenSSL 3 or newer is needed for pkeyutl -rawin" >&2; exit 1 ;;
esac

umask 077
work="$(mktemp -d "${RUNNER_TEMP:-/tmp}/release-sig.XXXXXX")"
trap 'rm -rf "$work"' EXIT
printf '%s\n' "$RELEASE_ED25519_PRIVATE_KEY" > "$work/key.pem"

rm -f "$sig"
openssl pkeyutl -sign -rawin -inkey "$work/key.pem" -in "$sums" -out "$sig"
rm -f "$work/key.pem"

size="$(wc -c < "$sig" | tr -d ' ')"
if [ "$size" != 64 ]; then
  echo "::error::SHA256SUMS.sig is $size bytes, want 64 (is the secret an Ed25519 key?)" >&2
  exit 1
fi

for pub in "${pubs[@]}"; do
  if openssl pkeyutl -verify -rawin -pubin -inkey "$pub" -in "$sums" -sigfile "$sig" >/dev/null 2>&1; then
    echo "SHA256SUMS.sig verifies with $(basename "$pub")"
    exit 0
  fi
done
echo "::error::SHA256SUMS.sig does not verify with any key in $keys; the secret does not match the keys the updaters trust" >&2
exit 1

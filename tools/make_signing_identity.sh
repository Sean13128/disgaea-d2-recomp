#!/bin/sh
# Create a self-signed code-signing identity for local builds, so macOS
# privacy grants (e.g. external-drive access) survive rebuilds.
# Writes signing/d2-signing.p12 (git-ignored). Importing it into your login
# keychain is a separate step you run yourself:
#   security import signing/d2-signing.p12 -k ~/Library/Keychains/login.keychain-db -P d2 -T /usr/bin/codesign
set -eu
cd "$(dirname "$0")/.."
mkdir -p signing
test ! -e signing/d2-signing.p12 || { echo "signing/d2-signing.p12 already exists" >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/cert.cnf" <<'EOF'
[req]
distinguished_name=dn
x509_extensions=ext
prompt=no
[dn]
CN=Disgaea D2 Local Signing
[ext]
basicConstraints=critical,CA:false
keyUsage=critical,digitalSignature
extendedKeyUsage=critical,codeSigning
EOF
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -config "$tmp/cert.cnf" \
    -keyout "$tmp/key.pem" -out "$tmp/cert.pem" 2>/dev/null
openssl pkcs12 -export -legacy -inkey "$tmp/key.pem" -in "$tmp/cert.pem" \
    -out signing/d2-signing.p12 -passout pass:d2 2>/dev/null ||
openssl pkcs12 -export -inkey "$tmp/key.pem" -in "$tmp/cert.pem" \
    -out signing/d2-signing.p12 -passout pass:d2
echo "Created signing/d2-signing.p12 (import password: d2)"

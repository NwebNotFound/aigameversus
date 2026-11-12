#!/usr/bin/env bash
# A small local certificate authority and a server certificate for the read-only LAN page
# (docker-compose.lan.yml, docs/LAN.md). Run once; run it again with --renew when the
# address changes or the server certificate runs out (397 days).
#
#   scripts/make_lan_cert.sh 192.168.178.45        # or LAN_BIND_IP in the environment
#
# Written to deploy/lan/certs/ (gitignored; nothing in it is ever committed or logged):
#   ca/ca.key         the CA's private key: keep it here, it is never mounted anywhere
#   ca/ca.crt         the CA certificate (public)
#   lan-ca.crt        a copy of ca.crt that the proxy serves at http://<address>:3101/ca.crt
#   server/server.key server/server.crt   what nginx uses (the only folder mounted)
#
# The phone trusts ca.crt once (docs/LAN.md); after that every renewed server certificate
# is trusted too. The CA is good for 10 years and can sign ANY name for a phone that trusts
# it (no name constraints), so keep ca/ca.key on this computer and install the CA only on
# your own devices.
set -euo pipefail

renew=0
args=()
for a in "$@"; do
  if [ "$a" = "--renew" ]; then renew=1; else args+=("$a"); fi
done
ip="${args[0]:-${LAN_BIND_IP:-}}"
if [ -z "$ip" ]; then
  echo "usage: scripts/make_lan_cert.sh <LAN address, e.g. 192.168.178.45> [--renew]" >&2
  exit 2
fi
case "$ip" in
  *[!0-9.]* | "") echo "not an IPv4 address: $ip" >&2; exit 2 ;;
esac

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dir="$root/deploy/lan/certs"
mkdir -p "$dir/ca" "$dir/server"
umask 077
# Every path below is relative to $dir: a Windows build of openssl does not know /tmp or /c/...
cd "$dir"
tmp=".work"
rm -rf "$tmp"; mkdir "$tmp"
trap 'rm -rf ".work"' EXIT
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'   # Git Bash on Windows rewrites "/CN=..."

if [ ! -f "ca/ca.key" ] || [ ! -f "ca/ca.crt" ]; then
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "ca/ca.key" 2>/dev/null
  cat > "$tmp/ca.cnf" <<CNF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = AIGameVersus local CA
O = AIGameVersus (this computer only)
[ext]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
CNF
  openssl req -new -x509 -key "ca/ca.key" -days 3650 -sha256 -config "$tmp/ca.cnf" \
    -out "ca/ca.crt"
  echo "created the CA: $dir/ca/ca.crt"
fi
cp "ca/ca.crt" "lan-ca.crt"

if [ "$renew" = 1 ] || [ ! -f "server/server.crt" ] || [ ! -f "server/server.key" ]; then
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "server/server.key" 2>/dev/null
  cat > "$tmp/srv.cnf" <<CNF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = $ip
[ext]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = IP:$ip, DNS:localhost, IP:127.0.0.1
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
CNF
  openssl req -new -key "server/server.key" -config "$tmp/srv.cnf" -out "$tmp/srv.csr"
  # 397 days: the longest an iPhone accepts for a server certificate
  openssl x509 -req -in "$tmp/srv.csr" -CA "ca/ca.crt" -CAkey "ca/ca.key" \
    -CAcreateserial -CAserial "$tmp/ca.srl" -days 397 -sha256 -extfile "$tmp/srv.cnf" \
    -extensions ext -out "server/server.crt" 2>/dev/null
  echo "created the server certificate for $ip, localhost and 127.0.0.1 (397 days)"
fi
chmod 600 "ca/ca.key" "server/server.key" 2>/dev/null || true
echo "trust on the phone: $dir/lan-ca.crt (also at http://$ip:3101/ca.crt once the proxy runs)"

# Watching on a phone: the spectator UI on the home network

The stack listens on `127.0.0.1` only. To watch a match on a phone on the same Wi-Fi or
network, `docker-compose.lan.yml` adds one small container, a read-only nginx in front of
the web UI (`deploy/lan/nginx.conf`):

- It publishes **two ports on one address**: **3443 (https)**, where the page is, and **3101
  (http)**, which only sends you on to https and hands out the CA certificate (below). The
  address is the computer's on the home network (`LAN_BIND_IP` in `.env`). Nothing listens on
  `0.0.0.0`, nothing is forwarded by the router, there is no tunnel: it is not reachable from
  the internet.
- https is TLS 1.2 or 1.3 only, with a certificate from a small local certificate authority
  (CA) that you create once (`scripts/make_lan_cert.sh`). There is **no HSTS** header: a home
  address must not lock a browser into https.
- Only `GET` and `HEAD` pass. Everything else gets `405`, so nobody on the network can start
  a paid match, pause or abort one, or reset anything. The new-match form is hidden (`404`),
  because it could not be submitted.
- The proxy adds `X-AGV-Read-Only: 1` to every request it forwards (and overwrites one sent by
  a client), so the web server shows viewers no buttons and no form link, and refuses writes
  itself too (`web/src/lib/server/read-only.ts`).
- The arena API (`8100`), Postgres, Redis and the ledger keep their `127.0.0.1` bindings.
  The caps and the ledger are untouched.
- The live stream (server-sent events), replays, the leaderboard and the model pages work.
  What the web UI shows in Spectator view (thoughts, hands, roles) is visible to everybody
  on the network: use it only on a network you trust.

## Turn it on

1. In `.env` (gitignored): `LAN_BIND_IP=192.168.178.45` (the address `ipconfig` shows for the
   Ethernet or Wi-Fi adapter; a router that hands out addresses by DHCP can change it, so give
   the computer a fixed address in the router. If it changes anyway: set the new address in
   `.env`, run `scripts/make_lan_cert.sh <new address> --renew`, and start the service again).
2. Make the certificates, once (needs `openssl`; Git Bash on Windows has it):

   ```bash
   scripts/make_lan_cert.sh 192.168.178.45
   ```

   It writes to `deploy/lan/certs/` (gitignored; never commit it, never paste a `.key` file
   anywhere): `ca/ca.key` and `ca/ca.crt` (the CA, 10 years), `lan-ca.crt` (a copy of the
   public CA certificate) and `server/server.key` + `server/server.crt` (the page's
   certificate for the address, `localhost` and `127.0.0.1`, 397 days: the longest an iPhone
   accepts). Only `server/` and `lan-ca.crt` are mounted into the container, **never the CA's
   key**. The plain port redirects only requests addressed to an IP address or `localhost` (a made-up `Host` header gets `400`, not an echo). Renew the server certificate with `--renew`; the CA stays, so the phone keeps
   trusting it.
3. Start only this service; the running stack is not touched:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.models.yml -f docker-compose.lan.yml \
       up -d --no-deps lan
   ```

   Without the models override, leave out `-f docker-compose.models.yml`.
4. Windows blocks inbound connections from other devices by default. Once, in an elevated
   PowerShell (the rule only admits the local subnet, on these two ports):

   ```powershell
   New-NetFirewallRule -DisplayName "AIGameVersus spectator (LAN, read-only)" -Direction Inbound `
     -Action Allow -Protocol TCP -LocalPort 3101,3443 -RemoteAddress LocalSubnet -Profile Any
   ```

   (`-Profile Any` because Windows often files a home Ethernet connection as "Public".)
5. On the phone: `https://<LAN_BIND_IP>:3443` (or `http://<LAN_BIND_IP>:3101`, which redirects).
   The first time the browser warns that the certificate is not trusted: either accept it once
   ("Advanced", "Continue"), or trust the CA as below, and the warning is gone for good.

## Trust the CA on the phone (once)

Open `http://<LAN_BIND_IP>:3101/ca.crt` in the phone's browser. It is the public CA
certificate (the same file as `deploy/lan/certs/lan-ca.crt`); the private key is not served.
Only trust it on your own phone: anyone who holds `ca/ca.key` can make certificates that
phone believes, which is why that key stays in `deploy/lan/certs/ca/` on this computer.

- **iPhone / iPad:** Safari asks to download a profile, then Settings, "Profile downloaded",
  Install. Then Settings, General, About, **Certificate Trust Settings**, switch **AIGameVersus
  local CA** on (full trust). Without this last step iOS ignores the CA.
- **Android:** download the file, then Settings, Security (or "Security & privacy"),
  "Encryption & credentials" (wording differs), Install a certificate, **CA certificate**,
  pick the file. Chrome on Android then trusts it; some apps do not, which does not matter
  for the browser.

## Turn it off

`docker compose -p aigameversus stop lan` (or `rm -sf lan`); remove the rule with
`Remove-NetFirewallRule -DisplayName "AIGameVersus spectator (LAN, read-only)"`; delete the
CA from the phone's settings if you no longer want it there.

## Check it

From the computer (on Windows `curl` uses Schannel, which cannot check revocation for a
private CA: add `--ssl-no-revoke`):

```bash
CA=deploy/lan/certs/ca/ca.crt
curl --ssl-no-revoke --cacert $CA https://<LAN_BIND_IP>:3443/                # 200
curl -I http://<LAN_BIND_IP>:3101/leaderboard                                # 301 to https://...:3443/leaderboard
curl --ssl-no-revoke --cacert $CA -X POST https://<LAN_BIND_IP>:3443/        # 405
curl --ssl-no-revoke --cacert $CA https://<LAN_BIND_IP>:3443/matches/new     # 404
curl --ssl-no-revoke --cacert $CA https://<LAN_BIND_IP>:3443/ | grep -c "New match"   # 0
curl -I --ssl-no-revoke --cacert $CA https://<LAN_BIND_IP>:3443/ | grep -ci strict-transport  # 0: no HSTS
curl -m 3 http://<LAN_BIND_IP>:8100/health                                   # no answer
openssl s_client -connect <LAN_BIND_IP>:3443 -tls1_1 </dev/null              # handshake fails
```

The same page on `http://127.0.0.1:3100` still has the "New match" link: that one is yours.

Not yet verified from a phone: the Windows rule needs an elevated PowerShell (step 4).

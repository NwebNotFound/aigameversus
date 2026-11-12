# Watching on a phone: the spectator UI on the home network

The stack listens on `127.0.0.1` only. To watch a match on a phone on the same Wi-Fi or
network, `docker-compose.lan.yml` adds one small container, a read-only nginx in front of
the web UI (`deploy/lan/nginx.conf`):

- It publishes **one port, 3101, on one address**: the computer's address on the home
  network (`LAN_BIND_IP` in `.env`). Nothing listens on `0.0.0.0`, nothing is forwarded by
  the router, there is no tunnel: it is not reachable from the internet.
- Only `GET` and `HEAD` pass. Everything else gets `405`, so nobody on the network can start
  a paid match, pause or abort one, or reset anything. The new-match form is hidden (`404`),
  because it could not be submitted.
- The arena API (`8100`), Postgres, Redis and the ledger keep their `127.0.0.1` bindings.
  The caps and the ledger are untouched.
- The live stream (server-sent events), replays, the leaderboard and the model pages work.
  What the web UI shows in Spectator view (thoughts, hands, roles) is visible to everybody
  on the network: use it only on a network you trust.

## Turn it on

1. In `.env` (gitignored): `LAN_BIND_IP=192.168.178.45` (the address `ipconfig` shows for the
   Ethernet or Wi-Fi adapter; a router that hands out addresses by DHCP can change it, so give
   the computer a fixed address in the router).
2. Start only this service; the running stack is not touched:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.models.yml -f docker-compose.lan.yml \
       up -d --no-deps lan
   ```

   Without the models override, leave out `-f docker-compose.models.yml`.
3. Windows blocks inbound connections from other devices by default. Once, in an elevated
   PowerShell (the rule only admits the local subnet, on this one port):

   ```powershell
   New-NetFirewallRule -DisplayName "AIGameVersus spectator (LAN, read-only)" -Direction Inbound `
     -Action Allow -Protocol TCP -LocalPort 3101 -RemoteAddress LocalSubnet -Profile Any
   ```

   (`-Profile Any` because Windows often files a home Ethernet connection as "Public".)
4. On the phone: `http://<LAN_BIND_IP>:3101`.

Turn it off: `docker compose -p aigameversus stop lan` (or `rm -sf lan`), and remove the rule
with `Remove-NetFirewallRule -DisplayName "AIGameVersus spectator (LAN, read-only)"`.

Check it from the computer itself: `GET /` answers `200`, `POST /matches/<id>/state` answers
`405`, `GET /matches/new` answers `404`, and `http://<LAN_BIND_IP>:8100/health` does not answer.

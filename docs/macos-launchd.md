# macOS launchd guide

Run HugrGate as a per-user launchd agent. Slice 449.

## 1. Prerequisites

- macOS 13+
- Python 3.10+ (python.org installer or Homebrew)

```bash
pip install "hugrgate[server]"
hugrgate doctor
```

## 2. Configure

```bash
mkdir -p ~/.config/hugrgate ~/Library/Logs/hugrgate \
    ~/Library/Application\ Support/HugrGate
cp deploy/macos/hugrgate.yaml ~/.config/hugrgate/hugrgate.yaml
$EDITOR ~/.config/hugrgate/hugrgate.yaml
```

The macOS config binds `127.0.0.1` — keep it unless a reverse
proxy terminates TLS in front of it.

## 3. Install the agent

```bash
cp deploy/macos/com.hugrgate.daemon.plist ~/Library/LaunchAgents/
# replace REPLACE_ME with your username in the plist paths
sed -i '' "s/REPLACE_ME/$USER/g" \
    ~/Library/LaunchAgents/com.hugrgate.daemon.plist
launchctl load ~/Library/LaunchAgents/com.hugrgate.daemon.plist
```

Verify:

```bash
launchctl list | grep hugrgate
curl localhost:8377/health
```

## 4. Operate

| Task | Command |
|------|---------|
| Status | `launchctl list \| grep hugrgate` |
| Logs | `tail -f ~/Library/Logs/hugrgate/service.log` |
| Restart | `launchctl kickstart -k gui/$(id -u)/com.hugrgate.daemon` |
| Unload | `launchctl unload ~/Library/LaunchAgents/com.hugrgate.daemon.plist` |

`KeepAlive` restarts the daemon on crashes (but not on a clean
exit); `ThrottleInterval` 30 s prevents respawn storms.
Health checks for external monitors: `GET /health`, `GET
/protocol`.

## 5. Notes

- This is a **per-user agent** (`~/Library/LaunchAgents`), not a
  system daemon — it runs while you are logged in. For a
  machine-wide service, move the plist to
  `/Library/LaunchDaemons/`, run it as a dedicated user, and
  point the config at a shared path.
- Upgrades: `pip install -U "hugrgate[server]"`, then
  `launchctl kickstart -k …`. Protocol negotiation keeps old
  clients working (see `docs/migration.md`).

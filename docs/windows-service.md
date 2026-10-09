# Windows service guide

Run HugrGate as a Windows service via
[NSSM](https://nssm.cc/) (the Non-Sucking Service Manager).
Slice 448.

## 1. Prerequisites

- Windows 10/11 or Windows Server 2019+, 64-bit
- Python 3.10+
- NSSM — download `nssm.exe` from https://nssm.cc/download and
  put it on `PATH`

```powershell
pip install "hugrgate[server]"
hugrgate doctor
```

## 2. Configure

Copy the daemon config next to the install script and edit it:

```powershell
Copy-Item deploy\windows\hugrgate.yaml C:\ProgramData\HugrGate\hugrgate.yaml
notepad C:\ProgramData\HugrGate\hugrgate.yaml
```

The Windows config binds `127.0.0.1` by default — keep it
unless a reverse proxy (IIS/ARR, nginx) terminates TLS in front
of it. HugrGate speaks plain HTTP.

## 3. Install the service

From an **elevated** PowerShell:

```powershell
.\deploy\windows\hugrgate-service.ps1 -Install -ConfigPath C:\ProgramData\HugrGate\hugrgate.yaml
```

The script registers the `HugrGate` service: automatic start,
log files under `C:\Program Files\HugrGate\logs` (rotated at
10 MB), restart-on-failure with a 5 s throttle.

Verify:

```powershell
Get-Service HugrGate
Invoke-RestMethod http://127.0.0.1:8377/health
```

## 4. Operate

| Task | Command |
|------|---------|
| Status | `Get-Service HugrGate` |
| Logs | `Get-Content "C:\Program Files\HugrGate\logs\service.log" -Tail 50 -Wait` |
| Restart | `Restart-Service HugrGate` |
| Uninstall | `.\deploy\windows\hugrgate-service.ps1 -Uninstall` |

Health checks for external monitors: `GET /health` (liveness),
`GET /protocol` (version). Both are unauthenticated by design —
bind loopback or firewall the port.

## 5. Notes

- The service runs as `LocalSystem` by default. For least
  privilege, set a dedicated account after install:
  `nssm set HugrGate ObjectName ".\hugr" "password"`.
- Upgrades: `pip install -U "hugrgate[server]"`, then
  `Restart-Service HugrGate`. Protocol negotiation keeps old
  clients working (see `docs/migration.md`).

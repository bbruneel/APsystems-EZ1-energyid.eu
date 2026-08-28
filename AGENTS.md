# AGENTS.md

Guidance for coding agents working in this repository.

## What this project is

A small Python app that:

1. Reads an **APsystems EZ1** microinverter over the **local HTTP API** (library `apsystems-ez1`, default IP `192.168.0.100`, port `8050`).
2. Maps lifetime generation to the EnergyID predefined webhook key `pv`.
3. Queues the payload in SQLite and POSTs pending readings to EnergyID as one JSON object or batch array.

It is intentionally **not** a Home Assistant integration. The sibling project is [Anker-Solarbank-Max-EnergyID.eu](https://github.com/bbruneel/Anker-Solarbank-Max-EnergyID.eu) — follow the same layout, logging, token cache, deploy scripts, and CI style.

## Co-installation defaults (this is the original generic name)

This repo is the original EnergyID monitor. It owns the **generic** CLI, tarball, and install paths. The Solarbank sibling already uses `solarbank`-suffixed names so both can run on one machine.

- CLI command: `energyid-monitor`
- Release tarball: `energyid-monitor-v*.tar.gz` (extracts to `energyid-monitor/`)
- Install dir: `/var/lib/energyid-monitor`
- Log file: `/var/log/energyid/energyid.log`
- systemd: `energyid.service` / `energyid.timer`

Do **not** rename these to `solarbank` (or another device suffix) unless the user explicitly asks — existing deployments depend on the generic names. See `DEPLOYMENT.md`.

## Do not add

- Home Assistant as a dependency
- APsystems cloud / ECU / smartphone-app APIs (local mode only)
- Write/control commands (`set_max_power`, `set_device_power_status`, …) unless the user explicitly asks (this app is read + report)
- Secrets, `.env`, IP addresses of live sites, or tokens in git

## Architecture

```
src/energyid_monitor/
  __main__.py                    python -m energyid_monitor / CLI energyid-monitor
  inverter.py                    EZ1 client, live output + lifetime energy reads
  energyid.py                    /hello, token cache, queue flush, webhook POST
  token_store.py                 SQLite token cache
  reading_store.py               SQLite reading queue + sync_state
  logging_config.py              loguru setup, token masking
  common.py                      required env helper
dbscripts/                       SQLite migrations (tokens + readings queue)
tests/                           offline unit tests (no live inverter / EnergyID)
scripts/                         deploy.sh, package.sh, version.sh
```

Cron/systemd runs `python -m energyid_monitor` as a **one-shot** every few minutes (typically every 5 minutes). Do not turn it into a long-running daemon unless asked.

## EZ1 local API facts

- Protocol: local HTTP API via `APsystemsEZ1M` (`apsystems-ez1` ≥ 2.7.0), default port **8050**
- Inverter must be in **local mode, Continuous**. Setup: https://github.com/SonnenladenGmbH/APsystems-EZ1-API#setup-your-inverter
- Logging out of the phone app after enabling local mode is often required
- Use a **static LAN IP**; default env is `EZ1_IP_ADDRESS=192.168.0.100`
- Two PV inputs: `p1`/`p2` (W) and `e1`/`e2` (kWh)
- Lifetime energy = `get_total_energy_lifetime()` (`e1 + e2`, kWh) — this is what EnergyID receives as `pv`
- Live output = `get_total_output()` (`p1 + p2`, W). The app logs this as kW but **does not** currently send it to EnergyID
- Lifetime-energy failures **must not enqueue** a reading (connection errors bubble up)
- Live-output failures are swallowed as `0.0` W so they never block the lifetime-energy path
- `inverter.py` has a standalone `main()` for a live probe (no EnergyID credentials needed)

Library / setup source:

- https://github.com/SonnenladenGmbH/APsystems-EZ1-API

## EnergyID mapping

Docs: https://help.energyid.eu/en/developer/incoming-webhooks/

| Key | Type | Unit | Source |
| --- | --- | --- | --- |
| `ts` | unix seconds **as a string** | — | `str(int(time.time()))` |
| `pv` | cumulative | kWh | `get_total_energy_lifetime()` |

Keep `ts` as a string. Do not switch it to an integer without an explicit request — that is the payload shape this repo already posts and tests.

Live power is fetched only for logs. If adding a predefined gauge later, EnergyID’s `pwr` is kW (`get_total_output() / 1000`).

Webhook rules to preserve:

- Pass `authorization` and `x-twin-id` headers **exactly** as `/hello` returned them
- Accept HTTP 200 and 201 as success
- On 401, call `/hello` again and retry once
- If `/hello` returns `claimCode` / `claimUrl`, fail with a clear “claim this device” message
- Cache tokens in SQLite with a 1-hour expiry buffer
- Always enqueue each successful lifetime-energy snapshot; flush all pending rows as one JSON array POST
- Do not POST more often than the effective upload interval: `max(ENERGYID_UPLOAD_INTERVAL_SECONDS, cached hello uploadInterval)`, or env only when `ENERGYID_UPLOAD_INTERVAL_OVERRIDE=true`
- When override is false and hello’s interval is not yet cached, call `/hello` once before gating; if that fails, fall back to the env interval (may hit 429)
- Keep readings until `ENERGYID_READING_RETENTION_SECONDS` (default 7 days); mark `sent_at` on success instead of deleting
- On 429, leave rows pending and log `Retry-After`
- Inverter read failure must not enqueue and must not attempt upload

## Commands

```bash
uv sync --extra dev
uv run pytest
uv run black .
uv run isort .
uv run flake8 . --max-line-length=127 --exclude=.venv,venv,__pycache__,.eggs,*.egg,dist,build

# Live inverter only (no EnergyID credentials needed)
ENERGYID_CONSOLE_LOGGING=true uv run python -m energyid_monitor.inverter

# Full EnergyID flow (needs a filled-in .env and a reachable inverter)
ENERGYID_CONSOLE_LOGGING=true uv run python -m energyid_monitor
```

Python: **3.11+** (local `.python-version` is 3.11). Package manager: **uv**. Package name: `ap-easypower-energyid`.

CI (`.github/workflows/python-package-conda.yml`) runs `uv sync --extra dev`, flake8, and pytest on Python 3.11. Releases are draft GitHub releases from `v*` tags (`.github/workflows/release.yml`).

## Conventions

- Match the Solarbank sibling: `src/` layout, `env.example`, `loguru`, `aiosqlite`, deploy/package/version scripts
- Keep functions typed; prefer small modules over a HA-style coordinator
- Never log raw bearer tokens (`logging_config.mask_token`)
- EnergyID /hello and webhook tests belong in `tests/test_energyid.py`; token cache tests in `tests/test_token_store.py`; reading queue tests in `tests/test_reading_store.py`
- Do not hit the real inverter or EnergyID from unit tests — mock `APsystemsEZ1M` and HTTP
- When adding inverter metrics, update the EnergyID mapping (if a predefined key exists), tests, README, and this file

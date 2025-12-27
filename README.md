# EnergyID Monitor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![Release](https://github.com/yourusername/energyid-monitor/actions/workflows/release.yml/badge.svg)](https://github.com/yourusername/energyid-monitor/actions/workflows/release.yml)

Python application that reads solar inverter data from APsystems EZ1 microinverters and sends it to the EnergyID platform every 5 minutes.

This requires
- an APsystems EZ1 microinverter running in local mode. To set your inverter to local mode you can refer to the instructions here: https://github.com/SonnenladenGmbH/APsystems-EZ1-API#setup-your-inverter You might want to logout from the app on your smartphone when doing so. (this GitHub repo provides the dependency to access the microinverter)
- an account on https://www.energyid.eu/en
  - an incoming webhook configured on the energyid.eu platform as described here: https://help.energyid.eu/en/developer/incoming-webhooks/


## Quick Start for Deployment

See the deployment guides:
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Full deployment guide for Linux systems
- **[CRONTAB-SETUP.md](CRONTAB-SETUP.md)** - Quick guide for crontab configuration
- **[DISTRIBUTION.md](DISTRIBUTION.md)** - How to package and distribute this application

### Quick Deploy

```bash
# Use default directories
./scripts/deploy.sh

# Or specify custom directories
./scripts/deploy.sh --install-dir /opt/energyid --log-dir /var/log/app

# View all options
./scripts/deploy.sh --help
```

Then configure your credentials in the appropriate `.env` file (default: `/var/lib/energyid-monitor/.env`) and set up crontab.

---

## EnergyID webhook Setup

As mentioned above, you need an incoming webhook configured on the energyid.eu platform as described here: https://help.energyid.eu/en/developer/incoming-webhooks/

Step by step instruction is also described here: https://app.energyid.eu/integrations/Webhook-In

Two ready-to-run example curl commands for EnergyID integration.

### Hello endpoint
- Use this to verify provisioning keys and **Device provisioning** and opening the URL in the *Claim* response in a browser.
- Use it again, after confirming the URL in a browser, to get the *bearer* token and *twin-id*.

```bash
curl -X POST "https://hooks.energyid.eu/hello" \
  -H "Content-Type: application/json" \
  -H "X-Provisioning-Key: ENERGYID_KEY" \
  -H "X-Provisioning-Secret: ENERGYID_SECRET" \
  -d '{
    "deviceId": "ENERGYID_YOUR_DEVICE_ID",
    "deviceName": "ENERGYID_YOUR_DEVICE_NAME"
  }'
```

### Webhook ingestion
Do a test and send measurements to the webhook with the headers from the response of the above. Put real data in the payload where `ts` is a https://www.unixtimestamp.com/ and 'pv' is the current total in kWh of your EZ1 microinverter.

```bash
curl -w "%{response_code}" -X POST "https://hooks.energyid.eu/webhook-in" \
  -H "Content-Type: application/json" \
  -H "authorization: ENERGYID_BEARER_TOKEN" \
  -H "x-twin-id: ENERGYID_TWIN_ID" \
  -d '{
    "ts": "1764950877",
    "pv": 67.67
  }'
```

## Troubleshooting
- Corporate SSL intercepts: point Python/uv to your CA bundle before running commands (PowerShell example)  
  ```powershell
  $env:SSL_CERT_FILE = 'C:\PathTo\cacert.pem'
  ```
- Bash example:
  ```bash
  export SSL_CERT_FILE="/PathTo/cacert.pem"
  ```

## EnergyID Python flow (hello + webhook)
- Set the required environment variables (can be in `.env`). See [env.example](env.example)
- Run the end-to-end flow (retrieves tokens via hello, reads live PV from the inverter, posts to webhook-in):
  ```bash
  python -m energyid_monitor
  ```
  Or, if installed as a package:
  ```bash
  energyid-monitor
  ```
  Output includes structured logs with bearer/twin IDs from hello and the webhook response body.

## Token Caching Database

The application uses SQLite to cache EnergyID bearer tokens and avoid unnecessary API calls.

### Database Setup

- **Database Location**: `data/token.db` (automatically created on first run)
- **SQLite Installation**: SQLite3 is typically pre-installed on most Linux systems. If needed:
  ```bash
  # Ubuntu/Debian
  sudo apt-get install sqlite3
  
  # macOS (usually pre-installed)
  brew install sqlite3
  ```
- **Schema Migrations**: Database tables are automatically created from SQL scripts in `dbscripts/` when the application first runs.

### How Token Caching Works

1. On startup, the application checks the database for a valid bearer token
2. If a token exists and is not expired (with a 1-hour buffer), it uses the cached token
3. If no token exists or it's expired/expiring soon, it fetches a new token from the EnergyID hello endpoint
4. New tokens are stored in the database with their expiration time (extracted from the JWT)

This reduces API calls and improves reliability by reusing valid tokens across multiple runs.

### Database Management

- **View tokens**: 
  ```bash
  sqlite3 data/token.db "SELECT bearer_token, twin_id, datetime(exp, 'unixepoch') as expires_at FROM tokens ORDER BY exp DESC LIMIT 5;"
  ```
- **Clear cache**: 
  ```bash
  rm data/token.db
  ```
  The database will be recreated on the next run.

## Logging

The application uses loguru for structured logging with automatic rotation, compression, and retention.

### Log Features

- **Automatic rotation**: Logs rotate daily at midnight
- **Compression**: Rotated logs are automatically compressed with gzip
- **Retention**: Old logs are automatically deleted after 30 days
- **Structured format**: Logs include timestamps, log levels, module/function names, and line numbers
- **Security**: Bearer tokens are automatically masked in all log entries

### Configuring Logging

You can configure logging via environment variables or `.env` file:

```bash
# Log level (default: INFO)
ENERGYID_LOG_LEVEL=DEBUG  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# Log file path (default: /var/log/energyid/energyid.log)
ENERGYID_LOG_FILE=/path/to/your/logs/energyid.log

# Enable console logging to stdout (default: false)
ENERGYID_CONSOLE_LOGGING=true  # Set to true to enable console output
```

**Note**: If the application doesn't have permission to create the log directory at the specified location, it will automatically fallback to `~/.local/log/energyid/energyid.log`. This allows the application to run during development without requiring elevated permissions.

### Log Levels

- `DEBUG` - Detailed information for debugging (includes full token details, response bodies)
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages (connection issues, missing data)
- `ERROR` - Error messages (exceptions, failures)
- `CRITICAL` - Critical errors only

### Viewing Logs

```bash
# View recent log entries
tail -f /var/log/energyid/energyid.log

# Search for errors
grep "ERROR" /var/log/energyid/energyid.log

# View with debug level (set in .env or environment)
ENERGYID_LOG_LEVEL=DEBUG python -m energyid_monitor
```

For more detailed logging configuration, see [DEPLOYMENT.md](DEPLOYMENT.md#logging-configuration).

## Releases and Versioning

This project uses semantic versioning (e.g., `1.0.0`, `2.1.3`). Releases are automatically created via GitHub Actions when git tags are pushed.

### Downloading Releases

You can download pre-built distribution packages from the [GitHub Releases page](https://github.com/yourusername/energyid-monitor/releases). Each release includes:
- Distribution package (`energyid-monitor-vX.Y.Z.tar.gz`)
- Changelog with commits since the previous release
- Release notes

### Creating a Release

Releases are created automatically when you push a git tag:

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

The GitHub Actions workflow will:
1. Run tests to ensure code quality
2. Update version in project files
3. Generate changelog from git commits
4. Create distribution package
5. Create a draft GitHub release for review

See [DISTRIBUTION.md](DISTRIBUTION.md) for more details about the release process and packaging.

## Inverter Setup
### Local inverter configuration
- Create a `.env` file in the project root or installation directory to set your inverter IP:
  ```
  EZ1_IP_ADDRESS=192.168.0.100
  ```
- The application will load this value (falling back to `192.168.0.100` if missing).
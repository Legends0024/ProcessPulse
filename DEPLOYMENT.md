# ProcessPulse deployment

## Local backend

From `C:\Users\manav\ProcessPulse`:

```powershell
.\.venv\Scripts\python.exe .\app.py
```

The dashboard is available at `http://127.0.0.1:5000`.

For local process termination, open **Settings**, enter
`dev-admin-token-change-in-production` in **Process control token**, and save
the field. For any shared or production deployment, set `DEVICE_ADMIN_TOKEN`
to a new secret and enter that value instead. Never put the production
administrator token in frontend source code.

## Agent enrollment

Set these variables on each authorized Windows computer. Each computer must
use a different `DEVICE_ID`.

```powershell
$env:API_ENDPOINT = "https://your-service.onrender.com"
$env:DEVICE_ID = "office-pc-01"
$env:DEVICE_NAME = "Office PC 01"
$env:DEVICE_REGISTRATION_TOKEN = "the-enrollment-secret"
$env:AGENT_INTERVAL = "5"
.\.venv\Scripts\python.exe .\agent\agent.py
```

On its first run the agent registers the device, receives a unique device
credential, and stores it in `.processpulse-device-token`. The credential is
never returned by device-list or metric APIs. Keep the token file private.
Use a distinct `DEVICE_TOKEN_FILE` path when several agents share a directory.

To connect another computer, install the project dependencies there, set a
new `DEVICE_ID` and `DEVICE_NAME`, and use the same enrollment secret. Do not
copy the first computer's token file.

## Required production variables

Set these in the hosting provider:

- `SECRET_KEY`: long random Flask secret
- `DATABASE_URL`: PostgreSQL connection string
- `DEVICE_REGISTRATION_TOKEN`: enrollment secret used only during agent setup
- `DEVICE_ADMIN_TOKEN`: secret for device revocation
- `ALLOW_LEGACY_AGENT_TOKEN=0`
- `HEARTBEAT_TIMEOUT_SECONDS=30`
- `CORS_ORIGINS`: only trusted dashboard origins

The agent requires `API_ENDPOINT`, `DEVICE_ID`, and
`DEVICE_REGISTRATION_TOKEN` for initial enrollment. After enrollment it can
use the saved device token without the enrollment secret.

## Render

The included `render.yaml` creates a Gunicorn web service and PostgreSQL
database. Review the generated service URL and set `API_ENDPOINT` to that URL
before starting remote agents. Render provides HTTPS for the service, so
agents should use an `https://` endpoint.

Deploying the web service does not install agents on remote computers. Each
authorized computer must run its own agent and have a unique registered
device. Remote-network operation should be tested from the actual target
network before relying on it in production.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

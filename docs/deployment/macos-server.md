# MoTitle — macOS Server Deployment Runbook

This runbook covers deploying MoTitle as a persistent server appliance on an Apple Silicon Mac. The setup installs two LaunchDaemons (Ollama + MoTitle server) that start automatically at boot, survive reboots, and run without anyone logged in.

---

## 1. Prerequisites

**Hardware**

- Apple Silicon Mac (M1 / M2 / M3 / M4 family). `setup-mac.sh` enforces `uname -m == arm64` and will refuse to run on Intel Macs. Intel users should use `setup.sh` instead.
- **Unified memory**: the default LLM (`qwen3.5:35b-a3b-mlx-bf16`) is a 35B MoE model loaded in bf16. It occupies roughly 70 GB of unified memory. A Mac with less than 64 GB unified memory will likely run too slowly for production use; 128 GB is comfortable.
- **Disk space**: the model download alone is approximately 70 GB. Allow at least **90 GB free** before running setup. Check with `df -h /`.
- **Power**: plug the Mac in. `caffeinate` in the daemon prevents idle and system sleep, but AC power is required for a server-grade always-on workload.

**Software (installed automatically by `setup-mac.sh`)**

- macOS Sonoma 14 or later (Sequoia 15 recommended)
- Xcode Command Line Tools (`xcode-select --install`)
- Homebrew — `setup-mac.sh` auto-installs Homebrew if absent (you'll be asked to press Return + your password); or pre-install it from https://brew.sh.
- FFmpeg, Ollama, and `uv` are pulled via Homebrew by the script.
- The Python venv uses a **self-contained CPython 3.11 via `uv`** (not Homebrew's python). This avoids a class of failures on bleeding-edge macOS where Homebrew's python has a broken `pyexpat` (libexpat symbol mismatch) that breaks `pip`/`venv`.

**Install location (IMPORTANT)**

- Put the app under a **non-protected** path such as **`/opt/motitle`**. Do **NOT** install under `~/Documents`, `~/Desktop`, or `~/Downloads` — macOS privacy protection (TCC) blocks **background services (launchd)** from executing files there, so the server crash-loops with `Operation not permitted`. `setup-mac.sh` refuses to run from those folders and prints the `mv` commands to relocate.

**Network**

- The Mac must be reachable at a stable LAN IP. Either configure a static IP in System Settings → Network, or reserve the DHCP lease on your router.
- The default pipeline is **fully local** (no internet needed at runtime). Only if you enable **Beta (OpenRouter) mode** (Section 7) does the server need outbound HTTPS to `openrouter.ai:443`. Test with `curl https://openrouter.ai/api/v1/models`.

---

## 2. Install

Place the app under `/opt/motitle` (see "Install location" above) and run the setup script:

```bash
# get the source onto /opt (clone, or copy the folder there)
sudo git clone https://github.com/your-org/motitle.git /opt/motitle
sudo chown -R "$(whoami)" /opt/motitle
cd /opt/motitle
./setup-mac.sh
```

Re-running the script is **safe**: the admin user, the `FLASK_SECRET_KEY` (and any other `backend/.env` vars such as `OPENROUTER_API_KEY`), and an already-downloaded model are all preserved; the HTTPS cert is regenerated.

> The ~70 GB model is pulled in the **background**, and only **after** the launchd-service step — the installer does **not** wait for it, so the server can be installed and the licence activated while the model downloads. Watch it with `tail -f /opt/motitle/backend/data/logs/ollama-pull.log` or `ollama list`.

What the script does, in order:

1. **Architecture + location check** — aborts on Intel (`x86_64`); refuses to run from `~/Documents`, `~/Desktop`, or `~/Downloads` (macOS TCC; see "Install location") and prints the `mv`-to-`/opt` commands.
2. **Homebrew** — auto-installs Homebrew if absent, then `eval "$(brew shellenv)"` to put it on PATH.
3. **Dependencies** — `brew install ollama uv` + **`ffmpeg-full`** (the lean `ffmpeg` formula lacks libass, so the `ass` subtitle-burn-in filter is missing and renders fail; `ffmpeg-full` bundles libass and is force-linked onto PATH). Skips already-installed packages; creates the runtime `data/` directories.
4. **Python venv** — `uv venv --seed --python 3.11` creates `backend/venv/` with a self-contained CPython, then installs all packages from `backend/requirements.txt` + `mlx-whisper` via `uv pip`. (`whisper-streaming` is intentionally excluded — Linux-only.)
5. **PyNaCl check** — verifies the licensing crypto library imports (fails fast if a native build went wrong).
6. **Admin user bootstrap** — **loops** prompting for an admin username + password until a valid one is accepted (min 8 chars, not a common password), then writes the account into `backend/data/app.db`. Skipped on re-runs if an admin already exists. (It no longer silently skips a weak password.)
7. **`FLASK_SECRET_KEY`** — generates a 64-character hex secret into `backend/.env` (gitignored, `chmod 600`) on first run; preserved on re-run. The server refuses to start without it.
8. **Self-signed HTTPS certificate** — generates `backend/data/certs/server.{crt,key}` (2048-bit RSA, 10-year). Clients see a browser warning on first connection; see Section 4.
9. **`Core setup complete`** then **Optional LaunchDaemon install** — prompts whether to install the two LaunchDaemons now (`sudo packaging/macos/motitle-service.sh install`). You can also do it later (Section 3).
10. **Ollama model** — runs **after** the service decision: ensures the ollama server is up, then pulls `qwen3.5:35b-a3b-mlx-bf16` (~70 GB) in the **background** (disk-checked; skipped if already present). Progress goes to `backend/data/logs/ollama-pull.log`.
11. **LAN URL + licence banner** — prints the Mac's LAN IP and the licence-activation reminder.

After a successful run the server is accessible at `https://<mac-ip>:5001` (HTTPS is the default once the cert exists; `http://<mac-ip>:5001` only if no cert).

---

## 2.5 License Activation (REQUIRED before first use)

> **This build gates all AI features behind a signed license.** A fresh install
> is intentionally locked: until a valid license token is activated, every
> functional route returns `403 {"error":"licence required"}` and the browser is
> redirected to a License Activation page. **This is expected, not a fault.**

What still works without a license: logging in, the License Activation page
(`/license.html`), and the health endpoint. Everything else (transcribe,
translate, render, model load) is blocked until activation.

**Activation steps (one-time, per machine):**

1. Open `http://<mac-ip>:5001` — you will be redirected to `/license.html`.
2. Log in with the admin account created during setup.
3. On the activation page, copy the **install ID** (this Mac's hardware-bound identifier).
4. Send the install ID to the vendor. The vendor returns a **signed license token**
   (Ed25519-signed; tied to this install ID; offline — no internet required).
5. Paste the token on `/license.html` and submit. The token is stored at
   `backend/config/license.json`. The gate unlocks immediately (no restart needed).

**Verify activation:**
```bash
curl -sk https://localhost:5001/api/files   # -k: self-signed cert; http:// only if no cert
# Before activation: {"error":"licence required"}
# After activation:  a normal JSON response (not the licence error)
```

**Notes:**
- The license is **air-gapped**: no call-home, no online revocation. Expiry +
  manual re-issue is the renewal path.
- `backend/config/license.json` is per-deployment (gitignored). Back it up; on a
  rebuild you can restore it instead of re-activating, as long as the install ID
  is unchanged.
- For an internal/demo machine you control, ask the vendor for a long-validity
  token rather than bypassing the gate.

---

## 3. Service Management

All service operations require `sudo`:

```bash
sudo packaging/macos/motitle-service.sh <subcommand>
```

| Subcommand | What it does |
|---|---|
| `install` | Renders the two plist templates (`__USER__`, `__REPO__`, `__OLLAMA_BIN__` substituted), copies them to `/Library/LaunchDaemons/`, and calls `launchctl bootstrap system` on each. Both daemons start immediately (`RunAtLoad true`) and will restart on crash (`KeepAlive true`). Stops any `brew services` Ollama instance first to avoid port conflicts. |
| `uninstall` | Calls `launchctl bootout` on both daemons and removes their plists from `/Library/LaunchDaemons/`. The venv, data files, and model remain on disk. |
| `start` | Re-bootstraps both daemons from their plists on disk. Use this after a manual `stop` or after `install` if you need to start without rebooting. |
| `stop` | Calls `launchctl bootout` on both daemons. They will NOT restart until you run `start` or reboot the machine. `KeepAlive` only restarts after a crash, not after an operator-initiated `bootout`. |
| `restart` | `bootout` both → `bootstrap` both. Useful after changing `backend/.env` or updating the code. |
| `status` | Prints the launchd state and PID for both daemons, then health-checks `https://localhost:5001/api/ready` (falling back to `http://`) and runs `ollama ps` to show which models are loaded. |
| `logs` | Tails the last 50 lines of `backend/data/logs/server.out.log` and `server.out.log` together, then follows both live (Ctrl-C to quit). Ollama logs are at `backend/data/logs/ollama.{out,err}.log`. |

**Bootstrap vs kickstart**: the `start` subcommand uses `launchctl bootstrap … <plist>` (not `kickstart`). Because the plists have `RunAtLoad true`, the daemon starts the moment it is bootstrapped — no separate kickstart needed.

**Reboots**: both daemons are system-level LaunchDaemons (`/Library/LaunchDaemons/`), so they start at boot before any user logs in. No login session is required.

---

## 4. LAN Access

Find the Mac's LAN IP:

```bash
ipconfig getifaddr en0        # Wi-Fi
ipconfig getifaddr en1        # Ethernet on some Macs
```

Or use the Bonjour hostname (no IP lookup needed):

```
http://<computer-name>.local:5001
```

Replace `<computer-name>` with the value from System Settings → General → Sharing → Local hostname (without `.local`).

Clients open one of:

```
http://<mac-ip>:5001          # plain HTTP — works for the full upload→transcribe flow
https://<mac-ip>:5001         # HTTPS — self-signed cert, browser warning on first visit
```

**macOS firewall prompt**: the first time a client connects, macOS may show a dialog asking whether to allow incoming connections on port 5001. Click **Allow**. If the dialog does not appear and connections are refused, go to System Settings → Network → Firewall → Options and add `python3.11` (or the venv Python) with **Allow incoming connections**.

**HTTPS self-signed certificate**: browsers will show a "Your connection is not private" warning. To accept it in Chrome/Edge, click Advanced → Proceed. In Safari, click Show Details → visit this website → Allow. For a persistent fix on macOS clients, distribute `backend/data/certs/server.crt` and add it to the system keychain with **Always Trust**.

**Recommended network setup**:

- Reserve the Mac's DHCP lease on your router so its IP never changes.
- Alternatively, configure a static IP in System Settings → Network → your interface → Details → TCP/IP → Configure IP: Manually.
- For team use, a simple DNS entry (e.g. `motitle.local.yourcompany.com`) is more memorable than an IP.

---

## 5. Troubleshooting

### Server does not start — `FLASK_SECRET_KEY` missing

The launcher (`packaging/macos/motitle-launcher.sh`) reads `FLASK_SECRET_KEY` from `backend/.env` before starting Python. If the file is missing or the key is empty, the launcher exits immediately with a FATAL message and launchd logs the failure.

Check:

```bash
cat backend/.env | grep FLASK_SECRET_KEY
```

If the file is missing or the line is absent, regenerate it:

```bash
python3 -c "import secrets; print('FLASK_SECRET_KEY=' + secrets.token_hex(32))" >> backend/.env
sudo packaging/macos/motitle-service.sh restart
```

### Port 5001 is occupied — stale `Python` process

A previous server process that was not properly stopped (e.g. after a forced reboot or a kill signal) can leave a capitalised `Python` process squatting port 5001. launchd will keep trying to start the daemon and failing.

Diagnose:

```bash
lsof -i :5001
```

If a `Python` process is listed that is NOT the launchd-managed one, kill it by PID:

```bash
sudo kill <pid>
```

Then restart the daemon:

```bash
sudo packaging/macos/motitle-service.sh restart
```

### Checking logs

```bash
# Live tail (both stdout + stderr):
sudo packaging/macos/motitle-service.sh logs

# Or directly:
tail -f backend/data/logs/server.err.log
tail -f backend/data/logs/server.out.log
tail -f backend/data/logs/ollama.err.log
```

The server prints its startup sequence (venv activation, FLASK_SECRET_KEY loaded, Flask listening) to `server.out.log`. Python tracebacks appear in `server.err.log`.

### Ollama not responding

```bash
ollama ps                          # shows loaded models
curl http://localhost:11434/api/tags  # lists available models
```

Check that the Ollama daemon is loaded:

```bash
launchctl print system/com.motitle.ollama
```

If it shows `state = not running`, restart it:

```bash
sudo packaging/macos/motitle-service.sh restart
```

If Ollama is running but the model is not listed, the pull may not have completed. Re-pull:

```bash
ollama pull qwen3.5:35b-a3b-mlx-bf16
```

### Model not pulled or corrupted

Re-running the pull is safe — Ollama resumes from where it left off:

```bash
ollama pull qwen3.5:35b-a3b-mlx-bf16
```

After the pull completes, restart the server so it can detect the model:

```bash
sudo packaging/macos/motitle-service.sh restart
```

### Mac goes to sleep

The launcher wraps the Python process in `caffeinate -is`, which prevents idle sleep and system sleep as long as the process is running. However, `caffeinate` does not override a manual sleep command or a scheduled shutdown.

To verify caffeinate is active:

```bash
pgrep caffeinate
```

If the process is missing, the daemon may have crashed. Check:

```bash
sudo packaging/macos/motitle-service.sh status
sudo packaging/macos/motitle-service.sh logs
```

Also ensure the Mac is on AC power — macOS may override caffeinate on battery in low-power mode.

### Checking daemon state after a reboot

After the Mac restarts:

```bash
sudo packaging/macos/motitle-service.sh status
```

Both `com.motitle.server` and `com.motitle.ollama` should show `state = running`. The server is typically ready within 30–60 seconds of boot (Ollama must load before the first translation request, which takes a further 10–30 seconds depending on the model).

---

## 6. Uninstall

Stop the daemons and remove the plists:

```bash
sudo packaging/macos/motitle-service.sh uninstall
```

This calls `launchctl bootout` on both daemons and deletes their plists from `/Library/LaunchDaemons/`. The services will not restart on the next reboot.

The following are **not** removed by uninstall and must be cleaned up manually if desired:

- `backend/venv/` — Python virtual environment (~3–5 GB)
- `backend/data/` — uploads, renders, database, logs, and HTTPS certificates
- Homebrew packages (`python@3.11`, `ffmpeg`, `ollama`) — remove with `brew uninstall`
- Ollama model — remove with `ollama rm qwen3.5:35b-a3b-mlx-bf16` (~70 GB freed)
- `backend/config/license.json` — the activated license (keep it if you may reinstall)
- The repository clone itself — `rm -rf motitle/`

---

## 7. Optional features

### Beta (OpenRouter) mode — cloud LLM

By default translation runs on the local Ollama model. An admin can flip a global
**Beta** toggle so the translation/refiner LLM routes to OpenRouter instead (ASR
**always** stays local mlx-whisper). This is useful for comparison or when local
LLM capacity is constrained.

- Enable it from the admin UI; it sets `beta_openrouter` in `backend/config/settings.json`.
- Provide an OpenRouter API key via the admin Beta pane. The key is persisted to
  `backend/.env` as `OPENROUTER_API_KEY` (file kept at `chmod 600`) and re-loaded
  on every boot by `app.py`, so it survives restarts — no need to add it to the
  launchd passthrough list.
- Requires outbound HTTPS to `openrouter.ai:443` (see Prerequisites → Network).
- There is **no fallback**: if Beta is on and the key is missing/invalid, translation
  fails rather than silently reverting to local. Turn Beta off to return to local.

### Custom subtitle fonts

Operators can upload custom fonts through the admin UI (`/api/fonts` GET/POST/DELETE).
Uploaded fonts are stored under `backend/assets/fonts/` and become selectable in the
render options — no pre-configuration or restart needed. The LaunchDaemon installer
ensures this directory is owned by the service user so uploads succeed.

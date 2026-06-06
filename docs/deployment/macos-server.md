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
- Homebrew — `setup-mac.sh` installs Homebrew if absent; if you prefer to pre-install it, see https://brew.sh.
- Python 3.11, FFmpeg, and Ollama are pulled via Homebrew by the script.

**Network**

- The Mac must be reachable at a stable LAN IP. Either configure a static IP in System Settings → Network, or reserve the DHCP lease on your router.

---

## 2. Install

Clone the repository and run the setup script:

```bash
git clone https://github.com/your-org/motitle.git
cd motitle
./setup-mac.sh
```

The script is **idempotent** — re-running it after a partial failure or an update is safe. Each step is skipped if it has already been completed.

What the script does, in order:

1. **Architecture check** — aborts with a clear error on Intel (`x86_64`).
2. **Homebrew** — installs Homebrew if absent; runs `brew update`.
3. **Dependencies** — `brew install python@3.11 ffmpeg ollama` (skips already-installed packages).
4. **Python venv** — creates `backend/venv/` and installs all Python packages from `backend/requirements.txt`, including `mlx-whisper` for Apple Silicon.
5. **Admin user bootstrap** — prompts for an admin username and password (minimum 8 characters, must not be a common password). Writes the account into `backend/data/app.db`. Safe to skip on re-runs if the user already exists.
6. **`FLASK_SECRET_KEY`** — generates a 64-character hex secret with `python -c "import secrets; print(secrets.token_hex(32))"` and writes it to `backend/.env` (gitignored). The server will refuse to start without this value.
7. **Self-signed HTTPS certificate** — generates `backend/data/certs/server.{crt,key}` with OpenSSL (2048-bit RSA, 10-year validity). Clients will see a browser warning on first connection; see Section 4 for workarounds.
8. **Disk space check** — warns if fewer than 90 GB are free before attempting the model pull.
9. **`ollama pull qwen3.5:35b-a3b-mlx-bf16`** — downloads the ~70 GB model. This takes 15–60 minutes depending on bandwidth. Progress is printed to the terminal.
10. **Optional LaunchDaemon install** — prompts whether to install the two LaunchDaemons now. If you answer yes, it calls `sudo packaging/macos/motitle-service.sh install`. You can also do this later (see Section 3).
11. **LAN URL** — prints the Mac's LAN IP address so you can test from another device immediately.

After a successful run the server is accessible at `http://<mac-ip>:5001` (or `https://<mac-ip>:5001` if HTTPS certs are present).

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
| `status` | Prints the launchd state and PID for both daemons, then hits `http://localhost:5001/api/ready` and runs `ollama ps` to show which models are loaded. |
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
- The repository clone itself — `rm -rf motitle/`

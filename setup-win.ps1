# setup-win.ps1 — Windows + NVIDIA installer (R5 Phase 1)
# Provisions venv + faster-whisper + CUDA wheels, bootstraps an admin user,
# and writes backend\.env with a freshly-generated FLASK_SECRET_KEY.
$ErrorActionPreference = "Stop"

# Check prerequisites
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.11 required: winget install --id Python.Python.3.11 -e"
}
if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "FFmpeg required: winget install --id Gyan.FFmpeg -e"
}

# Backend setup
Push-Location backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
# CUDA runtime wheels for GPU acceleration (ctranslate2 4.7 needs cublas64_12 + cudnn64_9)
pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12

# Admin bootstrap
Write-Host "`n=== Set up admin user ==="
$adminUser = Read-Host "Admin username [admin]"
if (-not $adminUser) { $adminUser = "admin" }
$adminPw = Read-Host "Admin password" -AsSecureString
$adminPw2 = Read-Host "Confirm password" -AsSecureString
$pw1 = [System.Net.NetworkCredential]::new("", $adminPw).Password
$pw2 = [System.Net.NetworkCredential]::new("", $adminPw2).Password
if ($pw1 -ne $pw2) { Write-Error "Passwords don't match" }

# Pass username + password via env (NOT string interpolation) so values
# containing quotes / shell metacharacters can't break out of the python
# heredoc.
$env:ADMIN_USER = $adminUser
$env:ADMIN_PW = $pw1
python -c @"
import os
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db',
                os.environ['ADMIN_USER'],
                os.environ['ADMIN_PW'],
                is_admin=True)
    print('Admin created.')
except ValueError as e:
    print(f'Skipped: {e}')
"@
Remove-Item Env:ADMIN_USER
Remove-Item Env:ADMIN_PW

# Secret key
$secret = python -c "import secrets; print(secrets.token_hex(32))"
"FLASK_SECRET_KEY=$secret" | Out-File -FilePath .env -Encoding utf8

Write-Host "`nSetup complete. Source backend\.env then run python app.py."
Pop-Location

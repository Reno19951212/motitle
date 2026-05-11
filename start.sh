#!/bin/bash
# MoTitle - Start Script
set -e

SCRIPT_DIR="$(dirname "$0")"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "=================================================="
echo "  MoTitle — 廣播字幕製作系統"
echo "=================================================="

# Check venv
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "⚠  虛擬環境未找到，請先運行 setup-mac.sh 或 setup.sh"
    exit 1
fi

# Load settings from .env (required — app crashes without FLASK_SECRET_KEY)
if [ -f "$BACKEND_DIR/.env" ]; then
    export FLASK_SECRET_KEY
    FLASK_SECRET_KEY=$(grep -E '^FLASK_SECRET_KEY=' "$BACKEND_DIR/.env" | cut -d= -f2-)
    if [ -z "$FLASK_SECRET_KEY" ]; then
        echo "⚠  .env 存在但 FLASK_SECRET_KEY 為空"
        exit 1
    fi
    # Load optional settings
    R5_HTTPS_VAL=$(grep -E '^R5_HTTPS=' "$BACKEND_DIR/.env" | cut -d= -f2-)
    if [ -n "$R5_HTTPS_VAL" ]; then
        export R5_HTTPS="$R5_HTTPS_VAL"
    fi
else
    echo "⚠  找不到 backend/.env，請先運行 setup-mac.sh 或手動建立："
    echo "   python3 -c \"import secrets; print('FLASK_SECRET_KEY=' + secrets.token_hex(32))\" > backend/.env"
    exit 1
fi

PORT="${FLASK_PORT:-5001}"

echo "🚀 啟動後端服務器 (port $PORT)..."
cd "$BACKEND_DIR"
source venv/bin/activate

# Start backend in background
python app.py &
BACKEND_PID=$!

echo "✓ 後端服務器已啟動 (PID: $BACKEND_PID)"
echo ""

# Wait a moment for server to start
sleep 2

# Verify server is up
if curl -s "http://localhost:$PORT/api/ready" | grep -q '"ready":true'; then
    echo "✓ 服務器健康檢查通過"
else
    echo "⚠  服務器未能正常啟動，請查看上方錯誤信息"
fi

# Open browser
echo "🌐 打開瀏覽器..."
if command -v open &> /dev/null; then
    open "http://localhost:$PORT"
elif command -v xdg-open &> /dev/null; then
    xdg-open "http://localhost:$PORT"
fi

echo ""
echo "=================================================="
echo "  應用程式已啟動!"
echo "  URL: http://localhost:$PORT"
echo "  管理後台: http://localhost:$PORT/admin.html"
echo ""
echo "  按 Ctrl+C 停止服務器"
echo "=================================================="

# Wait for Ctrl+C
trap "kill $BACKEND_PID 2>/dev/null; echo '服務器已停止'" EXIT
wait $BACKEND_PID

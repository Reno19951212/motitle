#!/bin/bash
# Whisper AI Web App - Start Script
set -e

SCRIPT_DIR="$(dirname "$0")"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "=================================================="
echo "  AI 字幕轉換 APP"
echo "=================================================="

# Check venv
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "⚠  虛擬環境未找到，請先運行 setup.sh"
    exit 1
fi

echo "🚀 啟動後端服務器..."
cd "$BACKEND_DIR"
source venv/bin/activate

# Start backend in background
python app.py &
BACKEND_PID=$!

echo "✓ 後端服務器已啟動 (PID: $BACKEND_PID)"
echo ""

# Wait a moment for server to start
sleep 2

# Open frontend in browser
echo "🌐 打開前端..."
FRONTEND_PATH="$FRONTEND_DIR/index.html"

if command -v open &> /dev/null; then
    open "$FRONTEND_PATH"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$FRONTEND_PATH"
fi

echo ""
echo "=================================================="
echo "  應用程式已啟動!"
echo "  後端 API: http://localhost:5000"
echo "  前端: $FRONTEND_PATH"
echo ""
echo "  按 Ctrl+C 停止服務器"
echo "=================================================="

# Wait for Ctrl+C
trap "kill $BACKEND_PID 2>/dev/null; echo '服務器已停止'" EXIT
wait $BACKEND_PID

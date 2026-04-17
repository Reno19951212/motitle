#!/bin/bash
# MoTitle - Setup Script
set -e

echo "=================================================="
echo "  MoTitle — 廣播字幕製作系統 — 安裝設置"
echo "=================================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，請先安裝 Python 3.8+"
    exit 1
fi
echo "✓ Python: $(python3 --version)"

# Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠  未找到 FFmpeg，正在嘗試安裝..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    elif command -v apt-get &> /dev/null; then
        sudo apt-get install -y ffmpeg
    else
        echo "❌ 請手動安裝 FFmpeg: https://ffmpeg.org/download.html"
        exit 1
    fi
fi
echo "✓ FFmpeg: $(ffmpeg -version 2>&1 | head -1)"

# Create virtual environment
echo ""
echo "📦 創建虛擬環境..."
cd "$(dirname "$0")/backend"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install dependencies
echo "📦 安裝 Python 依賴..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ 依賴安裝完成"

echo ""
echo "=================================================="
echo "  安裝完成！"
echo "=================================================="
echo ""
echo "  啟動後端服務器:"
echo "    cd backend && source venv/bin/activate && python app.py"
echo ""
echo "  打開前端:"
echo "    open ../frontend/index.html"
echo "    或直接在瀏覽器中打開 frontend/index.html"
echo ""
echo "  服務器地址: http://localhost:5000"
echo "=================================================="

@ECHO OFF
cd /d %~dp0

echo "Syncing uv environment..."
uv sync

echo "Cleaning previous build artifacts..."
rmdir /s /q dist
rmdir /s /q build

echo "Run Cython build"
uv run python build_cython.py

echo "Run PyInstaller build"
uv run python -m PyInstaller app.spec -y


echo "Build complete"

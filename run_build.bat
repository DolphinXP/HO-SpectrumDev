@ECHO OFF

echo "Cleaning previous build artifacts..."
rmdir /s /q dist
rmdir /s /q build

echo "Run Cython build"
python build_cython.py 

echo "Run PyInstaller build"
python -m PyInstaller app.spec -y 


echo "Build complete"
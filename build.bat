@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  BLE Explorer - exe build
echo ============================================

REM ---- check venv ----
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Create it first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)

REM ---- ensure pyinstaller ----
.venv\Scripts\python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Installing pyinstaller...
    .venv\Scripts\pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] pyinstaller install failed
        exit /b 1
    )
)

REM ---- run tests ----
echo.
echo [1/2] Running tests...
.venv\Scripts\python -m pytest -q
if errorlevel 1 (
    echo [ERROR] Tests failed - build aborted
    exit /b 1
)

REM ---- build ----
echo.
echo [2/2] Building exe...
.venv\Scripts\pyinstaller --noconfirm ble_explorer.spec
if errorlevel 1 (
    echo [ERROR] Build failed
    exit /b 1
)

echo.
echo ============================================
echo  Done: see dist\ for BLE_Explorer_v*.exe
echo ============================================
endlocal

@echo off
setlocal
cd /d "%~dp0"
echo ======================================================
echo ROLLOVER - Standalone Windows Build
echo Bundled market data; end users do not upload files.
echo ======================================================
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found. Install Python 3.11 or newer on this build computer.
  pause
  exit /b 1
)
if not exist "data\Gsec daily price data.xlsx" (
  echo ERROR: Missing bundled G-Sec data: data\Gsec daily price data.xlsx
  pause
  exit /b 1
)
if not exist "data\Daily_Repo.xlsx" (
  echo ERROR: Missing bundled repo data: data\Daily_Repo.xlsx
  pause
  exit /b 1
)
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements_dashboard.txt "pyinstaller>=6.0"
if errorlevel 1 goto :failed
python -m PyInstaller --noconfirm rollover_windows.spec
if errorlevel 1 goto :failed
echo.
echo BUILD COMPLETE. Open dist\ROLLOVER\ROLLOVER.exe
echo Copy the entire dist\ROLLOVER folder to other computers.
pause
exit /b 0
:failed
echo.
echo BUILD FAILED. Copy the full error shown above and share it for troubleshooting.
pause
exit /b 1

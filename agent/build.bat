@echo off
setlocal
echo Building GameTracker Agent...
echo.

cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  where python3 >nul 2>nul
  if %errorlevel%==0 set "PYTHON_CMD=python3"
)

if not defined PYTHON_CMD (
  for /f "delims=" %%P in ('dir /b /ad "%LocalAppData%\Programs\Python\Python*" 2^>nul') do (
    if exist "%LocalAppData%\Programs\Python\%%P\python.exe" (
      set "PYTHON_CMD=%LocalAppData%\Programs\Python\%%P\python.exe"
      goto :python_found
    )
  )
)

if not defined PYTHON_CMD (
  for /f "delims=" %%P in ('dir /b /ad "%ProgramFiles%\Python*" 2^>nul') do (
    if exist "%ProgramFiles%\%%P\python.exe" (
      set "PYTHON_CMD=%ProgramFiles%\%%P\python.exe"
      goto :python_found
    )
  )
)

if not defined PYTHON_CMD (
  for /f "delims=" %%P in ('dir /b /ad "%ProgramFiles(x86)%\Python*" 2^>nul') do (
    if exist "%ProgramFiles(x86)%\%%P\python.exe" (
      set "PYTHON_CMD=%ProgramFiles(x86)%\%%P\python.exe"
      goto :python_found
    )
  )
)

:python_found
if not defined PYTHON_CMD (
  echo Python not found. Install Python 3.8+ and add it to PATH.
  echo Tip: typical path is %%LocalAppData%%\Programs\Python\Python311\python.exe
  exit /b 1
)

REM Create venv if missing
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  call %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    exit /b 1
  )
)

REM Install dependencies in venv
echo Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo Failed to upgrade pip/setuptools/wheel.
  exit /b 1
)
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  exit /b 1
)

REM Ensure setuptools/pkg_resources is available for PyInstaller on Python 3.12
call .venv\Scripts\python.exe -c "import pkg_resources" >nul 2>nul
if errorlevel 1 (
  echo Restoring setuptools for pkg_resources...
  call .venv\Scripts\python.exe -m pip install --upgrade "setuptools>=70,<81"
  if errorlevel 1 (
    echo Failed to install setuptools.
    exit /b 1
  )
  call .venv\Scripts\python.exe -c "import pkg_resources" >nul 2>nul
  if errorlevel 1 (
    echo pkg_resources is still missing after setuptools install.
    exit /b 1
  )
)

REM Build with PyInstaller from venv
echo Building executable...
call .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --noconsole --name GameTrackerAgent agent.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Build complete! Executable is in dist\GameTrackerAgent.exe
pause

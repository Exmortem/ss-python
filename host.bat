@echo off
REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running as administrator
) else (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM Update source code from git
if exist .git (
    git pull
) else (
    echo No git repository found.
)
REM Install/update Python dependencies
pip install -r requirements.txt
REM Launch the host
python host.py 
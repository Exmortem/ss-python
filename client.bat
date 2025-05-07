@echo off
REM Update source code from git
if exist .git (
    git pull
) else (
    echo No git repository found.
)
REM Install/update Python dependencies
pip install -r requirements.txt
REM Launch the client
python client.py 
# Check if running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    Start-Process powershell.exe "-File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "Running as administrator" -ForegroundColor Green

# Update source code from git
if (Test-Path .git) {
    Write-Host "Updating from git..." -ForegroundColor Cyan
    git pull
} else {
    Write-Host "No git repository found." -ForegroundColor Yellow
}

# Install/update Python dependencies
Write-Host "Installing/updating Python dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt

# Launch the host
Write-Host "Starting host application..." -ForegroundColor Green
python host.py 
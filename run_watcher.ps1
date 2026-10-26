# Oracle Free-Tier Hunter - PowerShell Launcher
[CmdletBinding()]
param (
    [string]$Config = "config.yaml",
    [switch]$Once,
    [string]$Mode,
    [switch]$Check
)

Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "         ORACLE FREE-TIER HUNTER - WINDOWS LAUNCHER (POWERSHELL)       " -ForegroundColor Cyan
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

# Verify Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python is not installed or not in PATH. Please install Python 3.10+."
    exit 1
}

# Ensure config.yaml exists
if (-not (Test-Path $Config)) {
    if (Test-Path "config.example.yaml") {
        Write-Host "[INFO] Copying config.example.yaml to $Config..." -ForegroundColor Yellow
        Copy-Item "config.example.yaml" -Destination $Config
    }
}

# Construct arguments
$argsList = @("-c", $Config)
if ($Once) { $argsList += "--once" }
if ($Check) { $argsList += "--check" }
if ($Mode) { $argsList += @("--mode", $Mode) }

Write-Host "[INFO] Launching Free-Tier Hunter with arguments: $argsList" -ForegroundColor Green
& python main.py @argsList

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
$logFile = Join-Path $logDir "scheduled_git_pull.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

function Write-Log {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

try {
    Set-Location $repoRoot
    Write-Log "START pull in $repoRoot"

    $statusBefore = git status --porcelain 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed: $statusBefore"
    }

    $pullOutput = git pull --ff-only 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "git pull failed: $pullOutput"
    }

    Write-Log "OK: $($pullOutput.Trim())"
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}

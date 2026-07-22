$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if ($value) {
                Set-Item -Path "Env:$name" -Value $value
            }
        }
    }
}

# n8n-mcp expects N8N_API_URL, while this repo historically uses N8N_URL.
if (-not $env:N8N_API_URL -and $env:N8N_URL) {
    $env:N8N_API_URL = $env:N8N_URL
}

$env:MCP_MODE = "stdio"
$env:LOG_LEVEL = "error"
$env:DISABLE_CONSOLE_OUTPUT = "true"

$npx = Join-Path $env:ProgramFiles "nodejs\npx.cmd"
if (-not (Test-Path $npx)) {
    throw "npx not found. Install Node.js LTS and restart Cursor."
}

& $npx -y n8n-mcp

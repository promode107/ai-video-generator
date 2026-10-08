# run.ps1
# Lists all scripts in the scripts/ folder, lets you pick one, and
# sends it to the Azure Function to generate a video.
#
# Usage (from project root, with .venv active and func start running):
#   .\run.ps1
#
# To run in preview mode (check scene conversion without generating video):
#   .\run.ps1 -Preview

param(
    [switch]$Preview
)

$FunctionUrl = "http://localhost:7071/api/GenerateVideo"
$ScriptsDir  = Join-Path $PSScriptRoot "scripts"

# ── List available scripts ──────────────────────────────────────────────────
$files = Get-ChildItem -Path $ScriptsDir -Filter "*.txt" | Sort-Object Name

if ($files.Count -eq 0) {
    Write-Host "No script files found in $ScriptsDir" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  HelloAlfred · Video Generator" -ForegroundColor Cyan
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Available scripts:" -ForegroundColor White
Write-Host ""

for ($i = 0; $i -lt $files.Count; $i++) {
    # Strip leading number and underscores from filename for display
    $display = $files[$i].BaseName -replace '^\d+_', '' -replace '_', ' '
    $display = (Get-Culture).TextInfo.ToTitleCase($display.ToLower())
    Write-Host ("  [{0}] {1}" -f ($i + 1), $display) -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  [0] Cancel" -ForegroundColor DarkGray
Write-Host ""

# ── Get user choice ─────────────────────────────────────────────────────────
$choice = Read-Host "  Enter number"
$choice = $choice.Trim()

if ($choice -eq "0" -or $choice -eq "") {
    Write-Host "  Cancelled." -ForegroundColor DarkGray
    exit 0
}

$idx = [int]$choice - 1
if ($idx -lt 0 -or $idx -ge $files.Count) {
    Write-Host "  Invalid selection." -ForegroundColor Red
    exit 1
}

$selectedFile = $files[$idx]
$display = $selectedFile.BaseName -replace '^\d+_', '' -replace '_', ' '
$display = (Get-Culture).TextInfo.ToTitleCase($display.ToLower())

Write-Host ""
Write-Host ("  Selected: {0}" -f $display) -ForegroundColor Cyan
Write-Host ("  File:     {0}" -f $selectedFile.Name) -ForegroundColor DarkGray

# ── Read file using .NET (avoids PowerShell ETS decoration that breaks JSON) ─
$scriptText = [System.IO.File]::ReadAllText($selectedFile.FullName)

# ── Build request body ───────────────────────────────────────────────────────
$bodyObj = @{ script = $scriptText }
if ($Preview) {
    $bodyObj["preview_only"] = $true
    Write-Host "  Mode:     Preview only (no video will be generated)" -ForegroundColor DarkGray
} else {
    Write-Host "  Mode:     Full render" -ForegroundColor DarkGray
}

$body = $bodyObj | ConvertTo-Json -Depth 2

Write-Host ""

if ($Preview) {
    Write-Host "  Sending to pipeline (preview)..." -ForegroundColor White
} else {
    Write-Host "  Sending to pipeline. This will take 15-25 minutes." -ForegroundColor White
    Write-Host "  Watch the func start terminal for per-scene progress." -ForegroundColor DarkGray
}

Write-Host ""

# ── POST to Azure Function ───────────────────────────────────────────────────
try {
    $response = Invoke-RestMethod `
        -Uri $FunctionUrl `
        -Method Post `
        -Body $body `
        -ContentType "application/json" `
        -TimeoutSec 2400  # 40 minutes

    Write-Host "  Done!" -ForegroundColor Green
    Write-Host ""

    if ($Preview) {
        Write-Host "  Scene structure preview:" -ForegroundColor Cyan
        $response.scenes | ForEach-Object {
            Write-Host ("  Scene {0}: {1}" -f $_.scene, $_.visual.Substring(0, [Math]::Min(80, $_.visual.Length))) -ForegroundColor White
        }
    } else {
        Write-Host "  Video saved to:" -ForegroundColor Cyan
        Write-Host ("  {0}" -f $response.local_path) -ForegroundColor White
        if ($response.converted_script_path) {
            Write-Host ""
            Write-Host "  Scene JSON saved to:" -ForegroundColor DarkGray
            Write-Host ("  {0}" -f $response.converted_script_path) -ForegroundColor DarkGray
        }
    }

} catch {
    Write-Host "  Error calling function:" -ForegroundColor Red
    try {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host ($reader.ReadToEnd()) -ForegroundColor Red
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}

Write-Host ""

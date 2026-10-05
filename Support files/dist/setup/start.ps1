# Starts LLM OS Setup (llmos-setup.py, next to this file) with Python 3.8 or newer: one already on this PC, or
# else a private copy of the official Windows "embeddable" Python from python.org, fetched once (about 11 MB)
# into this user's local app data and used only after its SHA-256 matches the published one. Nothing is
# installed and no administrator rights are needed. "Start Here (Windows).bat" calls this.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'      # Invoke-WebRequest is very slow while it draws a progress bar
try { $Host.UI.RawUI.WindowTitle = 'LLM OS Setup' } catch {}
$cache = Join-Path $env:LOCALAPPDATA 'LLM OS Setup'
$private = Join-Path $cache 'python\python.exe'

function Test-Python([string]$exe, [string[]]$pre) {
    try {
        & $exe @pre -c 'import sys; sys.exit(sys.version_info < (3, 8))' *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

$py = $null; $pre = @()
if ((Test-Path -LiteralPath $private) -and (Test-Python $private @())) { $py = $private }
elseif ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Python 'py' @('-3'))) { $py = 'py'; $pre = @('-3') }
elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Python 'python' @())) { $py = 'python' }

if (-not $py) {
    $arm = ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') -or ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64')
    $flavor = if ($arm) { 'arm64' } else { 'amd64' }
    $sums = @{ amd64 = '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'
               arm64 = '790d097697a2020477549a6764d89d22194c88d6e42caebcb2db63791e004c94' }
    $url = "https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-$flavor.zip"
    Write-Host ''
    Write-Host '  Getting Python for this setup (one time, about 11 MB)...'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        $zip = Join-Path $cache 'python.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash -ne $sums[$flavor]) {
            Remove-Item -LiteralPath $zip -Force
            throw "the download didn't match its published checksum, so it wasn't used"
        }
        $dir = Join-Path $cache 'python'
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $dir -Force
        Remove-Item -LiteralPath $zip -Force
        if (Test-Python $private @()) { $py = $private }
    } catch {
        Write-Host "  Couldn't get Python: $($_.Exception.Message)"
    }
}

if (-not $py) {
    Write-Host ''
    Write-Host '  Setup needs Python 3 and could not download it just now.'
    Write-Host '  Check the internet connection and open Start Here again,'
    Write-Host '  or install Python from https://www.python.org/downloads/ first.'
    exit 1
}

& $py @pre (Join-Path $PSScriptRoot 'llmos-setup.py')
exit $LASTEXITCODE

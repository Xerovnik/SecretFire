# SecretFire Network Diagnostics — Windows
# Save this file and run in PowerShell:
#   .\SecretFire-Diagnose.ps1
#
# If PowerShell says scripts are disabled, run this first:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
# This script is SecretFire-specific. It does NOT test clearnet access
# through the SOCKS proxy — that is intentionally blocked (OnionTrafficOnly).
# Checking clearnet would always show FAIL on a healthy node and mislead you.

$ErrorActionPreference = "SilentlyContinue"
$DataDir   = "$env:USERPROFILE\.secretfire"
$TorData   = "$DataDir\tor_data"
$HsDir     = "$DataDir\hidden_service"
$Torrc     = "$TorData\torrc"
$TorLog    = "$TorData\tor.log"
$DbPath    = "$DataDir\node.db"
$FlaskPort = 7474
$Pass = 0
$Fail = 0

function Write-Ok   { param($msg, $note) Write-Host ("  [PASS] " + $msg) -ForegroundColor Green; if ($note) { Write-Host ("         > " + $note) -ForegroundColor Cyan } }
function Write-Fail { param($msg, $note) Write-Host ("  [FAIL] " + $msg) -ForegroundColor Red;   if ($note) { Write-Host ("         > " + $note) -ForegroundColor Yellow } }
function Write-Info { param($msg)        Write-Host ("  [INFO] " + $msg) -ForegroundColor Cyan }

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "      SecretFire Network Diagnostics              " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ("  Run at: " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss") + " UTC")
Write-Host ""

# ── 1. Data directory ──────────────────────────────────────────────────
Write-Host "[ 1/9 ] Data directory"
if (Test-Path $DataDir) {
    Write-Ok "~\.secretfire exists" $DataDir
    $Pass++
} else {
    Write-Fail "~\.secretfire does not exist" "SecretFire has never been run here, or uses a different path."
    $Fail++
}

# ── 2. Tor process ─────────────────────────────────────────────────────
Write-Host "[ 2/9 ] Tor process"
$TorProc = Get-Process -Name "tor" -ErrorAction SilentlyContinue
if ($TorProc) {
    Write-Ok "Tor process is running (PID $($TorProc.Id))"
    $Pass++
} else {
    Write-Fail "Tor process is NOT running" "Start SecretFire and wait 30 s, then run this script again."
    $Fail++
}

# ── 3. Bootstrap ───────────────────────────────────────────────────────
Write-Host "[ 3/9 ] Tor bootstrap status"
$BootPct = 0
if (Test-Path $TorLog) {
    $lines = Get-Content $TorLog -ErrorAction SilentlyContinue
    if ($lines) {
        $matches = $lines | Select-String -Pattern "Bootstrapped (\d+)%" -AllMatches
        foreach ($m in $matches) {
            $pct = [int]$m.Matches[0].Groups[1].Value
            if ($pct -gt $BootPct) { $BootPct = $pct }
        }
    }
}
if ($BootPct -eq 100) {
    Write-Ok "Tor fully bootstrapped (100%)"
    $Pass++
} elseif ($BootPct -gt 0) {
    Write-Fail "Tor bootstrap in progress ($BootPct%)" "Wait 30-90 s and run again. If stuck, enable bridges."
    $Fail++
} else {
    Write-Fail "No bootstrap progress (0%)" "Tor may be blocked by your ISP or firewall. Consider enabling bridges."
    $Fail++
}

# ── 4. Hidden service ──────────────────────────────────────────────────
Write-Host "[ 4/9 ] Hidden service"
$Onion = ""
$HostnameFile = "$HsDir\hostname"
if (Test-Path $HostnameFile) {
    $Onion = (Get-Content $HostnameFile -Raw).Trim()
}
if ($Onion) {
    Write-Ok "Hidden service address exists" $Onion
    $Pass++
} else {
    Write-Fail "Hidden service hostname missing" "Tor may not have finished publishing. Wait 60 s and try again."
    $Fail++
}

# ── 5. SOCKS port ──────────────────────────────────────────────────────
Write-Host "[ 5/9 ] SOCKS proxy port"
$SocksPort = 9150
if (Test-Path $Torrc) {
    $torrcContent = Get-Content $Torrc -Raw -ErrorAction SilentlyContinue
    if ($torrcContent -match "SocksPort\s+(\d+)") {
        $SocksPort = [int]$Matches[1]
    }
}
$SocksConn = Get-NetTCPConnection -LocalPort $SocksPort -State Listen -ErrorAction SilentlyContinue
if ($SocksConn) {
    Write-Ok "SOCKS proxy is listening on port $SocksPort"
    $Pass++
} else {
    Write-Fail "SOCKS proxy NOT listening on port $SocksPort" "Tor may have failed to start. Check SecretFire's Console tab."
    $Fail++
}

# ── 6. Clearnet blocked (expected) ────────────────────────────────────
Write-Host "[ 6/9 ] Clearnet traffic blocked (OnionTrafficOnly — expected)"
if ($SocksConn) {
    $ClearBlocked = $false
    try {
        $r = Invoke-WebRequest -Uri "http://1.1.1.1" `
            -Proxy "socks5://127.0.0.1:$SocksPort" `
            -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        # If we got here without exception, clearnet is reachable (unexpected)
    } catch {
        $ClearBlocked = $true
    }
    if ($ClearBlocked) {
        Write-Ok "Clearnet is blocked via SOCKS (correct — OnionTrafficOnly is active)"
        $Pass++
    } else {
        Write-Fail "Clearnet appears reachable via SOCKS" "OnionTrafficOnly may not be configured. Check torrc."
        $Fail++
    }
} else {
    Write-Info "Skipped clearnet block test (SOCKS not listening)"
}

# ── 7. Self-onion reachability ─────────────────────────────────────────
Write-Host "[ 7/9 ] Self-onion reachability (via SOCKS — may take up to 25 s)"
if ($Onion -and $SocksConn -and $BootPct -eq 100) {
    try {
        $r = Invoke-WebRequest `
            -Uri "http://${Onion}:${FlaskPort}/api/status" `
            -Proxy "socks5://127.0.0.1:$SocksPort" `
            -TimeoutSec 25 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Write-Ok "Your node is reachable via its .onion address" $Onion
            $Pass++
        } else {
            Write-Fail "Self-onion test returned HTTP $($r.StatusCode)" "Unexpected response from your own node."
            $Fail++
        }
    } catch {
        $ErrMsg = $_.Exception.Message
        Write-Fail "Self-onion reachability test failed" "Descriptor may not have propagated yet. Wait 60-120 s after first start and try again. ($ErrMsg)"
        $Fail++
    }
} else {
    Write-Info "Skipped — requires Tor at 100%, SOCKS listening, and a hidden service address."
}

# ── 8. System clock ────────────────────────────────────────────────────
Write-Host "[ 8/9 ] System clock"
$UtcTime = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss") + " UTC"
Write-Ok "System clock reads: $UtcTime" "Tor requires accurate time (within ~30 s). Compare with time.is if peers cannot connect."
$Pass++

# ── 9. Database file ───────────────────────────────────────────────────
Write-Host "[ 9/9 ] Local database"
if ((Test-Path $DbPath) -and (Get-Item $DbPath).Length -gt 0) {
    $DbSize = [math]::Round((Get-Item $DbPath).Length / 1KB, 1)
    Write-Ok "Database file exists (${DbSize} KB)" $DbPath
    $Pass++
} else {
    Write-Fail "Database file missing or empty" "$DbPath — SecretFire may not have started correctly."
    $Fail++
}

# ── Summary ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
$Total = $Pass + $Fail
Write-Host "  Result: $Pass passed, $Fail failed out of $Total checks" -ForegroundColor White
Write-Host ""
if ($Fail -eq 0) {
    Write-Host "  Your node looks healthy." -ForegroundColor Green
} else {
    Write-Host "  Recommended steps:" -ForegroundColor Yellow
    Write-Host "  1. Fully restart SecretFire (close from system tray, reopen)"
    Write-Host "  2. Wait 60-120 s after restart for the hidden service to publish"
    Write-Host "  3. If bootstrap is stuck, try a different network or enable bridges"
    Write-Host "  4. Verify your system clock is correct at time.is"
    Write-Host "  5. Copy and share this output with whoever is helping you troubleshoot"
}
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

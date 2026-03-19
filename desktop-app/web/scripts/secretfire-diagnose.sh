#!/usr/bin/env bash
# SecretFire Network Diagnostics — Linux / macOS
# Run:  chmod +x secretfire-diagnose.sh && ./secretfire-diagnose.sh
#
# This script is SecretFire-specific. It does NOT test clearnet access
# through the SOCKS proxy — that is intentionally blocked (OnionTrafficOnly).
# Checking clearnet would always show ✗ on a healthy node and mislead you.

CYAN="\033[1;36m"; GREEN="\033[1;32m"; RED="\033[1;31m"; YELLOW="\033[1;33m"; NC="\033[0m"
ok()   { echo -e "  ${GREEN}✓${NC} $1"; [ -n "$2" ] && echo -e "    ${CYAN}→ $2${NC}"; }
fail() { echo -e "  ${RED}✗${NC} $1"; [ -n "$2" ] && echo -e "    ${YELLOW}→ $2${NC}"; }
info() { echo -e "  ${CYAN}i${NC} $1"; }

DATA_DIR="$HOME/.secretfire"
TOR_DATA="$DATA_DIR/tor_data"
HS_DIR="$DATA_DIR/hidden_service"
TORRC="$TOR_DATA/torrc"
TOR_LOG="$TOR_DATA/tor.log"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       SecretFire Network Diagnostics             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo -e "  Run at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

PASS=0; FAIL=0

# ── 1. Data directory ──────────────────────────────────────────────────
echo "[ 1/9 ] Data directory"
if [ -d "$DATA_DIR" ]; then
    ok "~/.secretfire exists" "$DATA_DIR"
    ((PASS++))
else
    fail "~/.secretfire does not exist" "SecretFire has never been run on this machine, or it uses a different path."
    ((FAIL++))
fi

# ── 2. Tor process ─────────────────────────────────────────────────────
echo "[ 2/9 ] Tor process"
if pgrep -f "tor" > /dev/null 2>&1; then
    ok "Tor process is running"
    ((PASS++))
else
    fail "Tor process is NOT running" "Start SecretFire and wait 30 s, then run this script again."
    ((FAIL++))
fi

# ── 3. Bootstrap ───────────────────────────────────────────────────────
# SecretFire logs Tor to stdout only — there is no tor.log on disk.
# SecretFire only opens the SOCKS port after Tor reaches 100% bootstrap,
# so SOCKS listening is the reliable proxy for "bootstrapped successfully".
echo "[ 3/9 ] Tor bootstrap status"
SOCKS_TEST_PORT=9150
if [ -f "$TORRC" ]; then
    FOUND_PORT=$(grep -oE "SocksPort [0-9]+" "$TORRC" 2>/dev/null | grep -oE "[0-9]+" | head -1)
    [ -n "$FOUND_PORT" ] && SOCKS_TEST_PORT=$FOUND_PORT
fi
BOOT_SOCKS=0
if command -v ss &>/dev/null; then
    BOOT_SOCKS=$(ss -ltn 2>/dev/null | grep -c ":${SOCKS_TEST_PORT} ")
elif command -v netstat &>/dev/null; then
    BOOT_SOCKS=$(netstat -ltn 2>/dev/null | grep -c ":${SOCKS_TEST_PORT} ")
fi
BOOTSTRAPPED=0
if [ "$BOOT_SOCKS" -gt 0 ]; then
    ok "Tor bootstrapped (100%) — SOCKS port is open"
    BOOTSTRAPPED=1
    ((PASS++))
else
    fail "Tor not yet bootstrapped" "SOCKS port is not open. Wait 60–90 s after starting SecretFire. If stuck, try a different network or enable bridges."
    ((FAIL++))
fi

# ── 4. Hidden service ──────────────────────────────────────────────────
echo "[ 4/9 ] Hidden service"
ONION=""
if [ -f "$HS_DIR/hostname" ] && [ -s "$HS_DIR/hostname" ]; then
    ONION=$(cat "$HS_DIR/hostname" | tr -d '[:space:]')
    ok "Hidden service address exists" "$ONION"
    ((PASS++))
else
    fail "Hidden service hostname missing" "Tor may not have finished publishing the hidden service. Wait 60 s."
    ((FAIL++))
fi

# ── 5. SOCKS port ──────────────────────────────────────────────────────
echo "[ 5/9 ] SOCKS proxy port"
SOCKS_PORT=9150
if [ -f "$TORRC" ]; then
    FOUND_PORT=$(grep -oE "SocksPort [0-9]+" "$TORRC" 2>/dev/null | grep -oE "[0-9]+" | head -1)
    [ -n "$FOUND_PORT" ] && SOCKS_PORT=$FOUND_PORT
fi
if command -v ss &>/dev/null; then
    SOCKS_OK=$(ss -ltn 2>/dev/null | grep -c ":${SOCKS_PORT} ")
elif command -v netstat &>/dev/null; then
    SOCKS_OK=$(netstat -ltn 2>/dev/null | grep -c ":${SOCKS_PORT} ")
else
    SOCKS_OK=0
fi
if [ "$SOCKS_OK" -gt 0 ]; then
    ok "SOCKS proxy is listening on port ${SOCKS_PORT}"
    ((PASS++))
else
    fail "SOCKS proxy NOT listening on port ${SOCKS_PORT}" "Tor may have failed to start. Check SecretFire's Console tab."
    ((FAIL++))
fi

# ── 6. Clearnet blocked (expected) ────────────────────────────────────
echo "[ 6/9 ] Clearnet traffic blocked (OnionTrafficOnly — expected)"
if command -v curl &>/dev/null && [ "$SOCKS_OK" -gt 0 ]; then
    CLEAR=$(curl --socks5-hostname "127.0.0.1:${SOCKS_PORT}" -s --max-time 5 \
            "http://1.1.1.1" -o /dev/null -w "%{http_code}" 2>/dev/null || echo "blocked")
    if [ "$CLEAR" = "blocked" ] || [ "$CLEAR" = "000" ] || [ -z "$CLEAR" ]; then
        ok "Clearnet is blocked via SOCKS (correct — OnionTrafficOnly is active)"
        ((PASS++))
    else
        fail "Clearnet appears reachable via SOCKS" "OnionTrafficOnly may not be configured. Check torrc."
        ((FAIL++))
    fi
else
    info "Skipped clearnet block test (curl not available or SOCKS not listening)"
fi

# ── 7. Self-onion reachability ─────────────────────────────────────────
echo "[ 7/9 ] Self-onion reachability (via SOCKS — may take up to 20 s)"
if [ -n "$ONION" ] && [ "$SOCKS_OK" -gt 0 ] && [ "$BOOTSTRAPPED" -eq 1 ] && command -v curl &>/dev/null; then
    # Read the Flask port from config if possible, default 7474
    FLASK_PORT=7474
    SF_RESPONSE=$(curl --socks5-hostname "127.0.0.1:${SOCKS_PORT}" -s \
        --max-time 25 "http://${ONION}:${FLASK_PORT}/api/status" \
        -o /dev/null -w "%{http_code}" 2>/dev/null)
    if [ "$SF_RESPONSE" = "200" ]; then
        ok "Your node is reachable via its .onion address" "$ONION"
        ((PASS++))
    else
        fail "Self-onion reachability test failed (HTTP ${SF_RESPONSE:-timeout})" \
             "Descriptor may not have propagated yet. Wait 60–120 s after first start and try again."
        ((FAIL++))
    fi
else
    info "Skipped — requires Tor bootstrapped at 100%, SOCKS listening, and a hidden service address."
fi

# ── 8. System clock ────────────────────────────────────────────────────
echo "[ 8/9 ] System clock"
UTC_TIME=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
ok "System clock reads: ${UTC_TIME}" "Tor requires accurate time (within ~30 s). Compare with time.is if peers can't connect."
((PASS++))

# ── 9. Database file ───────────────────────────────────────────────────
echo "[ 9/9 ] Local database"
DB_PATH="$DATA_DIR/node.db"
if [ -f "$DB_PATH" ] && [ -s "$DB_PATH" ]; then
    DB_SIZE=$(du -h "$DB_PATH" 2>/dev/null | cut -f1)
    ok "Database file exists (${DB_SIZE})" "$DB_PATH"
    ((PASS++))
else
    fail "Database file missing or empty" "$DB_PATH — SecretFire may not have started correctly."
    ((FAIL++))
fi

# ── Summary ────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}──────────────────────────────────────────────────${NC}"
TOTAL=$((PASS + FAIL))
echo -e "  Result: ${GREEN}${PASS}${NC} passed, ${RED}${FAIL}${NC} failed out of ${TOTAL} checks"
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}✓ Your node looks healthy.${NC}"
else
    echo -e "  ${YELLOW}Recommended steps:${NC}"
    echo "  1. Fully restart SecretFire (close completely and reopen)"
    echo "  2. Wait 60–120 s after restart for hidden service to publish"
    echo "  3. If bootstrap is stuck, try a network with fewer restrictions"
    echo "  4. Verify your system clock is correct (compare with time.is)"
    echo "  5. Share this output with whoever is helping you troubleshoot"
fi
echo -e "${CYAN}──────────────────────────────────────────────────${NC}"
echo ""

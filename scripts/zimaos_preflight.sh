#!/bin/sh
# Read-only ZimaOS prerequisite check. Run AS the dedicated non-root rootless owner.
# Never run unreviewed system installers or print secrets.
set -u
fail=0
pass() { printf 'PASS  %s\n' "$1"; }
error() { printf 'FAIL  %s\n' "$1"; fail=$((fail+1)); }
info() { printf 'INFO  %s\n' "$1"; }
ident="$(id -u 2>/dev/null || printf unknown)"
user="$(id -un 2>/dev/null || printf unknown)"
info "date=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || printf unknown)"
info "user=$user uid=$ident arch=$(uname -m) kernel=$(uname -r)"
if [ -r /etc/os-release ]; then
  info "os=$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | head -1 | tr -d '\"')"
fi
[ "$ident" != "0" ] && pass 'Not running as root' || error 'Run as dedicated non-root user'
case " $(id -nG 2>/dev/null) " in
  *' docker '*) error 'User belongs to the administrative docker group';;
  *) pass 'Not in docker group';;
esac
SOCK="${WEBHOST_ROOTLESS_SOCKET:-/run/user/$ident/docker.sock}"
DATA="${WEBHOST_DATA_DIR:-/DATA/AppData/MrStore_webhost/data}"
if [ -S "$SOCK" ]; then pass "Rootless socket exists at $SOCK"; else error "No socket at $SOCK"; fi
if command -v docker >/dev/null 2>&1; then
  pass 'Docker client available'
  OPTIONS="$(docker --host "unix://$SOCK" info --format '{{json .SecurityOptions}}' 2>/dev/null || printf '')"
  case "$OPTIONS" in
    *'name=rootless'*) pass 'Docker daemon reports rootless mode';;
    *) error 'Docker daemon is not accessible or does not report rootless';;
  esac
else error 'Docker client missing'; fi
if [ -d "$DATA" ]; then
  if [ -r "$DATA" ] && [ -w "$DATA" ] && [ -x "$DATA" ]; then
    pass "Data directory accessible by rootless user: $DATA"
  else error "Data directory not accessible: $DATA"; fi
else error "Data directory missing: $DATA"; fi
if command -v ss >/dev/null 2>&1; then
  info 'Listening ports 8484/9101–9104 (inspect manually for conflicts):'
  ss -ltn 2>/dev/null | grep -E ':(8484|910[1-4])[[:space:]]' || true
else
  info 'ss is unavailable; port conflict check must be done manually'
fi
if [ "$fail" -eq 0 ]; then
  printf '\nPRE-FLIGHT: PASS (does NOT validate application deployments or reboot behavior)\n'
  exit 0
fi
printf '\nPRE-FLIGHT: FAIL (%s checks). Do not deploy on the NAS yet.\n' "$fail"
exit 1
#!/bin/sh
# Build and flash FP10 Lights (run on the machine the board is plugged into, e.g. moo).
#   ./build.sh          build + flash over USB
#   ./build.sh ota      build + flash over Wi-Fi (put the board in update mode first)
# Extra args go to arduino-cli compile (e.g. --clean).
# Optional OTA password: one line in ~/.config/fp10-lights/ota_pass, matching "set otapass" on the board.
cd "$(dirname "$0")" || exit 1
CLI=${ARDUINO_CLI:-arduino-cli}
command -v "$CLI" >/dev/null || CLI=~/.local/bin/arduino-cli
PORT=${PORT:-/dev/ttyACM0}
HOST=fp10-lights.local

MODE=usb
[ "$1" = ota ] && { MODE=ota; shift; }

# USB_PRODUCT names the board "FP10 Lights"; it has to be a build flag because USB starts before setup()
"$CLI" compile --profile fp10 --output-dir build \
  --build-property "compiler.cpp.extra_flags='-DUSB_PRODUCT=\"FP10 Lights\"'" \
  "$@" . || exit 1

if [ $MODE = usb ]; then
  exec "$CLI" upload --profile fp10 -p "$PORT" .
fi

# The board takes a few seconds to join Wi-Fi, and a cached name answers before it does: wait for a ping
for i in $(seq 30); do
  IP=$(getent hosts $HOST | awk '{print $1; exit}')
  [ -n "$IP" ] && ping -c 1 -W 1 "$IP" >/dev/null 2>&1 && break
  IP=
  sleep 1
done
[ -n "$IP" ] || { echo "Can't reach $HOST - is the board in update mode (purple LED)?"; exit 1; }
echo "Uploading to $HOST ($IP)"
# espota directly: arduino-cli's network upload first looks the board up over mDNS and fails ("port not found")
# when the board hasn't announced itself yet, which was most first tries (2026-11-01)
ESPOTA=$(ls ~/.arduino15/packages/esp32/hardware/esp32/*/tools/espota.py 2>/dev/null | tail -1)
[ -n "$ESPOTA" ] || { echo "espota.py not found - run ./build.sh once over USB to install the core"; exit 1; }
PASS_FILE=~/.config/fp10-lights/ota_pass
set -- -i "$IP" -p 3232 -f build/fp10_lights.ino.bin
[ -f "$PASS_FILE" ] && set -- "$@" -a "$(cat "$PASS_FILE")"
exec python3 "$ESPOTA" "$@"

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
"$CLI" compile --profile fp10 \
  --build-property "compiler.cpp.extra_flags='-DUSB_PRODUCT=\"FP10 Lights\"'" \
  "$@" . || exit 1

if [ $MODE = usb ]; then
  exec "$CLI" upload --profile fp10 -p "$PORT" .
fi

IP=$(getent hosts $HOST | awk '{print $1; exit}')
[ -n "$IP" ] || { echo "Can't find $HOST - is the board in update mode (purple LED)?"; exit 1; }
echo "Uploading to $HOST ($IP)"
# arduino-cli always asks for the password field, so pass it empty when the board has no otapass
PASS_FILE=~/.config/fp10-lights/ota_pass
PASS=$([ -f "$PASS_FILE" ] && cat "$PASS_FILE")
exec "$CLI" upload --profile fp10 -p "$IP" -l network --upload-field password="$PASS" .

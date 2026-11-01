#!/bin/sh
# Talk to the board through the Push it's plugged into: board_push.py runs there over SSH and sends CCs on
# channel 16 from a port Live can't subscribe to (the MCP server's HiddenOut), which keeps them out of Live's tracks.
#   ./board.sh update [off]       Wi-Fi update mode (CC119), then ./build.sh ota on moo
#   ./board.sh calibrate [off]    calibration mode (CC118): set where C1 and C6 light from the piano
#   ./board.sh restart            restart the board (CC117)
#   ./board.sh restart-test [N]   restart N times, checking the Push sets the board up again each time
cd "$(dirname "$0")" || exit 1
exec ssh -T -o BatchMode=yes -o ConnectTimeout=10 push3 /data/uv/tools/ableton-mcp/bin/python - "$@" < board_push.py

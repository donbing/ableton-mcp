#!/bin/sh
# Talk to the board through the Push it's plugged into: board_push.py runs there over SSH and sends CCs on
# channel 16 from a port Live can't subscribe to (the MCP server's HiddenOut), which keeps them out of Live's tracks.
#   ./board.sh update [off]       Wi-Fi update mode (CC119), then ./build.sh ota on moo
#   ./board.sh calibrate [off]    calibration mode (CC118): set where C1 and C6 light from the piano
#   ./board.sh restart            restart the board (CC117)
#   ./board.sh split [NOTE|off]   left-hand colour below NOTE (CC116; Live's names, C3 = 60 by default)
#   ./board.sh sparks [off]       each played note throws sparks along the strip (CC115)
#   ./board.sh brightness N       strip brightness 1-127, 64 = 50% (CC113), saved
#   ./board.sh layers [N|all]     which lights show for 2 minutes (CC114): 1 play 2 sparks 4 left 8 hints 16 flashes
#   ./board.sh restart-test [N]   restart N times, checking the Push sets the board up again each time
cd "$(dirname "$0")" || exit 1
exec ssh -T -o BatchMode=yes -o ConnectTimeout=10 push3 /data/uv/tools/ableton-mcp/bin/python - "$@" < board_push.py

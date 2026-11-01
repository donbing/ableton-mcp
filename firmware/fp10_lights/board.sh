#!/bin/sh
# Switch the board's modes with a CC on channel 16, sent over SSH from the Push it's plugged into.
# Live holds the raw MIDI port, so this goes through the ALSA sequencer from a port Live can't subscribe to
# (the MCP server's HiddenOut), which keeps the message out of Live's tracks.
#   ./board.sh update [off]      Wi-Fi update mode (CC119), then ./build.sh ota on moo
#   ./board.sh calibrate [off]   calibration mode (CC118): set where C1 and C6 light from the piano
case "$1" in
  update) CC=119 ;;
  calibrate) CC=118 ;;
  *) echo "usage: $0 update|calibrate [off]"; exit 2 ;;
esac
VALUE=127
[ "$2" = off ] && VALUE=0
exec ssh -T -o BatchMode=yes -o ConnectTimeout=10 push3 "/data/uv/tools/ableton-mcp/bin/python -c '
from MCP_Server.push_midi import open_output
out = open_output(\"FP10 Lights MIDI 1\")
if out is None:
    raise SystemExit(\"FP10 Lights is not connected to the Push\")
out.send_message([0xBF, $CC, $VALUE])
out.close_port()
print(\"$1 $( [ $VALUE = 0 ] && echo off || echo on )\")
'"

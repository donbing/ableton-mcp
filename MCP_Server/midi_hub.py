"""MIDI hub on the Push: the instruments plugged into it, over a WebSocket, so the Surface can use them over Wi-Fi.

Every hardware MIDI port on the Push (the FP-10, a USB keyboard, the Push's MIDI in, its pads) is read through
the ALSA sequencer, which gives each reader its own copy: Live keeps playing them as before (measured
2026-11-03: 141 FP-10 notes logged in 30 s while Live played them on an armed track). Our input port can't be
subscribed to, so Live never sees it as a track input or output, and we send through push_midi.HiddenOut for
the same reason. Ports that come and go (a keyboard plugged in later) are followed through ALSA's announcements.

Runs with the MCP server's Python on the Push (it has `websockets`; nothing else outside the standard library):

    /data/uv/tools/ableton-mcp/bin/python -m MCP_Server.midi_hub [--host 0.0.0.0] [--port 8766]

Messages are JSON text. From the hub:

    {"type": "hello", "sources": [name, ...], "outputs": [name, ...]}    on connect, and as "sources" on changes
    {"type": "midi", "src": name, "data": [status, d1, d2]}               a message played on a source

To the hub:

    {"type": "midi", "to": name, "data": [status, d1, d2]}                one of "outputs" (only FP10 Lights)

Names are the ALSA port names, as Live shows them ("Roland Digital Piano MIDI 1"). Only channel messages are
passed on (no sysex, clock or active sensing). From the Push's own pad port only pad notes (36-99) are, since
its buttons and encoders send a stream of CCs there. Starting the hub makes Live rescan its MIDI ports once
(about 1 s after our ports appear): a note held right then may hang in Live.
"""

import argparse
import asyncio
import json

PORT = 8766
OUTPUTS = ("FP10 Lights MIDI 1",)
# hardware ports we don't read: the strip only answers us, Midi Through echoes whatever is sent to it
SKIP = ("FP10 Lights", "Midi Through")
PADS_PORT = "Ableton Push 3 Live Port"
FIRST_PAD, LAST_PAD = 36, 99

# ALSA sequencer constants (alsa/seq.h, alsa/seq_event.h)
OPEN_INPUT, NONBLOCK = 2, 1
CAP_READ, CAP_WRITE, CAP_SUBS_READ, CAP_NO_EXPORT = 1, 2, 1 << 5, 1 << 7
TYPE_MIDI_GENERIC, TYPE_APPLICATION = 1 << 1, 1 << 20
KERNEL_CLIENT = 2
ANNOUNCE = (0, 1)
EV_NOTEON, EV_PITCHBEND = 6, 13  # the channel messages are event types 6-13
EV_CLIENT_START, EV_PORT_CHANGE = 60, 65  # client/port start, exit, change
POLLIN, EAGAIN = 1, 11


def keep(src, data):
    """Whether a message from port `src` is passed on."""
    if not data or not 0x80 <= data[0] <= 0xEF:
        return False
    if PADS_PORT in src:
        return data[0] & 0xE0 == 0x80 and len(data) == 3 and FIRST_PAD <= data[1] <= LAST_PAD
    return True


def parse_request(text, outputs):
    """(output, data) from a client's message, or None when it isn't a valid one for an output we have."""
    try:
        msg = json.loads(text)
    except ValueError:
        return None
    if not isinstance(msg, dict) or msg.get("type") != "midi" or msg.get("to") not in outputs:
        return None
    data = msg.get("data")
    if (not isinstance(data, list) or not 1 <= len(data) <= 3
            or not all(isinstance(b, int) and not isinstance(b, bool) and 0 <= b <= 255 for b in data)
            or not 0x80 <= data[0] <= 0xEF or any(b > 127 for b in data[1:])):
        return None
    return msg["to"], data


class SeqIn:
    """Reads hardware MIDI ports from one ALSA port nobody else can subscribe to."""

    def __init__(self, on_midi, on_change):
        import ctypes
        self.ctypes, self.asound = ctypes, ctypes.CDLL("libasound.so.2")
        self.on_midi, self.on_change = on_midi, on_change
        a = self.asound
        a.snd_seq_port_info_get_name.restype = ctypes.c_char_p
        a.snd_seq_client_info_get_name.restype = ctypes.c_char_p
        a.snd_midi_event_decode.restype = ctypes.c_long
        self.seq, self.coder = ctypes.c_void_p(), ctypes.c_void_p()
        if a.snd_seq_open(ctypes.byref(self.seq), b"default", OPEN_INPUT, NONBLOCK) < 0:
            raise OSError("no ALSA sequencer")
        a.snd_seq_set_client_name(self.seq, b"AbletonMCP hub")
        # WRITE without SUBS_WRITE: we connect sources to it ourselves (ALSA lets a port's owner), nobody else can
        self.port = a.snd_seq_create_simple_port(self.seq, b"AbletonMCP hub", CAP_WRITE | CAP_NO_EXPORT,
                                                 TYPE_MIDI_GENERIC | TYPE_APPLICATION)
        a.snd_midi_event_new(16, ctypes.byref(self.coder))
        a.snd_midi_event_no_status(self.coder, 1)  # every message with its status byte
        self.buf = (ctypes.c_ubyte * 16)()
        self.sources = {}  # (client, port) -> name
        a.snd_seq_connect_from(self.seq, self.port, *ANNOUNCE)

    def fileno(self):
        ctypes = self.ctypes

        class PollFd(ctypes.Structure):
            _fields_ = [("fd", ctypes.c_int), ("events", ctypes.c_short), ("revents", ctypes.c_short)]

        fds = (PollFd * 4)()
        n = self.asound.snd_seq_poll_descriptors(self.seq, fds, 4, POLLIN)
        if n < 1:
            raise OSError("no ALSA sequencer poll descriptor")
        return fds[0].fd

    def hardware(self):
        """{(client, port): name} of every hardware port that can be read."""
        ctypes, a = self.ctypes, self.asound
        cinfo, pinfo = ctypes.c_void_p(), ctypes.c_void_p()
        a.snd_seq_client_info_malloc(ctypes.byref(cinfo))
        a.snd_seq_port_info_malloc(ctypes.byref(pinfo))
        found = {}
        a.snd_seq_client_info_set_client(cinfo, -1)
        while a.snd_seq_query_next_client(self.seq, cinfo) >= 0:
            client = a.snd_seq_client_info_get_client(cinfo)
            if client == 0 or a.snd_seq_client_info_get_type(cinfo) != KERNEL_CLIENT:
                continue
            a.snd_seq_port_info_set_client(pinfo, client)
            a.snd_seq_port_info_set_port(pinfo, -1)
            while a.snd_seq_query_next_port(self.seq, pinfo) >= 0:
                name = a.snd_seq_port_info_get_name(pinfo).decode(errors="replace")
                caps = a.snd_seq_port_info_get_capability(pinfo)
                if caps & (CAP_READ | CAP_SUBS_READ) == CAP_READ | CAP_SUBS_READ and not any(s in name for s in SKIP):
                    found[(client, a.snd_seq_port_info_get_port(pinfo))] = name
        a.snd_seq_port_info_free(pinfo)
        a.snd_seq_client_info_free(cinfo)
        return found

    def rescan(self):
        """Connect to new hardware ports and forget gone ones; True when the list changed."""
        now = self.hardware()
        for addr in now.keys() - self.sources.keys():
            if self.asound.snd_seq_connect_from(self.seq, self.port, *addr) < 0:
                del now[addr]
        changed = now != self.sources
        self.sources = now
        return changed

    def drain(self):
        """Handle every event waiting (called when the sequencer's descriptor is readable)."""
        ctypes, a = self.ctypes, self.asound
        ev = ctypes.c_void_p()
        while True:
            left = a.snd_seq_event_input(self.seq, ctypes.byref(ev))
            if left == -EAGAIN or not ev.value:
                return
            if left < 0:
                continue  # -ENOSPC: the input overran; carry on with what's next
            raw = ctypes.cast(ev, ctypes.POINTER(ctypes.c_ubyte * 16)).contents
            kind, source = raw[0], (raw[12], raw[13])
            if EV_CLIENT_START <= kind <= EV_PORT_CHANGE:
                self.on_change()
            elif EV_NOTEON <= kind <= EV_PITCHBEND and source in self.sources:
                n = a.snd_midi_event_decode(self.coder, self.buf, len(self.buf), ev)
                if n > 0:
                    self.on_midi(self.sources[source], list(self.buf[:n]))


class Hub:
    def __init__(self):
        from MCP_Server.push_midi import HiddenOut
        self.clients = set()
        self.seq = SeqIn(self.played, self.ports_changed)
        self.out = HiddenOut(OUTPUTS[0])  # one sending port, pointed at whichever output a message is for
        self.outputs = {}  # name -> (client, port)
        self.pending = None

    def find_outputs(self):
        self.outputs = {name: dest for name in OUTPUTS if (dest := self.out._find(name))}

    def state(self, kind):
        return json.dumps({"type": kind, "sources": sorted(set(self.seq.sources.values())),
                           "outputs": sorted(self.outputs)})

    def played(self, src, data):
        if keep(src, data) and self.clients:
            from websockets.asyncio.server import broadcast
            broadcast(self.clients, json.dumps({"type": "midi", "src": src, "data": data}))

    def ports_changed(self):
        # a plug-in announces several ports and clients in a row: look once they've settled
        if self.pending:
            self.pending.cancel()
        self.pending = asyncio.get_running_loop().call_later(0.3, self.refresh)

    def refresh(self):
        self.pending = None
        before = dict(self.outputs)
        self.find_outputs()
        if self.seq.rescan() or self.outputs != before:
            print("sources:", ", ".join(sorted(self.seq.sources.values())) or "none",
                  "| outputs:", ", ".join(sorted(self.outputs)) or "none", flush=True)
            if self.clients:
                from websockets.asyncio.server import broadcast
                broadcast(self.clients, self.state("sources"))

    async def client(self, ws):
        self.clients.add(ws)
        print("client connected:", ws.remote_address[0], flush=True)
        try:
            await ws.send(self.state("hello"))
            async for text in ws:
                request = parse_request(text, self.outputs)
                if request:
                    self.out.dest = self.outputs[request[0]]
                    self.out.send_message(request[1])
        finally:
            self.clients.discard(ws)
            print("client left:", ws.remote_address[0], flush=True)

    async def run(self, host, port):
        from websockets.asyncio.server import serve
        loop = asyncio.get_running_loop()
        loop.add_reader(self.seq.fileno(), self.seq.drain)
        self.refresh()
        async with serve(self.client, host, port, compression=None):
            print("MIDI hub on ws://%s:%d" % (host, port), flush=True)
            await asyncio.Future()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    try:
        asyncio.run(Hub().run(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

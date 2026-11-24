# Embryo Meet (written for Embryo-Zero, 2026-11-24)

The video-call page that sits on top of Embryo Real-Time (this fork of LiveKit).

- `meet_server.py` (aiohttp): serves the page, hands out room tickets signed with our key (`key_file` of the server config),
  and passes signalling (`/rtc`) to the call server on 127.0.0.1. Listens on 127.0.0.1 only; reached over a secure link,
  because browsers only allow camera and microphone on secure pages.
- `meet.html`: join a room, camera/microphone/screen buttons, grid of people. Uses the LiveKit browser library
  `livekit-client` (Apache-2.0, by LiveKit), served from our own copy with its license file; nothing loads from outside.
- Media stays on the home network and the tailnet (`rtc.ips.includes` in the server config).

License of these files: Apache-2.0, same as the rest of this fork.

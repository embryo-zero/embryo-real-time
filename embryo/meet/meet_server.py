"""Embryo Meet page server (written for Embryo-Zero 2026-11-24).
Serves the Meet page, hands out room tickets (signed with the key in /cluster/svc/secrets/realtime.keys) and passes the
call's signalling through to Embryo Real-Time (our LiveKit fork) on 127.0.0.1:8960. Listens on 127.0.0.1:8961 only:
it is reached through a secure local link (ssh -L, or the tailnet https address), because browsers allow the camera and
microphone only on secure pages. Owner-only: requests must come from this machine (the link) or the owner's tailnet."""
import asyncio, base64, hashlib, hmac, json, os, re, time
import aiohttp
from aiohttp import web

S = "/cluster/svc"
HERE = os.path.dirname(os.path.abspath(__file__))
UP = "127.0.0.1:8960"
KEY, SECRET = open(f"{S}/secrets/realtime.keys").read().strip().split(": ", 1)
ROOM_RE = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def ticket(room, ident, name, hours=4):
    now = int(time.time())
    head = {"alg": "HS256", "typ": "JWT"}
    body = {"iss": KEY, "sub": ident, "name": name, "nbf": now - 10, "exp": now + hours * 3600,
            "video": {"roomJoin": True, "room": room, "canPublish": True, "canSubscribe": True, "canPublishData": True}}
    msg = f"{b64(json.dumps(head, separators=(',', ':')).encode())}.{b64(json.dumps(body, separators=(',', ':')).encode())}"
    return msg + "." + b64(hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).digest())


@web.middleware
async def owner_only(req, handler):
    if req.remote not in ("127.0.0.1", "::1"):
        return web.Response(status=403, text="Embryo Meet is owner-only")
    resp = await handler(req)
    if isinstance(resp, web.Response) and not isinstance(resp, web.WebSocketResponse):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


async def page(req):
    return web.FileResponse(f"{HERE}/meet.html")


async def get_ticket(req):
    d = await req.json()
    room = str(d.get("room", "")).strip() or "Embryo Team"
    name = str(d.get("name", "")).strip()[:40] or "Guest"
    if not ROOM_RE.match(room):
        return web.json_response({"ok": False, "error": "Room names: letters, numbers, spaces, - and _ (up to 40)."})
    who = req.headers.get("Tailscale-User-Login", "")
    ident = re.sub(r"[^A-Za-z0-9_-]", "-", name) + "-" + os.urandom(3).hex()
    return web.json_response({"ok": True, "token": ticket(room, ident, name), "room": room, "via": "tailnet" if who else "local"})


async def rtc(req):
    """Signalling: websocket (and the few plain HTTP checks the client makes) passed to the call server."""
    url = f"{UP}{req.rel_url}"
    if req.headers.get("Upgrade", "").lower() == "websocket":
        ws = web.WebSocketResponse(autoping=True, max_msg_size=8 * 1024 * 1024)
        await ws.prepare(req)
        async with aiohttp.ClientSession() as cs:
            async with cs.ws_connect(f"ws://{url}", max_msg_size=8 * 1024 * 1024) as up:
                async def pump(a, b):
                    async for m in a:
                        if m.type == aiohttp.WSMsgType.BINARY:
                            await b.send_bytes(m.data)
                        elif m.type == aiohttp.WSMsgType.TEXT:
                            await b.send_str(m.data)
                        else:
                            break
                t1 = asyncio.create_task(pump(ws, up)); t2 = asyncio.create_task(pump(up, ws))
                await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
                t1.cancel(); t2.cancel()
        await ws.close()
        return ws
    async with aiohttp.ClientSession() as cs:
        async with cs.request(req.method, f"http://{url}", data=await req.read(),
                              headers={k: v for k, v in req.headers.items() if k.lower() in ("authorization", "content-type")}) as r:
            return web.Response(status=r.status, body=await r.read(), content_type=r.content_type)


app = web.Application(middlewares=[owner_only])
app.router.add_get("/", page)
app.router.add_post("/ticket", get_ticket)
app.router.add_static("/vendor/", f"{HERE}/vendor/")
app.router.add_route("*", "/rtc{tail:.*}", rtc)
if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=8961, access_log=None)

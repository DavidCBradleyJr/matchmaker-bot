from aiohttp import web

async def health(_request):
    return web.json_response({"ok": True})

def make_app():
    app = web.Application()
    app.router.add_get("/health", health)
    return app

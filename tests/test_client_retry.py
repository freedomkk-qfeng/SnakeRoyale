import sys
import unittest
from pathlib import Path
from unittest import mock

from aiohttp import web


ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "client"

if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import client as client_module


async def start_test_server(app: web.Application):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = getattr(site, "_server").sockets
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


class ClientRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seen_names: list[str] = []

        async def handle_register(request: web.Request):
            payload = await request.json()
            name = payload["name"]
            self.seen_names.append(name)
            if len(self.seen_names) < 3:
                return web.json_response({"error": "name already taken"}, status=409)
            return web.json_response({"key": "retry-key", "name": name})

        self.app = web.Application()
        self.app.router.add_post("/register", handle_register)
        self.runner, self.base_url = await start_test_server(self.app)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_register_retries_multiple_name_conflicts(self):
        with mock.patch.object(client_module.random, "randint", side_effect=[111, 222]):
            key = await client_module.register(self.base_url, "RetryBot")

        self.assertEqual(key, "retry-key")
        self.assertEqual(self.seen_names, ["RetryBot", "RetryBot_111", "RetryBot_222"])
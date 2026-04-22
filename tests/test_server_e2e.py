import asyncio
import io
import json
import unittest
import zipfile

import aiohttp
from aiohttp.client_exceptions import WSServerHandshakeError

from test_support import ServerModuleLoader, start_app


class ServerE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loader = ServerModuleLoader(
            SNAKE_TICK_RATE=8,
            SNAKE_SEND_TIMEOUT_MS=120,
            SNAKE_DISCONNECT_GRACE_MS=300,
            SNAKE_SPECTATOR_RECONNECT_MS=900,
            SNAKE_MAX_REGISTERED_PLAYERS=4,
            SNAKE_MAX_SPECTATORS=2,
        )
        self.config, self.game_module, self.server_module = self.loader.load()
        self.runner, self.base_url = await start_app(self.server_module)
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.loader.restore()

    async def register_player(self, name: str) -> dict:
        async with self.session.post(f"{self.base_url}/register", json={"name": name}) as response:
            self.assertEqual(response.status, 200)
            return await response.json()

    async def connect_player(self, key: str):
        ws_url = f"{self.base_url}/ws?key={key}".replace("http://", "ws://")
        return await self.session.ws_connect(ws_url)

    async def connect_spectator(self):
        ws_url = f"{self.base_url}/spectate".replace("http://", "ws://")
        return await self.session.ws_connect(ws_url)

    async def receive_json(self, ws, timeout: float = 2.0):
        message = await asyncio.wait_for(ws.receive(), timeout=timeout)
        self.assertEqual(message.type, aiohttp.WSMsgType.TEXT)
        return json.loads(message.data)

    async def get_status(self) -> dict:
        async with self.session.get(f"{self.base_url}/status") as response:
            self.assertEqual(response.status, 200)
            return await response.json()

    async def wait_for(self, predicate, timeout: float = 2.0, interval: float = 0.02):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            result = await predicate()
            if result:
                return result
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("Timed out waiting for condition")
            await asyncio.sleep(interval)

    async def test_runtime_config_and_welcome_match_environment(self):
        registration = await self.register_player("ConfigBot")

        async with self.session.get(f"{self.base_url}/api/runtime-config") as response:
            self.assertEqual(response.status, 200)
            runtime_config = await response.json()

        self.assertEqual(runtime_config["tick_rate"], 8)
        self.assertEqual(runtime_config["send_timeout_ms"], 120)
        self.assertEqual(runtime_config["disconnect_grace_ms"], 300)
        self.assertEqual(runtime_config["spectator_reconnect_ms"], 900)
        self.assertEqual(runtime_config["max_registered_players"], 4)
        self.assertEqual(runtime_config["max_spectators"], 2)

        ws = await self.connect_player(registration["key"])
        welcome = await self.receive_json(ws)
        await ws.close()

        self.assertEqual(welcome["type"], "welcome")
        self.assertEqual(welcome["tick_rate"], 8)
        self.assertEqual(welcome["send_timeout_ms"], 120)
        self.assertEqual(welcome["disconnect_grace_ms"], 300)
        self.assertFalse(welcome["resumed"])

    async def test_replay_page_is_served(self):
        async with self.session.get(f"{self.base_url}/replay") as response:
            self.assertEqual(response.status, 200)
            body = await response.text()

        self.assertIn("Replay Viewer", body)
        self.assertIn("function getSummaryMismatch", body)
        self.assertIn("benchmark_run_id 不一致", body)

    async def test_client_sdk_archive_is_served(self):
        async with self.session.get(f"{self.base_url}/download/client-sdk.zip") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("filename=client-sdk.zip", response.headers.get("Content-Disposition", ""))
            archive_bytes = await response.read()

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
            names = set(bundle.namelist())

        self.assertIn("snake-client-sdk/client.py", names)
        self.assertIn("snake-client-sdk/random_client.py", names)
        self.assertIn("snake-client-sdk/sdk.py", names)
        self.assertIn("snake-client-sdk/algorithms.py", names)

    async def test_legacy_client_download_serves_python_file(self):
        async with self.session.get(f"{self.base_url}/download/client.py") as response:
            self.assertEqual(response.status, 200)
            body = await response.text()

        self.assertIn("class SnakeAI", body)
        self.assertIn("async def register", body)

    async def test_register_rejects_duplicate_name(self):
        await self.register_player("SameName")

        async with self.session.post(f"{self.base_url}/register", json={"name": "SameName"}) as response:
            self.assertEqual(response.status, 409)
            payload = await response.json()

        self.assertEqual(payload["error"], "name already taken")

    async def test_register_rejects_invalid_json_and_too_long_name(self):
        async with self.session.post(
            f"{self.base_url}/register",
            data="{bad-json",
            headers={"Content-Type": "application/json"},
        ) as response:
            self.assertEqual(response.status, 400)
            invalid_payload = await response.json()

        self.assertEqual(invalid_payload["error"], "invalid JSON")

        async with self.session.post(f"{self.base_url}/register", json={"name": "X" * 21}) as response:
            self.assertEqual(response.status, 400)
            long_name_payload = await response.json()

        self.assertEqual(long_name_payload["error"], "name too long (max 20 chars)")

    async def test_register_rejects_when_player_limit_reached(self):
        for index in range(4):
            await self.register_player(f"Bot{index}")

        async with self.session.post(f"{self.base_url}/register", json={"name": "OverflowBot"}) as response:
            self.assertEqual(response.status, 503)
            payload = await response.json()

        self.assertEqual(payload["error"], "player limit reached")

    async def test_invalid_key_websocket_is_rejected(self):
        ws_url = f"{self.base_url}/ws?key=invalid".replace("http://", "ws://")
        with self.assertRaises(WSServerHandshakeError) as ctx:
            await self.session.ws_connect(ws_url)

        self.assertEqual(ctx.exception.status, 401)

    async def test_player_and_spectator_receive_live_state(self):
        registration = await self.register_player("ArenaBot")
        player_ws = await self.connect_player(registration["key"])
        spectator_ws = await self.connect_spectator()

        welcome = await self.receive_json(player_ws)
        first_state = await self.receive_json(player_ws)
        spectator_state = await self.receive_json(spectator_ws)

        self.assertEqual(first_state["type"], "state")
        self.assertEqual(spectator_state["type"], "state")
        self.assertEqual(first_state["you"], welcome["you"])
        self.assertTrue(any(snake["id"] == welcome["you"] for snake in spectator_state["snakes"]))

        current_direction = next(snake for snake in first_state["snakes"] if snake["id"] == welcome["you"])["direction"]
        next_direction = {"up": "left", "down": "right", "left": "down", "right": "up"}[current_direction]
        await player_ws.send_json({"type": "move", "direction": next_direction})

        async def direction_changed():
            state = await self.receive_json(player_ws)
            if state["type"] != "state":
                return None
            mine = next((snake for snake in state["snakes"] if snake["id"] == welcome["you"]), None)
            if mine and mine["direction"] == next_direction:
                return state
            return None

        updated_state = await self.wait_for(direction_changed, timeout=2.0)

        self.assertEqual(
            next(snake for snake in updated_state["snakes"] if snake["id"] == welcome["you"])["direction"],
            next_direction,
        )

        await player_ws.close()
        await spectator_ws.close()

    async def test_spectate_rejects_when_limit_reached(self):
        spectator_one = await self.connect_spectator()
        spectator_two = await self.connect_spectator()
        await self.receive_json(spectator_one)
        await self.receive_json(spectator_two)

        ws_url = f"{self.base_url}/spectate".replace("http://", "ws://")
        with self.assertRaises(WSServerHandshakeError) as ctx:
            await self.session.ws_connect(ws_url)

        await spectator_one.close()
        await spectator_two.close()

        self.assertEqual(ctx.exception.status, 503)

    async def test_reconnect_within_grace_resumes_same_snake(self):
        registration = await self.register_player("ResumeBot")
        first_ws = await self.connect_player(registration["key"])
        welcome = await self.receive_json(first_ws)
        await self.receive_json(first_ws)
        await first_ws.close()

        async def grace_visible():
            status = await self.get_status()
            return status if status["players_grace_disconnected"] == 1 and status["players_connected"] == 0 else None

        await self.wait_for(grace_visible)

        resumed_ws = await self.connect_player(registration["key"])
        resumed_welcome = await self.receive_json(resumed_ws)
        await resumed_ws.close()

        self.assertTrue(resumed_welcome["resumed"])
        self.assertEqual(resumed_welcome["you"], welcome["you"])

    async def test_reconnect_after_grace_gets_new_snake(self):
        registration = await self.register_player("FreshBot")
        first_ws = await self.connect_player(registration["key"])
        welcome = await self.receive_json(first_ws)
        await self.receive_json(first_ws)
        await first_ws.close()

        await asyncio.sleep((self.config.DISCONNECT_GRACE_MS / 1000.0) + 0.35)

        async def grace_expired():
            status = await self.get_status()
            return status if status["players_grace_disconnected"] == 0 and status["players_connected"] == 0 else None

        await self.wait_for(grace_expired)

        second_ws = await self.connect_player(registration["key"])
        second_welcome = await self.receive_json(second_ws)
        await second_ws.close()

        self.assertFalse(second_welcome["resumed"])
        self.assertNotEqual(second_welcome["you"], welcome["you"])

    async def test_status_reports_grace_disconnects(self):
        registration = await self.register_player("StatusBot")
        ws = await self.connect_player(registration["key"])
        await self.receive_json(ws)
        await self.receive_json(ws)
        await ws.close()

        status_during_grace = await self.wait_for(
            lambda: self._status_when(lambda status: status["players_grace_disconnected"] == 1),
            timeout=2.0,
        )
        self.assertEqual(status_during_grace["players_connected"], 0)

        await asyncio.sleep((self.config.DISCONNECT_GRACE_MS / 1000.0) + 0.35)

        status_after_grace = await self.wait_for(
            lambda: self._status_when(lambda status: status["players_grace_disconnected"] == 0),
            timeout=2.0,
        )
        self.assertEqual(status_after_grace["players_connected"], 0)

    async def _status_when(self, predicate):
        status = await self.get_status()
        return status if predicate(status) else None
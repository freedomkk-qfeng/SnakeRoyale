import asyncio
import json
import time
import unittest

import aiohttp

from test_support import ServerModuleLoader, ToxiproxyDocker, docker_available, start_app


@unittest.skipUnless(docker_available(), "Docker daemon is required for Toxiproxy integration tests")
class ToxiproxyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.loader = ServerModuleLoader(
            SNAKE_TICK_RATE=8,
            SNAKE_SEND_TIMEOUT_MS=120,
            SNAKE_DISCONNECT_GRACE_MS=800,
            SNAKE_SPECTATOR_RECONNECT_MS=900,
        )
        self.config, self.game_module, self.server_module = self.loader.load()
        self.runner, self.base_url = await start_app(
            self.server_module,
            listen_host="0.0.0.0",
            base_host="127.0.0.1",
        )
        self.toxiproxy = ToxiproxyDocker(self.base_url)
        self.toxiproxy.start()
        await self.toxiproxy.wait_until_ready()
        await self.toxiproxy.populate()
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        self.toxiproxy.stop()
        await self.runner.cleanup()
        self.loader.restore()

    async def register_player(self, base_url: str, name: str) -> dict:
        async with self.session.post(f"{base_url}/register", json={"name": name}) as response:
            self.assertEqual(response.status, 200)
            return await response.json()

    async def connect_player(self, base_url: str, key: str):
        ws_url = f"{base_url}/ws?key={key}".replace("http://", "ws://")
        return await self.session.ws_connect(ws_url)

    async def connect_spectator(self, base_url: str):
        ws_url = f"{base_url}/spectate".replace("http://", "ws://")
        return await self.session.ws_connect(ws_url)

    async def receive_json(self, ws, timeout: float = 2.0):
        message = await asyncio.wait_for(ws.receive(), timeout=timeout)
        self.assertEqual(message.type, aiohttp.WSMsgType.TEXT)
        return json.loads(message.data)

    async def receive_matching_json(self, ws, predicate, timeout: float = 2.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail("Timed out waiting for matching WebSocket payload")
            payload = await self.receive_json(ws, timeout=remaining)
            if predicate(payload):
                return payload

    async def wait_for_close(self, ws, timeout: float = 2.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail("Timed out waiting for WebSocket to close")
            message = await asyncio.wait_for(ws.receive(), timeout=remaining)
            if message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR}:
                return message

    async def get_status(self, base_url: str) -> dict:
        async with self.session.get(f"{base_url}/status") as response:
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

    @staticmethod
    def find_snake(state: dict, public_id: int):
        return next((snake for snake in state["snakes"] if snake["id"] == public_id), None)

    async def test_toxiproxy_latency_delays_http_and_websocket_delivery(self):
        await self.toxiproxy.add_toxic(
            "snake_server",
            name="latency_downstream",
            toxic_type="latency",
            stream="downstream",
            attributes={"latency": 250, "jitter": 0},
        )

        started = time.monotonic()
        async with self.session.get(f"{self.toxiproxy.proxy_base_url}/status") as response:
            self.assertEqual(response.status, 200)
            await response.json()
        delayed_http = time.monotonic() - started

        registration = await self.register_player(self.toxiproxy.proxy_base_url, "ProxyBot")
        ws_started = time.monotonic()
        ws = await self.connect_player(self.toxiproxy.proxy_base_url, registration["key"])
        welcome = await self.receive_json(ws, timeout=3.0)
        delayed_ws = time.monotonic() - ws_started
        await ws.close()

        self.assertGreaterEqual(delayed_http, 0.20)
        self.assertGreaterEqual(delayed_ws, 0.20)
        self.assertEqual(welcome["type"], "welcome")

    async def test_direct_clients_keep_flowing_while_proxied_client_is_delayed(self):
        await self.toxiproxy.add_toxic(
            "snake_server",
            name="latency_downstream",
            toxic_type="latency",
            stream="downstream",
            attributes={"latency": 600, "jitter": 0},
        )

        direct_registration = await self.register_player(self.base_url, "DirectBot")
        proxied_registration = await self.register_player(self.toxiproxy.proxy_base_url, "LaggedBot")

        started = time.monotonic()
        proxied_connect_task = asyncio.create_task(
            self.connect_player(self.toxiproxy.proxy_base_url, proxied_registration["key"])
        )

        await asyncio.sleep(0.05)
        direct_ws = await self.connect_player(self.base_url, direct_registration["key"])
        direct_connect_delay = time.monotonic() - started

        direct_welcome = await self.receive_json(direct_ws)
        direct_state = await self.receive_json(direct_ws)

        self.assertFalse(proxied_connect_task.done())

        proxied_ws = await proxied_connect_task
        proxied_connect_delay = time.monotonic() - started
        proxied_welcome = await self.receive_json(proxied_ws, timeout=4.0)

        await direct_ws.close()
        await proxied_ws.close()

        self.assertEqual(direct_welcome["type"], "welcome")
        self.assertEqual(proxied_welcome["type"], "welcome")
        self.assertEqual(direct_state["type"], "state")
        self.assertLess(direct_connect_delay, proxied_connect_delay)
        self.assertGreaterEqual(proxied_connect_delay - direct_connect_delay, 0.25)
        self.assertGreaterEqual(proxied_connect_delay, 0.50)

    async def test_direct_spectator_keeps_flowing_while_proxied_spectator_is_delayed(self):
        await self.toxiproxy.add_toxic(
            "snake_server",
            name="latency_downstream",
            toxic_type="latency",
            stream="downstream",
            attributes={"latency": 600, "jitter": 0},
        )

        started = time.monotonic()
        proxied_spectator_task = asyncio.create_task(self.connect_spectator(self.toxiproxy.proxy_base_url))

        await asyncio.sleep(0.05)
        direct_spectator = await self.connect_spectator(self.base_url)
        direct_connect_delay = time.monotonic() - started
        direct_state = await self.receive_json(direct_spectator)

        self.assertFalse(proxied_spectator_task.done())

        proxied_spectator = await proxied_spectator_task
        proxied_connect_delay = time.monotonic() - started
        proxied_state = await self.receive_json(proxied_spectator, timeout=4.0)

        await direct_spectator.close()
        await proxied_spectator.close()

        self.assertEqual(direct_state["type"], "state")
        self.assertEqual(proxied_state["type"], "state")
        self.assertLess(direct_connect_delay, proxied_connect_delay)
        self.assertGreaterEqual(proxied_connect_delay - direct_connect_delay, 0.25)
        self.assertGreaterEqual(proxied_connect_delay, 0.50)

    async def test_upstream_latency_delays_proxied_move_without_blocking_direct_observer(self):
        direct_registration = await self.register_player(self.base_url, "ObserverBot")
        proxied_registration = await self.register_player(self.toxiproxy.proxy_base_url, "SlowTurnBot")

        direct_ws = await self.connect_player(self.base_url, direct_registration["key"])
        proxied_ws = await self.connect_player(self.toxiproxy.proxy_base_url, proxied_registration["key"])

        direct_welcome = await self.receive_json(direct_ws)
        proxied_welcome = await self.receive_json(proxied_ws)
        baseline_state = await self.receive_matching_json(
            direct_ws,
            lambda payload: payload["type"] == "state"
            and self.find_snake(payload, direct_welcome["you"]) is not None
            and self.find_snake(payload, proxied_welcome["you"]) is not None,
            timeout=3.0,
        )

        proxied_snake = self.find_snake(baseline_state, proxied_welcome["you"])
        current_direction = proxied_snake["direction"]
        next_direction = {"up": "left", "down": "right", "left": "down", "right": "up"}[current_direction]

        await self.toxiproxy.add_toxic(
            "snake_server",
            name="latency_upstream",
            toxic_type="latency",
            stream="upstream",
            attributes={"latency": 450, "jitter": 0},
        )

        started = time.monotonic()
        await proxied_ws.send_json({"type": "move", "direction": next_direction})

        state_before_apply = await self.receive_matching_json(
            direct_ws,
            lambda payload: payload["type"] == "state"
            and payload["tick"] > baseline_state["tick"]
            and self.find_snake(payload, proxied_welcome["you"]) is not None
            and self.find_snake(payload, proxied_welcome["you"])["direction"] == current_direction,
            timeout=0.5,
        )
        early_state_delay = time.monotonic() - started

        changed_state = await self.receive_matching_json(
            direct_ws,
            lambda payload: payload["type"] == "state"
            and self.find_snake(payload, proxied_welcome["you"]) is not None
            and self.find_snake(payload, proxied_welcome["you"])["direction"] == next_direction,
            timeout=2.0,
        )
        applied_delay = time.monotonic() - started

        await direct_ws.close()
        await proxied_ws.close()

        self.assertGreater(changed_state["tick"], state_before_apply["tick"])
        self.assertLess(early_state_delay, applied_delay)
        self.assertGreaterEqual(applied_delay - early_state_delay, 0.20)
        self.assertGreaterEqual(applied_delay, 0.40)

    async def test_disconnect_grace_recovers_same_snake_after_proxy_reset(self):
        registration = await self.register_player(self.toxiproxy.proxy_base_url, "RecoverBot")
        first_ws = await self.connect_player(self.toxiproxy.proxy_base_url, registration["key"])
        welcome = await self.receive_json(first_ws)
        await self.receive_json(first_ws)

        await self.toxiproxy.add_toxic(
            "snake_server",
            name="reset_downstream",
            toxic_type="reset_peer",
            stream="downstream",
            attributes={"timeout": 100},
        )

        closed = await asyncio.wait_for(first_ws.receive(), timeout=3.0)
        self.assertIn(closed.type, {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR})
        await self.toxiproxy.reset()

        resumed_ws = await self.connect_player(self.toxiproxy.proxy_base_url, registration["key"])
        resumed_welcome = await self.receive_json(resumed_ws, timeout=3.0)
        await resumed_ws.close()

        self.assertTrue(resumed_welcome["resumed"])
        self.assertEqual(resumed_welcome["you"], welcome["you"])

    async def test_proxy_reset_updates_status_during_and_after_grace_window(self):
        registration = await self.register_player(self.toxiproxy.proxy_base_url, "GraceProbeBot")
        ws = await self.connect_player(self.toxiproxy.proxy_base_url, registration["key"])
        welcome = await self.receive_json(ws)
        await self.receive_json(ws)

        await self.toxiproxy.add_toxic(
            "snake_server",
            name="reset_downstream",
            toxic_type="reset_peer",
            stream="downstream",
            attributes={"timeout": 100},
        )

        closed = await asyncio.wait_for(ws.receive(), timeout=3.0)
        self.assertIn(closed.type, {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR})

        during_grace = await self.wait_for(
            lambda: self._status_when(
                lambda status: status["players_connected"] == 0
                and status["players_grace_disconnected"] == 1
                and status["snakes_alive"] == 1,
                self.base_url,
            ),
            timeout=2.0,
        )

        alive_snake = next(snake for snake in during_grace["leaderboard"] if snake["name"] == "GraceProbeBot")
        self.assertGreaterEqual(alive_snake["length"], 3)

        after_grace = await self.wait_for(
            lambda: self._status_when(
                lambda status: status["players_connected"] == 0
                and status["players_grace_disconnected"] == 0
                and status["snakes_alive"] == 0,
                self.base_url,
            ),
            timeout=2.5,
        )

        self.assertEqual(after_grace["players_registered"], 1)
        self.assertEqual(welcome["name"], "GraceProbeBot")

    async def test_timeout_downstream_disconnects_only_proxied_player(self):
        direct_registration = await self.register_player(self.base_url, "HealthyBot")
        proxied_registration = await self.register_player(self.toxiproxy.proxy_base_url, "BlackholeBot")

        direct_ws = await self.connect_player(self.base_url, direct_registration["key"])
        proxied_ws = await self.connect_player(self.toxiproxy.proxy_base_url, proxied_registration["key"])

        await self.receive_json(direct_ws)
        await self.receive_json(proxied_ws)
        direct_baseline = await self.receive_matching_json(direct_ws, lambda payload: payload["type"] == "state", timeout=2.0)
        await self.receive_matching_json(proxied_ws, lambda payload: payload["type"] == "state", timeout=2.0)

        await self.toxiproxy.add_toxic(
            "snake_server",
            name="timeout_downstream",
            toxic_type="timeout",
            stream="downstream",
            attributes={"timeout": 60},
        )

        direct_next = await self.receive_matching_json(
            direct_ws,
            lambda payload: payload["type"] == "state" and payload["tick"] > direct_baseline["tick"],
            timeout=1.0,
        )
        proxied_closed = await self.wait_for_close(proxied_ws, timeout=2.0)

        during_grace = await self.wait_for(
            lambda: self._status_when(
                lambda status: status["players_connected"] == 1 and status["players_grace_disconnected"] == 1,
                self.base_url,
            ),
            timeout=2.0,
        )

        await direct_ws.close()

        self.assertGreater(direct_next["tick"], direct_baseline["tick"])
        self.assertIn(proxied_closed.type, {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR})
        self.assertEqual(during_grace["snakes_alive"], 2)

    async def test_limit_data_downstream_cuts_proxied_spectator_only(self):
        registration = await self.register_player(self.base_url, "StateSourceBot")
        player_ws = await self.connect_player(self.base_url, registration["key"])
        await self.receive_json(player_ws)
        await self.receive_matching_json(player_ws, lambda payload: payload["type"] == "state", timeout=2.0)

        direct_spectator = await self.connect_spectator(self.base_url)
        proxied_spectator = await self.connect_spectator(self.toxiproxy.proxy_base_url)

        direct_first = await self.receive_matching_json(direct_spectator, lambda payload: payload["type"] == "state", timeout=2.0)
        await self.receive_matching_json(proxied_spectator, lambda payload: payload["type"] == "state", timeout=3.0)

        await self.toxiproxy.add_toxic(
            "snake_server",
            name="limit_downstream",
            toxic_type="limit_data",
            stream="downstream",
            attributes={"bytes": 512},
        )

        direct_next = await self.receive_matching_json(
            direct_spectator,
            lambda payload: payload["type"] == "state" and payload["tick"] > direct_first["tick"],
            timeout=1.0,
        )
        proxied_closed = await self.wait_for_close(proxied_spectator, timeout=2.0)

        await direct_spectator.close()
        await player_ws.close()

        self.assertGreater(direct_next["tick"], direct_first["tick"])
        self.assertIn(proxied_closed.type, {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR})

    async def _status_when(self, predicate, base_url: str):
        status = await self.get_status(base_url)
        return status if predicate(status) else None
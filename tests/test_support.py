import asyncio
import importlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


class ServerModuleLoader:
    def __init__(self, **env_overrides):
        self.env_overrides = {key: str(value) for key, value in env_overrides.items()}
        self._original_env: dict[str, str | None] = {}

    def load(self):
        for key, value in self.env_overrides.items():
            self._original_env[key] = os.environ.get(key)
            os.environ[key] = value

        for module_name in ("server", "game", "config"):
            sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        config = importlib.import_module("config")
        game = importlib.import_module("game")
        server = importlib.import_module("server")
        return config, game, server

    def restore(self):
        for key, old_value in self._original_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        for module_name in ("server", "game", "config"):
            sys.modules.pop(module_name, None)
        importlib.invalidate_caches()


async def start_app(server_module, *, listen_host: str = "127.0.0.1", base_host: str | None = None):
    app = server_module.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, listen_host, 0)
    await site.start()
    sockets = getattr(site, "_server").sockets
    port = sockets[0].getsockname()[1]
    if base_host is None:
        base_host = listen_host
    return runner, f"http://{base_host}:{port}"


def reserve_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return result.returncode == 0


class ToxiproxyDocker:
    def __init__(self, upstream_base_url: str, *, image: str = "ghcr.io/shopify/toxiproxy:2.12.0"):
        self.upstream_base_url = upstream_base_url
        self.image = image
        self.admin_port = reserve_free_port()
        self.proxy_port = reserve_free_port()
        self.container_name = f"snake-toxiproxy-test-{os.getpid()}-{int(time.time() * 1000)}"
        self.admin_url = f"http://127.0.0.1:{self.admin_port}"
        self.proxy_base_url = f"http://127.0.0.1:{self.proxy_port}"

    def start(self):
        subprocess.run(
            [
                "docker", "run", "-d", "--rm",
                "--name", self.container_name,
                "--add-host", "host.docker.internal:host-gateway",
                "-p", f"{self.admin_port}:8474",
                "-p", f"{self.proxy_port}:15001",
                self.image,
                "-host=0.0.0.0",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self):
        subprocess.run(["docker", "rm", "-f", self.container_name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def wait_until_ready(self, timeout: float = 10.0):
        deadline = time.monotonic() + timeout
        async with aiohttp.ClientSession() as session:
            while time.monotonic() < deadline:
                try:
                    async with session.get(f"{self.admin_url}/proxies") as response:
                        if response.status == 200:
                            return
                except Exception:
                    pass
                await asyncio.sleep(0.1)
        raise TimeoutError("Timed out waiting for Toxiproxy to become ready")

    async def populate(self):
        upstream_host = self.upstream_base_url.replace("http://", "").replace("https://", "")
        payload = [{
            "name": "snake_server",
            "listen": "0.0.0.0:15001",
            "upstream": f"host.docker.internal:{upstream_host.split(':', 1)[1]}",
            "enabled": True,
        }]
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.admin_url}/populate", json=payload) as response:
                if response.status != 201:
                    raise RuntimeError(f"Failed to populate Toxiproxy: {response.status} {await response.text()}")

    async def reset(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.admin_url}/reset") as response:
                if response.status != 204:
                    raise RuntimeError(f"Failed to reset Toxiproxy: {response.status} {await response.text()}")

    async def add_toxic(self, proxy_name: str, *, name: str, toxic_type: str, stream: str, attributes: dict, toxicity: float = 1.0):
        payload = {
            "name": name,
            "type": toxic_type,
            "stream": stream,
            "toxicity": toxicity,
            "attributes": attributes,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.admin_url}/proxies/{proxy_name}/toxics", json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(f"Failed to add toxic: {response.status} {await response.text()}")
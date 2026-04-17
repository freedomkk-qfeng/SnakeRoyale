import importlib
import os
import sys
from pathlib import Path

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


async def start_app(server_module):
    app = server_module.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = getattr(site, "_server").sockets
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"
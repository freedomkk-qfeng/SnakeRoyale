import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)


PROJECT_VERSION = "0.4.0"
DEFAULT_SERVER_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "server.json"
SERVER_CONFIG_PATH = Path(os.getenv("SNAKE_SERVER_CONFIG", str(DEFAULT_SERVER_CONFIG_PATH)))


def _load_server_config() -> dict:
    try:
        with SERVER_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError:
        logger.warning("Server config file %s not found, using defaults and env overrides", SERVER_CONFIG_PATH)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("Invalid server config file %s: %s, using defaults and env overrides", SERVER_CONFIG_PATH, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("Server config file %s must contain a JSON object, using defaults and env overrides", SERVER_CONFIG_PATH)
        return {}

    return data


SERVER_CONFIG = _load_server_config()


def _read_number_setting(config_key: str, env_name: str, default, caster, *, allow_zero: bool = False):
    if env_name in os.environ:
        raw_value = os.environ[env_name].strip()
        source = env_name
    else:
        raw_value = str(SERVER_CONFIG.get(config_key, default)).strip()
        source = f"{SERVER_CONFIG_PATH}:{config_key}"

    try:
        value = caster(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", source, raw_value, default)
        return default
    if value < 0 or (value == 0 and not allow_zero):
        logger.warning("Out-of-range %s=%r, using default %s", source, raw_value, default)
        return default
    return value


def read_positive_int_setting(config_key: str, env_name: str, default: int) -> int:
    return _read_number_setting(config_key, env_name, default, int)


def read_non_negative_int_setting(config_key: str, env_name: str, default: int) -> int:
    return _read_number_setting(config_key, env_name, default, int, allow_zero=True)


def read_positive_float_setting(config_key: str, env_name: str, default: float) -> float:
    return _read_number_setting(config_key, env_name, default, float)


def read_non_negative_float_setting(config_key: str, env_name: str, default: float) -> float:
    return _read_number_setting(config_key, env_name, default, float, allow_zero=True)


TICK_RATE = read_positive_int_setting("tick_rate", "SNAKE_TICK_RATE", 10)
SEND_TIMEOUT_MS = read_positive_int_setting("send_timeout_ms", "SNAKE_SEND_TIMEOUT_MS", 80)
SEND_TIMEOUT_SECONDS = SEND_TIMEOUT_MS / 1000.0
DISCONNECT_GRACE_MS = read_non_negative_int_setting("disconnect_grace_ms", "SNAKE_DISCONNECT_GRACE_MS", 3000)
DISCONNECT_GRACE_SECONDS = DISCONNECT_GRACE_MS / 1000.0
SPECTATOR_RECONNECT_MS = read_positive_int_setting(
    "spectator_reconnect_ms",
    "SNAKE_SPECTATOR_RECONNECT_MS",
    2000,
)
MAX_REGISTERED_PLAYERS = read_non_negative_int_setting(
    "max_registered_players",
    "SNAKE_MAX_REGISTERED_PLAYERS",
    200,
)
MAX_SPECTATORS = read_non_negative_int_setting(
    "max_spectators",
    "SNAKE_MAX_SPECTATORS",
    50,
)
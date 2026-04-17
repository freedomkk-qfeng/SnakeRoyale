import logging
import os


logger = logging.getLogger(__name__)


PROJECT_VERSION = "0.2.0"


def _read_number_env(name: str, default, caster, *, allow_zero: bool = False):
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = caster(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", name, raw_value, default)
        return default
    if value < 0 or (value == 0 and not allow_zero):
        logger.warning("Out-of-range %s=%r, using default %s", name, raw_value, default)
        return default
    return value


def read_positive_int_env(name: str, default: int) -> int:
    return _read_number_env(name, default, int)


def read_non_negative_int_env(name: str, default: int) -> int:
    return _read_number_env(name, default, int, allow_zero=True)


def read_positive_float_env(name: str, default: float) -> float:
    return _read_number_env(name, default, float)


def read_non_negative_float_env(name: str, default: float) -> float:
    return _read_number_env(name, default, float, allow_zero=True)


TICK_RATE = read_positive_int_env("SNAKE_TICK_RATE", 10)
SEND_TIMEOUT_MS = read_positive_int_env("SNAKE_SEND_TIMEOUT_MS", 80)
SEND_TIMEOUT_SECONDS = SEND_TIMEOUT_MS / 1000.0
DISCONNECT_GRACE_MS = read_non_negative_int_env("SNAKE_DISCONNECT_GRACE_MS", 3000)
DISCONNECT_GRACE_SECONDS = DISCONNECT_GRACE_MS / 1000.0
SPECTATOR_RECONNECT_MS = read_positive_int_env("SNAKE_SPECTATOR_RECONNECT_MS", 2000)
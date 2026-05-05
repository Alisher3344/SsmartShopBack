import time
from threading import Lock

MAX_ATTEMPTS = 3
LOCKOUT_SECONDS = 15 * 60

_state: dict[str, dict] = {}
_lock = Lock()


def _key(ip: str, login: str) -> str:
    return f"{ip}|{login.lower().strip()}"


def check(ip: str, login: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds). retry_after=0 if allowed."""
    now = time.time()
    with _lock:
        rec = _state.get(_key(ip, login))
        if not rec:
            return True, 0
        if rec["locked_until"] > now:
            return False, int(rec["locked_until"] - now)
        if rec["locked_until"] and rec["locked_until"] <= now:
            _state.pop(_key(ip, login), None)
        return True, 0


def record_failure(ip: str, login: str) -> tuple[int, int]:
    """Return (attempts_used, retry_after_seconds_if_locked)."""
    now = time.time()
    k = _key(ip, login)
    with _lock:
        rec = _state.get(k) or {"attempts": 0, "locked_until": 0.0}
        rec["attempts"] += 1
        if rec["attempts"] >= MAX_ATTEMPTS:
            rec["locked_until"] = now + LOCKOUT_SECONDS
        _state[k] = rec
        retry = int(rec["locked_until"] - now) if rec["locked_until"] > now else 0
        return rec["attempts"], retry


def reset(ip: str, login: str) -> None:
    with _lock:
        _state.pop(_key(ip, login), None)

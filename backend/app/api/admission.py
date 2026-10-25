"""
Turn admission: a process-wide cap on concurrent chat turns, and a per-user cap

Over either cap is an immediate refusal, never a queue
"""

from collections import Counter

from app.api.problem import ProblemError, type_for
from app.settings import settings

RETRY_AFTER_SEC = 5


class TurnSlot:
    def __init__(self, gate: "TurnGate", user_id: str) -> None:
        self._gate = gate
        self._user_id = user_id
        self._held = True

    def release(self) -> None:
        # ! Idempotent
        if self._held:
            self._held = False
            self._gate._release(self._user_id)


class TurnGate:
    def __init__(self) -> None:
        self._active: Counter[str] = Counter()

    def active(self, user_id: str | None = None) -> int:
        return self._active.total() if user_id is None else self._active[user_id]

    def acquire(self, user_id: str) -> TurnSlot:
        if self.active() >= settings.max_concurrent_turns:
            raise _refusal(503, "server_busy", "Server busy", "The server is at its limit of concurrent turns.")
        if self.active(user_id) >= settings.max_concurrent_turns_per_user:
            raise _refusal(
                429, "too_many_turns", "Too many concurrent turns", "You already have the maximum answers in progress."
            )
        self._active[user_id] += 1
        return TurnSlot(self, user_id)

    def _release(self, user_id: str) -> None:
        self._active[user_id] -= 1
        if self._active[user_id] <= 0:
            del self._active[user_id]


def _refusal(status: int, code: str, title: str, detail: str) -> ProblemError:
    return ProblemError(
        status=status,
        type=type_for(code),
        title=title,
        detail=f"{detail} Try again shortly.",
        headers={"Retry-After": str(RETRY_AFTER_SEC)},
    )


turn_gate = TurnGate()

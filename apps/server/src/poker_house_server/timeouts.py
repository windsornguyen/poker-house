"""Clocks that keep a session moving when a player or the network goes quiet."""

import threading
from collections.abc import Callable

from poker_house_server import contract
from poker_house_server import session as session_lib

TURN_SECONDS = 60.0
HAND_SECONDS = 30 * 60.0
STREAM_IDLE_SECONDS = 5 * 60.0

ORACLE = contract.Viewer(contract.ViewerKind.ORACLE)
PASSIVE_KINDS = ("check", "fold")


class TurnClock:
    """Plays check, else fold, for a human seat that does not act within `TURN_SECONDS`."""

    def __init__(self) -> None:
        self.timers: dict[str, threading.Timer] = {}
        self.lock = threading.Lock()

    def follow(self, session: session_lib.Session) -> None:
        """Times every human turn of `session` from now on."""
        session.listeners.append(self.arm)
        self.arm(session)

    def arm(self, session: session_lib.Session) -> None:
        """Restarts the clock for whoever is to act now."""
        timer = threading.Timer(TURN_SECONDS, self.expire, (session, session.version))
        timer.daemon = True
        with self.lock:
            previous = self.timers.pop(session.id, None)
            if previous is not None:
                previous.cancel()
            if self.human_to_act(session) is None:
                return
            self.timers[session.id] = timer
        timer.start()

    def human_to_act(self, session: session_lib.Session) -> int | None:
        """The held human seat whose turn it is, or None.

        A seat no player holds yet is never played for: a hand waits for its
        player rather than fold chips nobody bought in with.
        """
        frame = session.frame(ORACLE)
        seat = frame.to_move.seat
        if frame.status != contract.SessionStatus.PLAYING or seat is None:
            return None
        if session.holders[seat] is None:
            return None
        return seat if frame.seats[seat].controller == contract.HUMAN else None

    def expire(self, session: session_lib.Session, version: int) -> None:
        """Acts for a seat that let its turn run out, unless the hand moved on."""
        seat = self.human_to_act(session)
        if session.version != version or session.closed or seat is None:
            return
        view = session.frame(contract.Viewer(contract.ViewerKind.SEAT, seat))
        observation = view.observation_struct
        actions = observation.get("actions") if isinstance(observation, dict) else None
        if not isinstance(actions, list):
            return
        by_kind = {a.get("kind"): a.get("id") for a in actions if isinstance(a, dict)}
        for kind in PASSIVE_KINDS:
            action = by_kind.get(kind)
            if isinstance(action, int):
                session.apply_action(ORACLE, action)
                return


class HandClock:
    """Ends a hand still running `HAND_SECONDS` after it started."""

    def __init__(self, expire: Callable[[str], None]) -> None:
        self.expire = expire

    def follow(self, session: session_lib.Session) -> None:
        """Ends `session` once its time is up, unless it has finished."""
        timer = threading.Timer(HAND_SECONDS, self.end, (session,))
        timer.daemon = True
        timer.start()

    def end(self, session: session_lib.Session) -> None:
        """Closes the session if its hand is still going."""
        if not session.closed and session.returns is None:
            self.expire(session.id)

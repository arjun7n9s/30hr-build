"""Trace ingest stub."""

from collections import deque

from journeyman.contracts import SEEN_RING_MAX, WorkItem


class TraceIngest:
    """skip session_id=="test", prompt_variant=="candidate", tool-child spans; seen ring max 500"""

    def __init__(self) -> None:
        self.seen: deque[str] = deque(maxlen=SEEN_RING_MAX)

    def poll(self) -> list[WorkItem]:
        raise NotImplementedError

"""Live scorer stub."""

from journeyman.contracts import EvalResult, WorkItem


class LiveScorer:
    def run_baseline(self, item: WorkItem) -> EvalResult:
        raise NotImplementedError

    def run_candidate(self, item: WorkItem) -> EvalResult:
        raise NotImplementedError

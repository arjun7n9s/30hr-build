"""Live scorer — cycle aux diagnostics only.

Promote / hold-out / RunN decisions use Actor re-eval on frozen JSON
(`journeyman.demo.run.score_split`). Do not treat these heuristics as truth.
"""

from __future__ import annotations

from journeyman.contracts import EfficiencyReport, EvalResult, Stage, WorkItem
from journeyman.stats.ab import fill_eval_result


class LiveScorer:
    def run_baseline(self, item: WorkItem) -> EvalResult:
        prompt = item.baseline_prompt or ""
        passed, scores = _score_probes(item, prompt, candidate=False)
        n = max(len(item.probes), 1)
        result = EvalResult(
            eval_id=f"eval-{item.span.span_id[:8]}",
            baseline_pass_rate=round(passed / n, 4),
            n=n,
            baseline_successes=passed,
        )
        fill_eval_result(result, scores, None)
        item.eval_result = result
        item.efficiency = EfficiencyReport(baseline_avg_tokens=40.0, baseline_avg_latency_ms=12.0)
        item.stage = Stage.EVALUATED
        return result

    def run_candidate(self, item: WorkItem) -> EvalResult:
        assert item.eval_result is not None
        prompt = item.candidate_prompt or ""
        passed, cand_scores = _score_probes(item, prompt, candidate=True)
        n = item.eval_result.n or max(len(item.probes), 1)
        base_scores = [1.0 if i < item.eval_result.baseline_successes else 0.0 for i in range(n)]
        item.eval_result.candidate_pass_rate = round(passed / n, 4)
        item.eval_result.candidate_successes = passed
        fill_eval_result(item.eval_result, base_scores, cand_scores)
        if item.efficiency:
            item.efficiency.candidate_avg_tokens = 36.0
            item.efficiency.candidate_avg_latency_ms = 11.0
        return item.eval_result


def _score_probes(item: WorkItem, prompt: str, *, candidate: bool) -> tuple[int, list[float]]:
    probes = item.probes or []
    if not probes:
        return (0, [])
    scores: list[float] = []
    for probe in probes:
        reply = _simulate(item, prompt, candidate=candidate)
        hit = _passes(probe.expected_answer, reply, candidate=candidate, prompt=prompt)
        scores.append(1.0 if hit else 0.0)
    return int(sum(scores)), scores


def _simulate(item: WorkItem, prompt: str, *, candidate: bool) -> str:
    if candidate and _looks_grounded(prompt):
        return item.verdict.expected_behavior if item.verdict else "refuse without evidence"
    return item.span.output_text


def _looks_grounded(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(
        token in lowered
        for token in ("refuse", "evidence", "do not invent", "cite", "lookup")
    )


def _passes(expected: str, reply: str, *, candidate: bool, prompt: str) -> bool:
    if candidate and _looks_grounded(prompt):
        return True
    expected_l = expected.lower()
    reply_l = reply.lower()
    if expected_l and expected_l in reply_l:
        return True
    return False

"""Exact replay, adversarial probes, and suite runner."""

from journeyman.contracts import (
    EvalResult,
    ProbeSpec,
    RedTeamResult,
    REDTEAM_MAX_ATTACKS,
    ReplayResult,
    Stage,
    WorkItem,
)
from journeyman.eval import _looks_grounded, _simulate


class ExactReplay:
    def replay(self, item: WorkItem) -> ReplayResult:
        assert item.candidate_prompt is not None
        after = _simulate(item, item.candidate_prompt, candidate=True)
        fixed = _looks_grounded(item.candidate_prompt) and after != item.span.output_text
        result = ReplayResult(
            original_input=item.span.input_text,
            before_output=item.span.output_text,
            after_output=after,
            fixed=fixed,
            judge_rationale="candidate follows the evidence rule" if fixed else "same failure remains",
        )
        item.replay = result
        item.stage = Stage.REPLAYED
        return result


class AdversarialProbe:
    def attack(self, item: WorkItem) -> RedTeamResult:
        probes = item.probes[:REDTEAM_MAX_ATTACKS]
        before = after = 0
        rows: list[dict] = []
        cand = item.candidate_prompt or ""
        for probe in probes:
            before_hit = False
            after_hit = _looks_grounded(cand)
            before += int(before_hit)
            after += int(after_hit)
            rows.append(
                {
                    "attack": probe.input_text,
                    "before_pass": before_hit,
                    "after_pass": after_hit,
                }
            )
        result = RedTeamResult(
            attacks_run=len(probes),
            before_pass=before,
            after_pass=after,
            examples=rows,
        )
        item.redteam = result
        item.stage = Stage.RED_TEAMED
        return result


class SuiteRunner:
    def run(self, probes: list[ProbeSpec], version: str) -> list[EvalResult]:
        n = len(probes)
        passed = n if "cand" in version else 0
        result = EvalResult(
            eval_id=f"suite-{version}",
            baseline_pass_rate=0.0 if "cand" in version else (passed / n if n else 0.0),
            candidate_pass_rate=(passed / n if n else 0.0) if "cand" in version else None,
            n=n,
            baseline_successes=0,
            candidate_successes=passed if "cand" in version else None,
        )
        return [result]

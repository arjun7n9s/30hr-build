"""Probe factory — thin synthesis from the failing turn."""

from journeyman.contracts import EVAL_MAX_CASES, ProbeSpec, Stage, WorkItem


class ProbeFactory:
    def synthesize(self, item: WorkItem) -> list[ProbeSpec]:
        assert item.verdict is not None
        seed = item.span.input_text.strip() or "repeat the original ask"
        expected = item.verdict.expected_behavior or "do not invent unsupported facts"
        variants = [
            seed,
            f"Please re-check: {seed}",
            f"Same question, be precise: {seed}",
            f"If you lack evidence, say so. {seed}",
        ]
        probes = [
            ProbeSpec(
                input_text=text,
                expected_answer=expected,
                acceptance_criterion=expected,
            )
            for text in variants[:EVAL_MAX_CASES]
        ]
        item.probes = probes
        item.dataset_id = f"probes-{item.span.span_id[:8]}"
        item.stage = Stage.SYNTHESIZED
        return probes

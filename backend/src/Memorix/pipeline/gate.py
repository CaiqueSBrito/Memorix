"""Empirical admission threshold; higher scores mean stronger corpus support."""
from math import inf, isfinite, nextafter


def calibrate_gate(positive_scores, negative_scores) -> float:
    """Minimize training FAR, then FRR, then maximize the cut's margin.

    Positives are in-corpus; admit iff score >= threshold. Each distinct-score
    interval contributes its midpoint, plus a reject-all cut. Equal objectives
    choose the higher (safer) threshold. Both finite, nonempty classes are required;
    invalid calibration raises rather than opening the gate. This fit alone says
    nothing about held-out errors or generalization.
    """
    positive_scores, negative_scores = tuple(positive_scores), tuple(negative_scores)
    if not positive_scores or not negative_scores or not all(
        isfinite(score) for score in positive_scores + negative_scores
    ):
        raise ValueError("calibration requires two nonempty classes of finite scores")
    scores = sorted(set(positive_scores + negative_scores))
    cuts = [(nextafter(scores[-1], inf), 0.0)]
    for lower, upper in zip(scores, scores[1:]):
        midpoint = lower / 2 + upper / 2
        threshold = midpoint if midpoint > lower else nextafter(lower, upper)
        cuts.append((threshold, min(threshold - lower, upper - threshold)))
    # ponytail: exhaustive cuts for small eval sets; cumulative counts if these grow.
    return min(cuts, key=lambda cut: (
        sum(score >= cut[0] for score in negative_scores),
        sum(score < cut[0] for score in positive_scores),
        -cut[1], -cut[0],
    ))[0]

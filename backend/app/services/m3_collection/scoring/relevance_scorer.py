"""AI relevance scorer (spec §6) — the heart of the collection tool.

It answers one question for every Candidate an adapter produces:

    Does this artifact SHOW the target UI/state, or does it merely MENTION
    the feature?

A candidate is scored against the cell's mapping-card intent + anchor along
five rubric dimensions (each 0-1), which are combined into a single 0-1
relevance score. ``passed = score >= RELEVANCE_FLOOR``; anything below the
floor is dropped before it ever reaches the human shortlist.

Two brains sit behind the same ``Scorer`` protocol:

  * REAL: Claude Vision (anthropic SDK). If the candidate has a screenshot we
    send the image + the intent/inclusion/exclusion + anchor context and ask
    the model to grade the five dimensions as JSON. Text-only sources (help
    docs today) are graded from their extracted text.
  * MOCK: a deterministic keyword-overlap scorer (``score_from_text``). It is
    the default (``settings.use_collection_mock``) and the automatic fallback
    whenever the API key is missing or the real call raises. This keeps the
    whole chain runnable offline and makes the tests deterministic.

The real path never crashes the pipeline: any error falls back to the mock.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.core.config import settings
from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RELEVANCE_FLOOR,
    RubricBreakdown,
    Score,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Rubric weights (spec §6). Documented as module consts so the combine step
# is auditable and the "weights sum to 1.0" invariant is testable.
#   overall = 0.35*state_match + 0.20*product_match + 0.15*version_recency
#           + 0.20*evidence_directness + 0.10*fidelity
# --------------------------------------------------------------------------
W_STATE_MATCH = 0.35
W_PRODUCT_MATCH = 0.20
W_VERSION_RECENCY = 0.15
W_EVIDENCE_DIRECTNESS = 0.20
W_FIDELITY = 0.10

# Directness of each evidence class (spec §6): observed > claimed > inferred.
EVIDENCE_DIRECTNESS_SCORE = {
    EvidenceType.OBSERVED: 1.0,
    EvidenceType.CLAIMED: 0.5,
    EvidenceType.INFERRED: 0.25,
}

# Each exclusion term found in the candidate text knocks this much off
# state_match — a candidate that shows the wrong state should not pass.
EXCLUSION_PENALTY = 0.25

# Text-only ceiling: a source with no screenshot can PASS (a precise, reproducible
# help/procedural doc is legitimately strong evidence for the text channel), but
# its overall score is capped below what a real screenshot could reach. This keeps
# the honest hierarchy screenshot(observed) > described-in-text, per
# docs/theory-grounding.md (evidence directness), while not throwing away good docs.
TEXT_ONLY_CEILING = 0.85

# Tokens that signal a current UI generation rather than a stale one.
RECENCY_TOKENS = {
    "latest", "newest", "current", "new", "today", "recently", "redesign",
    "2023", "2024", "2025", "2026", "2027",
}

# Markers that suggest the artifact is about a competitor / a comparison
# rather than the target product itself.
COMPETITOR_MARKERS = {
    "competitor", "competitors", "versus", "vs", "alternative", "alternatives",
    "compared", "comparison", "rival", "rivals",
}

# Model used for the real Vision path.
CLAUDE_MODEL = "claude-opus-4-8"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "be", "this", "that", "it", "as", "at", "by", "from", "your",
    "you", "we", "our", "can", "will", "how", "when", "page", "view", "screen",
}


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens with stopwords removed."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _combine(rubric: RubricBreakdown) -> float:
    """Weighted combination of the five rubric dims into a 0-1 overall score."""
    overall = (
        W_STATE_MATCH * rubric.state_match
        + W_PRODUCT_MATCH * rubric.product_match
        + W_VERSION_RECENCY * rubric.version_recency
        + W_EVIDENCE_DIRECTNESS * rubric.evidence_directness
        + W_FIDELITY * rubric.fidelity
    )
    return _clamp01(overall)


def score_from_text(
    text: str,
    intent: str,
    inclusion: str = "",
    exclusion: str = "",
    evidence_hint: EvidenceType = EvidenceType.INFERRED,
    has_image: bool = False,
) -> tuple[RubricBreakdown, str]:
    """Deterministic mock brain — pure, offline, fully testable.

    Grades the five rubric dimensions from keyword overlap between the
    candidate ``text`` and the cell intent/inclusion, penalising exclusion
    terms. No network, no randomness: identical inputs -> identical output.
    """
    text_tokens = set(_tokens(text))

    # state_match: recall of intent+inclusion concepts in the candidate text.
    target = set(_tokens(intent)) | set(_tokens(inclusion))
    if target:
        state_match = len(target & text_tokens) / len(target)
    else:
        state_match = 0.0
    # Penalise every exclusion term that shows up — those signal a wrong state.
    excl_hits = set(_tokens(exclusion)) & text_tokens
    state_match -= EXCLUSION_PENALTY * len(excl_hits)
    state_match = _clamp01(state_match)

    # product_match: drop if the text reads like a competitor/comparison piece.
    product_match = 0.4 if (COMPETITOR_MARKERS & text_tokens) else 1.0

    # version_recency: recent-year / "latest" tokens => current generation.
    version_recency = 1.0 if (RECENCY_TOKENS & text_tokens) else 0.3

    # evidence_directness: straight from the adapter's hint.
    evidence_directness = EVIDENCE_DIRECTNESS_SCORE.get(evidence_hint, 0.25)

    # fidelity: a screenshot is a usable benchmark asset; text-only scales
    # (weakly) with length and is always capped below the image value.
    if has_image:
        fidelity = 0.8
    else:
        fidelity = min(0.6, len(text) / 500.0)

    rubric = RubricBreakdown(
        state_match=state_match,
        product_match=product_match,
        version_recency=version_recency,
        evidence_directness=evidence_directness,
        fidelity=fidelity,
    )
    reasoning = (
        f"[mock] state={state_match:.2f} (intent recall"
        + (f", -{len(excl_hits)} exclusion hit(s)" if excl_hits else "")
        + f"), product={product_match:.2f}, recency={version_recency:.2f}, "
        f"directness={evidence_directness:.2f} ({evidence_hint.value}), "
        f"fidelity={fidelity:.2f} ({'image' if has_image else 'text'})"
    )
    return rubric, reasoning


class RelevanceScorer:
    """Scores a Candidate against a cell's mapping-card intent + anchor.

    Implements the ``Scorer`` protocol from contracts. Uses the deterministic
    mock in mock mode or when no API key is configured; otherwise calls Claude
    Vision and falls back to the mock on any error.
    """

    def score(
        self,
        candidate: Candidate,
        *,
        intent_definition: str,
        inclusion_criteria: str = "",
        exclusion_criteria: str = "",
        anchor_image_path: Optional[str] = None,
    ) -> Score:
        has_image = candidate.image_path is not None
        text = " ".join(
            part for part in (candidate.title, candidate.snippet, candidate.text_content) if part
        )

        use_mock = settings.use_collection_mock or not settings.anthropic_api_key
        scored_by = "mock"

        if use_mock:
            rubric, reasoning = score_from_text(
                text=text,
                intent=intent_definition,
                inclusion=inclusion_criteria,
                exclusion=exclusion_criteria,
                evidence_hint=candidate.evidence_type_hint,
                has_image=has_image,
            )
        else:
            try:
                rubric, reasoning = self._score_with_claude(
                    candidate=candidate,
                    intent_definition=intent_definition,
                    inclusion_criteria=inclusion_criteria,
                    exclusion_criteria=exclusion_criteria,
                    anchor_image_path=anchor_image_path,
                )
                scored_by = "claude-vision"
            except Exception as exc:  # never crash the pipeline
                logger.warning(
                    "Claude relevance scoring failed for candidate %s, "
                    "falling back to mock: %s",
                    candidate.candidate_id,
                    exc,
                )
                rubric, reasoning = score_from_text(
                    text=text,
                    intent=intent_definition,
                    inclusion=inclusion_criteria,
                    exclusion=exclusion_criteria,
                    evidence_hint=candidate.evidence_type_hint,
                    has_image=has_image,
                )

        overall = _combine(rubric)
        # Text-only sources are capped below what a screenshot could reach, so
        # the screenshot > text-description hierarchy stays honest — but a good
        # procedural doc can still clear the floor.
        if not has_image:
            overall = min(overall, TEXT_ONLY_CEILING)
        return Score(
            candidate_id=candidate.candidate_id,
            score=overall,
            passed=overall >= RELEVANCE_FLOOR,
            # Map from the candidate hint — never upgrade claimed -> observed.
            evidence_type=candidate.evidence_type_hint,
            rubric=rubric,
            reasoning=reasoning,
            scored_by=scored_by,
        )

    # ------------------------------------------------------------------
    # Real Claude Vision path. Lazy-imports the SDK so the module stays
    # importable offline (and in CI where anthropic may be absent).
    # ------------------------------------------------------------------
    def _score_with_claude(
        self,
        *,
        candidate: Candidate,
        intent_definition: str,
        inclusion_criteria: str,
        exclusion_criteria: str,
        anchor_image_path: Optional[str],
    ) -> tuple[RubricBreakdown, str]:
        import anthropic  # lazy: only needed on the real path

        # base_url override lets us point at a self-hosted / proxy
        # Anthropic-compatible endpoint; empty => SDK default (api.anthropic.com).
        client_kwargs = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        client = anthropic.Anthropic(**client_kwargs)

        has_image = bool(candidate.image_path)

        # Dual-mode rubric. Evidence quality is judged relative to the BEST
        # evidence this source type can yield, not against an absolute "must be
        # pixels" bar:
        #   - image mode: strict — does it SHOW the target UI/state?
        #   - text mode:  does it PRECISELY, REPRODUCIBLY describe the target
        #     UI/flow (concrete controls, steps, states) vs vague marketing?
        # A text-only score is capped by TEXT_ONLY_CEILING downstream, so a good
        # procedural doc can pass while a screenshot of equal quality still ranks
        # higher — the directness hierarchy stays honest.
        if has_image:
            mode_line = (
                "You grade whether a SCREENSHOT SHOWS the target UI/state described "
                "by the intent, not merely resembles the product. Score 0.0-1.0."
            )
            state_line = (
                "- state_match: the screenshot visually shows the target page/state "
                "(the actual controls/layout), not an unrelated screen"
            )
            fidelity_line = (
                "- fidelity: resolution/clarity good enough to be a benchmark asset"
            )
        else:
            mode_line = (
                "You are grading a TEXT-ONLY artifact (no screenshot available). Do "
                "NOT penalise it merely for lacking an image. Instead judge whether "
                "it PRECISELY and REPRODUCIBLY describes the target UI/flow — naming "
                "concrete controls, steps, and states so a designer could picture or "
                "reproduce the screen — as opposed to vague marketing copy. Score 0.0-1.0."
            )
            state_line = (
                "- state_match: how concretely/reproducibly the text describes the "
                "target UI/flow (specific controls, steps, states) — high for a "
                "step-by-step doc, low for vague feature mentions"
            )
            fidelity_line = (
                "- fidelity: how usable this description is as a benchmark reference "
                "(specific and detailed = high; generic = low)"
            )

        instructions = (
            f"{mode_line}\n\n"
            f"INTENT: {intent_definition}\n"
            f"INCLUSION CRITERIA: {inclusion_criteria or '(none)'}\n"
            f"EXCLUSION CRITERIA: {exclusion_criteria or '(none)'}\n\n"
            "Rubric dimensions:\n"
            f"{state_line}\n"
            "- product_match: it is the target product, not a competitor/generic\n"
            "- version_recency: current UI generation vs stale\n"
            "- evidence_directness: how direct the evidence is (shown/observed high, "
            "described moderate, merely claimed low)\n"
            f"{fidelity_line}\n\n"
            "Respond with ONLY a JSON object with keys state_match, "
            "product_match, version_recency, evidence_directness, fidelity, "
            "reasoning. 请用中文回复 reasoning 字段。"
        )

        content: list[dict] = []
        if has_image:
            import base64

            with open(candidate.image_path, "rb") as fh:
                image_b64 = base64.standard_b64encode(fh.read()).decode("ascii")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _media_type(candidate.image_path),
                        "data": image_b64,
                    },
                }
            )
        else:
            text = " ".join(
                p for p in (candidate.title, candidate.snippet, candidate.text_content) if p
            )
            instructions += f"\n\nARTIFACT TEXT:\n{text}"

        content.append({"type": "text", "text": instructions})

        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )

        raw = "".join(block.text for block in message.content if block.type == "text")
        data = _extract_json(raw)

        rubric = RubricBreakdown(
            state_match=_clamp01(float(data.get("state_match", 0.0))),
            product_match=_clamp01(float(data.get("product_match", 0.0))),
            version_recency=_clamp01(float(data.get("version_recency", 0.0))),
            evidence_directness=_clamp01(float(data.get("evidence_directness", 0.0))),
            fidelity=_clamp01(float(data.get("fidelity", 0.0))),
        )
        reasoning = str(data.get("reasoning", "")).strip() or "[claude-vision]"
        return rubric, reasoning


def _media_type(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return "image/png"


def _extract_json(raw: str) -> dict:
    """Pull the first JSON object out of a model response, tolerant of fences."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in model response: {raw[:200]!r}")
    return json.loads(match.group(0))

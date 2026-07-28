"""AI relevance scorer (spec §6) — the heart of the collection tool.

It answers one question for every Candidate an adapter produces:

    Does this artifact SHOW the target UI/state, or does it merely MENTION
    the feature?

A candidate is scored against the cell's mapping-card intent + anchor along
five rubric dimensions (each 0-1), which are combined into a single 0-1
relevance score. ``passed = score >= RELEVANCE_FLOOR``; anything below the
floor is dropped before it ever reaches the human shortlist.

Two brains sit behind the same ``Scorer`` protocol:

  * REAL: the GPT relay (OpenAI-compatible, ``settings.gpt_base_url``). If the
    candidate has a screenshot we send the image + the intent/inclusion/
    exclusion + anchor context and ask the model to grade the five dimensions
    as JSON. Text-only sources (help docs today) are graded from their
    extracted text.
  * MOCK: a deterministic keyword-overlap scorer (``score_from_text``). It is
    used only when ``settings.use_collection_mock`` is enabled, keeping offline
    runs and tests deterministic without disguising live relay failures.

The real path fails closed: transport/configuration failures produce a rejected,
explicitly labelled audit score and never become mock evidence.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from billiard.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.m3_collection.contracts import (
    RELEVANCE_FLOOR,
    Candidate,
    EvidenceType,
    RubricBreakdown,
    Score,
    SourceType,
)
from app.utils.robust_json import extract_json

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

# The production relay normally answers in 5-15 seconds. A short per-request
# ceiling prevents one degraded upstream call from consuming a full minute and
# exhausting the 12-minute Celery task budget across a large candidate set.
LIVE_GPT_TIMEOUT_SECONDS = 20
GPT_ERROR_PREFIX = "gpt-error:"

# Product-match gate. This is a competitor-scoped tool: a Notion cell must hold
# NOTION evidence, so an off-competitor doc that happens to show the same feature
# is worthless there. The weighted combine alone can't enforce this (product_match
# is only 0.20 of the total, so an off-competitor doc can still clear the floor on
# state/directness). So when we know the target product name, an OFFICIAL-source
# candidate whose product_match falls below this gate is hard-failed regardless of
# overall score. Only enforced when a product name is supplied (mock/offline tests
# pass none -> gate is inert, keeping them deterministic).
PRODUCT_MATCH_GATE = 0.5

# A product_match at/below this is the model stating the artifact is DEFINITELY a
# different product - it never mentions the target at all (not a "Notion vs Coda"
# comparison, which scores ~0.3-0.4). Such evidence is hard-failed for EVERY source
# type, including community/generic, closing the generic-bucket hole (its queries
# carry no competitor name, so off-product docs slip in).
PRODUCT_MATCH_ZERO = 0.05

# The 0.5 product-match gate HARD-FAILS these official source types - material that
# must belong to the competitor itself. Community/generic sources are third-party
# (forums, reviews, comparisons) and legitimately discuss the target product
# alongside others, so they clear the 0.5 gate and are judged on overall score -
# but they are STILL subject to the PRODUCT_MATCH_ZERO floor above.
_OFFICIAL_SOURCES = {
    SourceType.HELP_DOCS,
    SourceType.AGENTIC_SITE,
    SourceType.INTERACTIVE_DEMO,
}

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
    mock only in explicit mock mode; live relay failures are rejected and
    labelled for audit rather than converted into deterministic mock scores.
    """

    def __init__(self, *, request_timeout_seconds: int = LIVE_GPT_TIMEOUT_SECONDS) -> None:
        self.request_timeout_seconds = max(1, int(request_timeout_seconds))

    def score(
        self,
        candidate: Candidate,
        *,
        intent_definition: str,
        inclusion_criteria: str = "",
        exclusion_criteria: str = "",
        anchor_image_path: Optional[str] = None,
        product_name: str = "",
    ) -> Score:
        has_image = candidate.image_path is not None
        text = " ".join(
            part for part in (candidate.title, candidate.snippet, candidate.text_content) if part
        )

        use_mock = settings.use_collection_mock
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
            # ALL live candidates go to the GPT relay — text and images. A live
            # failure must remain visible and rejected; treating it as mock can
            # manufacture false-positive evidence and confidence.
            img = (candidate.image_path or anchor_image_path) if has_image else None
            model = settings.gpt_vision_model if img else settings.gpt_scorer_model
            scored_by = f"{GPT_ERROR_PREFIX}{model}"
            if not settings.gpt_api_key:
                rubric = RubricBreakdown()
                reasoning = "[gpt-error:MissingApiKey] live scoring failed closed"
                logger.warning(
                    "GPT relevance scoring unavailable for candidate %s: missing API key",
                    candidate.candidate_id,
                )
            else:
                try:
                    rubric, reasoning = self._score_with_gpt(
                        text=text,
                        intent_definition=intent_definition,
                        inclusion_criteria=inclusion_criteria,
                        exclusion_criteria=exclusion_criteria,
                        evidence_hint=candidate.evidence_type_hint,
                        image_path=img,
                        product_name=product_name,
                    )
                    scored_by = f"gpt:{model}"
                except SoftTimeLimitExceeded:
                    raise
                except Exception as exc:  # fail closed without killing the probe
                    error_type = type(exc).__name__
                    logger.warning(
                        "GPT relevance scoring failed closed for candidate %s: %s",
                        candidate.candidate_id,
                        error_type,
                    )
                    rubric = RubricBreakdown()
                    reasoning = f"[gpt-error:{error_type}] live scoring failed closed"

        overall = _combine(rubric)
        # Text-only sources are capped below what a screenshot could reach, so
        # the screenshot > text-description hierarchy stays honest — but a good
        # procedural doc can still clear the floor.
        if not has_image:
            overall = min(overall, TEXT_ONLY_CEILING)

        # Product-match gate (competitor-scoped tool): when we know the target
        # product, evidence about a DIFFERENT product is hard-failed even if the
        # feature matches - otherwise the 0.20-weighted product_match can't stop
        # an off-competitor doc from clearing the floor on the other dimensions.
        # The 0.5 gate applies only to OFFICIAL sources, which MUST be the
        # competitor's own material; third-party community/generic sources
        # legitimately read as comparisons and are judged on overall score, but
        # still hard-fail at PRODUCT_MATCH_ZERO. The numeric score is never
        # rewritten - only the verdict flips - so the audit trail stays intact.
        passed = overall >= RELEVANCE_FLOOR
        if product_name and rubric.product_match <= PRODUCT_MATCH_ZERO:
            passed = False
            if not reasoning.startswith("[off-product"):
                reasoning = (
                    f"[off-product gate: product_match={rubric.product_match:.2f}"
                    f"~0, not {product_name} at all] " + reasoning
                )
        elif (
            product_name
            and candidate.source_type in _OFFICIAL_SOURCES
            and rubric.product_match < PRODUCT_MATCH_GATE
        ):
            passed = False
            if not reasoning.startswith("[off-product"):
                reasoning = (
                    f"[off-product gate: product_match={rubric.product_match:.2f}"
                    f"<{PRODUCT_MATCH_GATE}, not {product_name}] " + reasoning
                )

        return Score(
            candidate_id=candidate.candidate_id,
            score=overall,
            passed=passed,
            # Map from the candidate hint — never upgrade claimed -> observed.
            evidence_type=candidate.evidence_type_hint,
            rubric=rubric,
            reasoning=reasoning,
            scored_by=scored_by,
        )

    # ------------------------------------------------------------------
    # Real GPT relay path (text + vision). Uses urllib only, so the module
    # stays importable offline and in CI with no extra SDK dependency.
    # ------------------------------------------------------------------
    def _score_with_gpt(
        self,
        *,
        text: str,
        intent_definition: str,
        inclusion_criteria: str,
        exclusion_criteria: str,
        evidence_hint,
        image_path: Optional[str] = None,
        product_name: str = "",
    ) -> tuple[RubricBreakdown, str]:
        """Scoring via the GPT relay (OpenAI-compatible). Handles BOTH modes:

        - image_path given → vision mode: the model SEES the screenshot, so it
          can judge evidence_directness as "observed" (real UI shown).
        - text only → judges from fetched page text and must NOT claim to have
          "seen" the UI (keeps evidence_directness honest).

        Same 5-dimension rubric + JSON contract as Claude, so all downstream
        (_combine, text ceiling, evidence drawer) is unchanged.
        """
        import base64
        import urllib.request

        has_image = bool(image_path)
        model = settings.gpt_vision_model if has_image else settings.gpt_scorer_model

        # Name the target product explicitly so product_match is a real check
        # ("is this Notion?") not a vague "is this a real product?" - the latter
        # gave off-competitor docs a false 1.0.
        product_line = (
            f"- product_match: 是否确实是「{product_name}」这个产品的证据"
            f"（他家产品即使功能相同也给 ≤0.2；无法判断给 0.4）\n"
            if product_name else
            "- product_match: 是否确实是目标产品（而非泛泛而谈或他家产品）\n"
        )
        rubric_spec = (
            "按 5 个维度打分（每项 0-1 小数）：\n"
            "- state_match: 是否命中目标场景/页面状态\n"
            f"{product_line}"
            "- version_recency: 内容新鲜度/是否当前版本（无法判断给 0.5）\n"
            "- evidence_directness: 直接展示操作/界面(高) vs 仅泛泛提及(低)\n"
            "- fidelity: 是否具体到可复现该场景（步骤/字段/交互/清晰度）\n\n"
            '只返回 JSON：{"state_match":0.0,"product_match":0.0,'
            '"version_recency":0.0,"evidence_directness":0.0,"fidelity":0.0,'
            '"reasoning":"一句话中文理由"}'
        )
        target_line = f"目标产品：{product_name}\n" if product_name else ""
        ctx = (
            f"{target_line}"
            f"目标场景意图：{intent_definition}\n"
            f"应包含：{inclusion_criteria or '（未指定）'}\n"
            f"应排除：{exclusion_criteria or '（未指定）'}\n"
            f"证据类型提示：{getattr(evidence_hint, 'value', evidence_hint)}\n\n"
        )

        if has_image:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            prompt = (
                "你是 UX 竞品研究的证据相关性评分器。看这张产品界面截图，判断它是否是"
                "目标场景的高质量证据（你能直接看到真实 UI）。\n\n" + ctx + rubric_spec
            )
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            ]
        else:
            prompt = (
                "你是 UX 竞品研究的证据相关性评分器。判断下面抓取到的网页正文，是否是"
                "目标场景的高质量、可复现证据。只依据文字描述判断——网页没有截图，"
                "所以不能认为你'看到了'真实 UI。\n\n" + ctx
                + f"网页正文（截断）：\n{text[:3500]}\n\n" + rubric_spec
            )
            content = prompt

        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
        }).encode()
        req = urllib.request.Request(
            f"{settings.gpt_base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.gpt_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.request_timeout_seconds) as resp:
            payload = json.load(resp)
        raw = payload["choices"][0]["message"]["content"]
        data = _extract_json(raw)
        rubric = RubricBreakdown(
            state_match=_clamp01(float(data.get("state_match", 0.0))),
            product_match=_clamp01(float(data.get("product_match", 0.0))),
            version_recency=_clamp01(float(data.get("version_recency", 0.5))),
            evidence_directness=_clamp01(float(data.get("evidence_directness", 0.0))),
            fidelity=_clamp01(float(data.get("fidelity", 0.0))),
        )
        return rubric, str(data.get("reasoning", ""))[:400]


def _extract_json(raw: str) -> dict:
    """Pull the first JSON object out of a model response, tolerant of fences
    and of unescaped inner quotes (common in Chinese reasoning text)."""
    return extract_json(raw)

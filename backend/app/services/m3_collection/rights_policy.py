"""Rights -> media disposition policy (the decision-critical seam).

Pinned by docs/collection-phase-spec-v2.md §6.4 and docs/theory-grounding.md.
Deterministic: the disposition is decided at capture time from rights_status,
never guessed after the fact. This governs what we may store/serve for an Asset:

    original       full media may be stored/served
    thumbnail_only only a downscaled thumbnail + attribution + deep link
    link_only      no media stored; link + attribution only

Rule of thumb (honest, conservative):
  self_captured_under_tos  -> original      (our own account, PII-masked upstream)
  third_party_official     -> thumbnail_only (help docs etc.; internal-original
                              would need a separate legal sign-off, so the stored
                              disposition stays thumbnail_only by default)
  embedded_third_party     -> thumbnail_only (Navattic/Storylane demos)
  copyrighted_marketing    -> link_only     (marketing video frames etc.)
  unknown                  -> link_only + needs_human review (blocked from display)
"""
from __future__ import annotations

from enum import StrEnum


class MediaDisposition(StrEnum):
    ORIGINAL = "original"
    THUMBNAIL_ONLY = "thumbnail_only"
    LINK_ONLY = "link_only"


# Known rights_status values (mirror EvidenceType provenance hints / adapters).
RIGHTS_SELF_CAPTURED = "self_captured_under_tos"
RIGHTS_THIRD_PARTY_OFFICIAL = "third_party_official"
RIGHTS_EMBEDDED_THIRD_PARTY = "embedded_third_party"
RIGHTS_COPYRIGHTED_MARKETING = "copyrighted_marketing"
RIGHTS_UNKNOWN = "unknown"


_DISPOSITION: dict[str, MediaDisposition] = {
    RIGHTS_SELF_CAPTURED: MediaDisposition.ORIGINAL,
    RIGHTS_THIRD_PARTY_OFFICIAL: MediaDisposition.THUMBNAIL_ONLY,
    RIGHTS_EMBEDDED_THIRD_PARTY: MediaDisposition.THUMBNAIL_ONLY,
    RIGHTS_COPYRIGHTED_MARKETING: MediaDisposition.LINK_ONLY,
    RIGHTS_UNKNOWN: MediaDisposition.LINK_ONLY,
}


def disposition_for(rights_status: str) -> MediaDisposition:
    """Deterministic media disposition for a rights_status.

    Any unrecognised value is treated as UNKNOWN -> link_only (fail safe:
    never over-expose media we can't account for).
    """
    return _DISPOSITION.get(rights_status, MediaDisposition.LINK_ONLY)


def needs_human_review(rights_status: str) -> bool:
    """True when rights are unaccounted for and display must be blocked until
    a human clears them. Only 'unknown' (or unrecognised) triggers this."""
    return rights_status not in _DISPOSITION or rights_status == RIGHTS_UNKNOWN

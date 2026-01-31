"""Tracks endorsement boundaries across pages for continuation detection.

IMPORTANT: Based on real document analysis, form numbers (like CA T3 53 02 15) are
often NOT extractable from markdown content - they're in footers/headers. Instead,
this tracker relies on:

1. Mid-sentence continuation (page starts lowercase/mid-phrase)
2. Alphabetic section sequence (A, B, C -> D, E, F)
3. Explicit continuation text ("CONTINUED ON", "CONTINUATION OF")
4. Endorsement context window (pages after endorsement header without new header)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models.page_analysis_models import PageSignals, PageType, SemanticRole
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Alphabetic sequence for section labels
ALPHA_SEQUENCE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def is_sequence_continuation(prev_labels: List[str], curr_labels: List[str]) -> Tuple[bool, str]:
    """Check if current page's section labels continue from previous page.

    Example: Page 5 ends with C, Page 6 starts with D -> continuation

    Args:
        prev_labels: Section labels from previous page
        curr_labels: Section labels from current page

    Returns:
        Tuple of (is_continuation, reason_string)
    """
    if not prev_labels or not curr_labels:
        return (False, "")

    prev_last = prev_labels[-1].upper() if prev_labels else None
    curr_first = curr_labels[0].upper() if curr_labels else None

    if prev_last and curr_first:
        # Check alphabetic sequence
        if prev_last in ALPHA_SEQUENCE and curr_first in ALPHA_SEQUENCE:
            prev_idx = ALPHA_SEQUENCE.index(prev_last)
            curr_idx = ALPHA_SEQUENCE.index(curr_first)
            if curr_idx == prev_idx + 1:
                return (True, f"Section sequence: {prev_last} -> {curr_first}")

        # Check numeric sequence
        if prev_last.isdigit() and curr_first.isdigit():
            if int(curr_first) == int(prev_last) + 1:
                return (True, f"Section sequence: {prev_last} -> {curr_first}")

    return (False, "")


@dataclass
class EndorsementContext:
    """Tracks the current endorsement context."""

    endorsement_id: str  # Unique ID (form number if available, else page-based)
    start_page: int
    policy_number: Optional[str] = None
    expected_pages: Optional[int] = None  # From "Page X of Y"
    last_section_labels: List[str] = field(default_factory=list)  # Section labels on last page
    pages_seen: List[int] = field(default_factory=list)

    def is_continuation_candidate(self, signals: PageSignals) -> Tuple[bool, float, str]:
        """Determine if a page is likely a continuation of this endorsement.

        PRIORITY ORDER (based on real data reliability):
        1. Mid-sentence start (0.85 confidence) - MOST RELIABLE
        2. Section sequence continuation (0.80 confidence)
        3. Explicit continuation text (0.90 confidence)
        4. Consecutive page + no new header (0.50 confidence)
        5. Same policy number (0.30 confidence) - WEAK signal

        Returns:
            Tuple of (is_continuation, confidence, reasoning)
        """
        page_num = signals.page_number
        confidence = 0.0
        reasons = []

        # NEGATIVE: New endorsement header = new endorsement, NOT continuation
        # UNLESS it's an explicit continuation form
        if signals.has_endorsement_header and not signals.explicit_continuation:
            return (False, 0.0, "New endorsement header detected - not a continuation")

        # 1. EXPLICIT CONTINUATION TEXT (HIGHEST PRIORITY)
        if signals.explicit_continuation:
            confidence += 0.90
            reasons.append(f"Explicit continuation: {signals.explicit_continuation}")

        # 2. MID-SENTENCE START (VERY HIGH PRIORITY - most reliable from real data)
        if signals.starts_mid_sentence:
            confidence += 0.85
            first_words = signals.first_line_text[:50] if signals.first_line_text else ""
            reasons.append(f"Mid-sentence start: '{first_words}...'")

        # 3. SECTION SEQUENCE CONTINUATION (HIGH PRIORITY)
        if self.last_section_labels and signals.section_labels:
            is_seq, seq_reason = is_sequence_continuation(
                self.last_section_labels, signals.section_labels
            )
            if is_seq:
                confidence += 0.80
                reasons.append(seq_reason)

        # 4. CONSECUTIVE PAGE + NO NEW HEADER (MEDIUM PRIORITY)
        if self.pages_seen and page_num == self.pages_seen[-1] + 1:
            confidence += 0.30
            reasons.append("Consecutive page, no new endorsement header")

        # 5. SAME POLICY NUMBER (WEAK SIGNAL - only additive)
        if signals.policy_number and self.policy_number:
            if signals.policy_number == self.policy_number:
                confidence += 0.15
                reasons.append(f"Same policy number: {self.policy_number}")

        # Threshold for continuation
        is_continuation = confidence >= 0.40
        return (is_continuation, min(confidence, 1.0), "; ".join(reasons) if reasons else "No continuation signals")


class EndorsementTracker:
    """Tracks endorsement context across pages for continuation detection.

    This tracker uses content-based signals instead of form numbers, which are
    unreliable in extracted markdown content.

    Usage:
        tracker = EndorsementTracker()
        for signals in page_signals_list:
            is_cont, ctx, conf, reason = tracker.check_continuation(signals)
            if is_cont:
                classification.is_continuation = True
                classification.parent_endorsement_id = ctx.endorsement_id
            elif signals.has_endorsement_header:
                tracker.start_endorsement(signals)
    """

    def __init__(self):
        """Initialize the endorsement tracker."""
        self.active_context: Optional[EndorsementContext] = None
        self.completed_endorsements: List[EndorsementContext] = []

    def reset(self):
        """Reset tracker state for new document."""
        if self.active_context:
            self.completed_endorsements.append(self.active_context)
        self.active_context = None
        self.completed_endorsements = []

    def start_endorsement(self, signals: PageSignals) -> EndorsementContext:
        """Start tracking a new endorsement.

        Args:
            signals: PageSignals for the endorsement start page

        Returns:
            The newly created EndorsementContext
        """
        # Close any active context
        if self.active_context:
            self.completed_endorsements.append(self.active_context)

        page_num = signals.page_number
        endorsement_id = signals.form_number or f"ENDORSEMENT_PAGE_{page_num}"

        self.active_context = EndorsementContext(
            endorsement_id=endorsement_id,
            start_page=page_num,
            policy_number=signals.policy_number,
            last_section_labels=signals.section_labels.copy() if signals.section_labels else [],
            pages_seen=[page_num],
        )

        LOGGER.debug(
            f"Started tracking endorsement {endorsement_id} at page {page_num}"
        )

        return self.active_context

    def check_continuation(
        self, signals: PageSignals
    ) -> Tuple[bool, Optional[EndorsementContext], float, str]:
        """Check if the current page is a continuation of an active endorsement.

        Args:
            signals: PageSignals for the current page

        Returns:
            Tuple of (is_continuation, context, confidence, reasoning)
        """
        # If no active context, can't be a continuation
        if not self.active_context:
            return (False, None, 0.0, "No active endorsement context")

        # Check continuation signals
        is_cont, conf, reason = self.active_context.is_continuation_candidate(signals)

        if is_cont:
            # Update context with this page's information
            self.active_context.pages_seen.append(signals.page_number)
            if signals.section_labels:
                self.active_context.last_section_labels = signals.section_labels.copy()
            # Update policy number if found
            if signals.policy_number and not self.active_context.policy_number:
                self.active_context.policy_number = signals.policy_number

            LOGGER.debug(
                f"Page {signals.page_number} is continuation of {self.active_context.endorsement_id}: {reason}"
            )
            return (True, self.active_context, conf, reason)

        return (False, None, conf, reason)

    def get_active_endorsement_id(self) -> Optional[str]:
        """Get the ID of the currently active endorsement."""
        return self.active_context.endorsement_id if self.active_context else None

    def get_endorsement_summary(self) -> dict:
        """Get summary of all tracked endorsements."""
        all_endorsements = self.completed_endorsements.copy()
        if self.active_context:
            all_endorsements.append(self.active_context)

        return {
            "total_endorsements": len(all_endorsements),
            "endorsements": [
                {
                    "id": e.endorsement_id,
                    "start_page": e.start_page,
                    "pages": e.pages_seen,
                    "page_count": len(e.pages_seen),
                }
                for e in all_endorsements
            ]
        }

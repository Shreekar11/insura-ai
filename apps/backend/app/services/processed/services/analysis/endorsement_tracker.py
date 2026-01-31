"""Tracks endorsement boundaries across pages for continuation detection.

SIGNAL PRIORITY ORDER (based on reliability):

1. FORM NUMBER MATCH (0.95 confidence) - MOST RELIABLE
   - When form numbers are available (from footer extraction), matching form numbers
     definitively link multi-page endorsements
   - Example: Pages 5-8 all have "CA T3 53 02 15" -> same endorsement

2. EXPLICIT CONTINUATION TEXT (0.90 confidence)
   - "CONTINUATION OF FORM IL T4 05" explicitly marks continuation

3. MID-SENTENCE START (0.85 confidence)
   - Page starts with lowercase letter -> continues previous page's sentence

4. SECTION SEQUENCE (0.80 confidence)
   - A, B, C -> D, E, F alphabetic continuation

5. CONSECUTIVE PAGE + NO NEW HEADER (0.30 confidence)
   - Weak signal, only additive

6. SAME POLICY NUMBER (0.15 confidence)
   - Very weak signal, only additive

NOTE: Form numbers can now be extracted via the FooterExtractor service which uses
Docling and pypdfium2 to read form numbers from PDF footers.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Alphabetic sequence for section labels
ALPHA_SEQUENCE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def is_sequence_continuation(prev_labels: List[str], curr_labels: List[str]) -> Tuple[bool, str]:
    """Check if current page's section labels continue from previous page.

    Supports both:
    - Strict sequence: B -> C (consecutive)
    - Alphabetic progression: B -> G (non-consecutive but progressing)

    Example: Page 5 ends with B, Page 7 starts with G -> continuation (progressing)

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
        # Check alphabetic sequence/progression
        if prev_last in ALPHA_SEQUENCE and curr_first in ALPHA_SEQUENCE:
            prev_idx = ALPHA_SEQUENCE.index(prev_last)
            curr_idx = ALPHA_SEQUENCE.index(curr_first)

            # Strict consecutive sequence (B -> C) - high confidence
            if curr_idx == prev_idx + 1:
                return (True, f"Section sequence: {prev_last} -> {curr_first}")

            # Alphabetic progression (B -> G) - medium confidence
            # Current label is later in alphabet than previous (progressing forward)
            # but not too far (max 10 letters gap to avoid false positives)
            if curr_idx > prev_idx and (curr_idx - prev_idx) <= 10:
                return (True, f"Section progression: {prev_last} -> {curr_first}")

        # Check numeric sequence
        if prev_last.isdigit() and curr_first.isdigit():
            prev_num = int(prev_last)
            curr_num = int(curr_first)
            if curr_num == prev_num + 1:
                return (True, f"Section sequence: {prev_last} -> {curr_first}")
            # Numeric progression
            if curr_num > prev_num and (curr_num - prev_num) <= 10:
                return (True, f"Section progression: {prev_last} -> {curr_first}")

    return (False, "")


@dataclass
class EndorsementContext:
    """Tracks the current endorsement context."""

    endorsement_id: str  # Unique ID (form number if available, else page-based)
    start_page: int
    policy_number: Optional[str] = None
    form_number: Optional[str] = None  # Form number from footer extraction
    expected_pages: Optional[int] = None  # From "Page X of Y"
    last_section_labels: List[str] = field(default_factory=list)  # Section labels on last page
    pages_seen: List[int] = field(default_factory=list)

    def is_continuation_candidate(self, signals: PageSignals) -> Tuple[bool, float, str]:
        """Determine if a page is likely a continuation of this endorsement.

        PRIORITY ORDER (based on reliability):
        1. FORM NUMBER MATCH (0.95 confidence) - MOST RELIABLE
        2. EXPLICIT CONTINUATION TEXT (0.90 confidence)
        3. MID-SENTENCE START (0.85 confidence)
        4. SECTION SEQUENCE (0.80 confidence)
        5. CONTENT CONTINUITY (0.70 confidence) - NEW
        6. CONSECUTIVE PAGE + NO STRONG HEADER (0.50 confidence) - BOOSTED
        7. SAME POLICY NUMBER (0.15 confidence) - WEAK signal

        Returns:
            Tuple of (is_continuation, confidence, reasoning)
        """
        page_num = signals.page_number
        confidence = 0.0
        reasons = []

        # Extract metadata signals
        metadata = signals.additional_metadata or {}
        has_strong_header = metadata.get("has_strong_header", False)
        content_continuity = metadata.get("content_continuity", False)

        # NEGATIVE: New endorsement header = new endorsement, NOT continuation
        # UNLESS it's an explicit continuation form OR same form number
        if signals.has_endorsement_header:
            # Check if form number matches - same form number = continuation
            if signals.form_number and self.form_number and signals.form_number == self.form_number:
                # Same form number overrides new header detection
                pass
            elif not signals.explicit_continuation:
                return (False, 0.0, "New endorsement header detected - not a continuation")

        # 1. FORM NUMBER MATCH (HIGHEST PRIORITY - most reliable)
        # When form numbers are available from footer extraction, matching form numbers
        # definitively link multi-page endorsements
        if signals.form_number and self.form_number:
            if signals.form_number == self.form_number:
                confidence += 0.95
                reasons.append(f"Same form number: {signals.form_number}")
                # Form number match is so strong that we can return early with high confidence
                return (True, min(confidence, 1.0), "; ".join(reasons))

        # 2. EXPLICIT CONTINUATION TEXT (VERY HIGH PRIORITY)
        if signals.explicit_continuation:
            confidence += 0.90
            reasons.append(f"Explicit continuation: {signals.explicit_continuation}")

        # 3. MID-SENTENCE START (HIGH PRIORITY - reliable from real data)
        if signals.starts_mid_sentence:
            confidence += 0.85
            first_words = signals.first_line_text[:50] if signals.first_line_text else ""
            reasons.append(f"Mid-sentence start: '{first_words}...'")

        # 4. SECTION SEQUENCE CONTINUATION (HIGH PRIORITY)
        if self.last_section_labels and signals.section_labels:
            is_seq, seq_reason = is_sequence_continuation(
                self.last_section_labels, signals.section_labels
            )
            if is_seq:
                confidence += 0.80
                reasons.append(seq_reason)

        # 5. CONTENT CONTINUITY (MEDIUM-HIGH PRIORITY) - NEW
        if content_continuity:
            confidence += 0.70
            reasons.append("Content continuity pattern detected")

        # 6. CONSECUTIVE PAGE + NO STRONG HEADER (MEDIUM PRIORITY) - BOOSTED
        # If this is a consecutive page and doesn't have a strong section header,
        # it's more likely to be continuation
        if self.pages_seen and page_num == self.pages_seen[-1] + 1:
            if not has_strong_header and not signals.has_endorsement_header:
                confidence += 0.50
                reasons.append("Consecutive page without strong header")
            else:
                confidence += 0.20
                reasons.append("Consecutive page")

        # 7. SAME POLICY NUMBER (WEAK SIGNAL - only additive)
        if signals.policy_number and self.policy_number:
            if signals.policy_number == self.policy_number:
                confidence += 0.15
                reasons.append(f"Same policy number: {self.policy_number}")

        # Threshold for continuation - lowered slightly to catch more continuations
        is_continuation = confidence >= 0.35
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
        # Use form number as the endorsement ID if available - this enables
        # form number-based continuation tracking
        endorsement_id = signals.form_number or f"ENDORSEMENT_PAGE_{page_num}"

        self.active_context = EndorsementContext(
            endorsement_id=endorsement_id,
            start_page=page_num,
            policy_number=signals.policy_number,
            form_number=signals.form_number,  # Store form number for continuation matching
            last_section_labels=signals.section_labels.copy() if signals.section_labels else [],
            pages_seen=[page_num],
        )

        LOGGER.debug(
            f"Started tracking endorsement {endorsement_id} at page {page_num}"
            f"{' (form: ' + signals.form_number + ')' if signals.form_number else ''}"
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
            # Update form number if found (improves future continuation detection)
            if signals.form_number and not self.active_context.form_number:
                self.active_context.form_number = signals.form_number
                # Also update the endorsement_id if it was generated from page number
                if self.active_context.endorsement_id.startswith("ENDORSEMENT_PAGE_"):
                    self.active_context.endorsement_id = signals.form_number
                    LOGGER.debug(
                        f"Updated endorsement ID to {signals.form_number} from page {signals.page_number}"
                    )

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

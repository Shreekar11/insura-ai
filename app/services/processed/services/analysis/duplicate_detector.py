"""Duplicate page detector using MinHash for similarity detection.

This module detects duplicate pages in insurance documents, which is common
for repeated ISO forms and boilerplate disclaimers.
"""

from typing import Dict, Optional, Tuple
from datasketch import MinHash

from app.models.page_analysis_models import PageSignals
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DuplicateDetector:
    """Detector for duplicate pages using MinHash similarity.
    
    Maintains a registry of seen pages and compares new pages against them
    using Jaccard similarity.
    """
    
    def __init__(self, similarity_threshold: float = 0.8, num_perm: int = 128):
        """Initialize duplicate detector.
        
        Args:
            similarity_threshold: Jaccard similarity threshold (0.0 to 1.0)
                Pages above this threshold are considered duplicates
            num_perm: Number of permutations for MinHash (higher = more accurate)
        """
        self.similarity_threshold = similarity_threshold
        self.num_perm = num_perm
        self.seen_pages: Dict[int, MinHash] = {}  # page_number -> MinHash
        
        logger.info(
            f"Initialized DuplicateDetector with threshold {similarity_threshold}, "
            f"num_perm {num_perm}"
        )
    
    def is_duplicate(
        self, 
        signals: PageSignals
    ) -> Tuple[bool, Optional[int]]:
        """Check if a page is a duplicate of a previously seen page.
        
        Args:
            signals: PageSignals for the page to check
            
        Returns:
            Tuple of (is_duplicate, duplicate_of_page_number)
            If not a duplicate, returns (False, None)
        """
        # Create MinHash for this page
        current_hash = self._create_minhash(signals)
        
        # Compare against all previously seen pages
        for seen_page_num, seen_hash in self.seen_pages.items():
            similarity = current_hash.jaccard(seen_hash)
            
            if similarity >= self.similarity_threshold:
                logger.info(
                    f"Page {signals.page_number} is duplicate of page {seen_page_num} "
                    f"(similarity: {similarity:.3f})",
                    extra={
                        "page_number": signals.page_number,
                        "duplicate_of": seen_page_num,
                        "similarity": similarity
                    }
                )
                return True, seen_page_num
        
        # Not a duplicate - add to registry
        self.seen_pages[signals.page_number] = current_hash
        
        logger.debug(
            f"Page {signals.page_number} is unique (checked against "
            f"{len(self.seen_pages)-1} previous pages)"
        )
        
        return False, None
    
    def _create_minhash(self, signals: PageSignals) -> MinHash:
        """Create MinHash from page signals.
        
        Args:
            signals: PageSignals to hash
            
        Returns:
            MinHash object
        """
        minhash = MinHash(num_perm=self.num_perm)
        
        # Hash each line from top_lines
        for line in signals.top_lines:
            # Normalize: lowercase, remove extra whitespace
            normalized = ' '.join(line.lower().split())
            
            # Split into words and hash each
            words = normalized.split()
            for word in words:
                if word:  # Skip empty strings
                    minhash.update(word.encode('utf-8'))
        
        return minhash
    
    def reset(self):
        """Reset the seen pages registry.
        
        Useful when starting analysis of a new document.
        """
        self.seen_pages.clear()
        logger.info("Reset duplicate detector registry")
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about duplicate detection.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "total_pages_seen": len(self.seen_pages),
            "similarity_threshold": self.similarity_threshold,
            "num_permutations": self.num_perm
        }

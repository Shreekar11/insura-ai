"""Data model for page-specific OCR results."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class PageData:
    """Represents OCR-extracted data from a single page.

    Attributes:
        page_number: Page number (1-indexed)
        text: Plain text content from the page
        markdown: Markdown-formatted content from the page (if available)
        metadata: Additional metadata about the page
        width_points: Page width in PDF points (1 point = 1/72 inch)
        height_points: Page height in PDF points
        rotation: Page rotation in degrees (0, 90, 180, 270)
    """

    page_number: int
    text: str
    markdown: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    width_points: Optional[float] = None
    height_points: Optional[float] = None
    rotation: int = 0
    
    def get_content(self, prefer_markdown: bool = True) -> str:
        """Get page content, preferring markdown if available.
        
        Args:
            prefer_markdown: Whether to prefer markdown over plain text
            
        Returns:
            str: Page content
        """
        if prefer_markdown and self.markdown:
            return self.markdown
        return self.text
    
    def __len__(self) -> int:
        """Return length of text content."""
        return len(self.get_content())
    
    def __str__(self) -> str:
        """Return string representation."""
        return f"PageData(page={self.page_number}, length={len(self)})"

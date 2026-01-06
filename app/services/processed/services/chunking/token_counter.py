"""Token counting utilities for chunking service.

This module provides utilities to count tokens in text chunks to ensure
they stay within LLM context limits.
"""

import re
from typing import Optional

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class TokenCounter:
    """Token counter for estimating token counts in text.
    
    Uses tiktoken for accurate token counting where possible,
    falling back to a heuristic-based approach if needed.
    """
    
    # Average characters per token (empirically derived for insurance docs)
    CHARS_PER_TOKEN = 4.0
    
    # Adjustment factor for insurance documents (more technical terms)
    INSURANCE_DOC_FACTOR = 1.1
    
    def __init__(self, model: str = "gpt-3.5-turbo"):
        """Initialize token counter.
        
        Args:
            model: Model name for token counting
        """
        self.model = model
        self.encoder = None
        try:
            import tiktoken
            try:
                self.encoder = tiktoken.encoding_for_model(model)
                LOGGER.debug(f"Initialized tiktoken encoder for model: {model}")
            except KeyError:
                self.encoder = tiktoken.get_encoding("cl100k_base")
                LOGGER.debug(f"Model {model} not found, using cl100k_base encoding")
        except ImportError:
            LOGGER.warning("tiktoken not installed, using heuristic token counting")
        
        LOGGER.debug(f"Initialized token counter for model: {model}")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text.
        
        Uses tiktoken if available, otherwise falls back to a heuristic approach.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            int: Token count
        """
        if not text:
            return 0
            
        if self.encoder:
            try:
                return len(self.encoder.encode(text))
            except Exception as e:
                LOGGER.warning(f"tiktoken encoding failed: {e}, falling back to heuristic")
        
        # Heuristic fallback (original logic)
        char_count = len(text)
        base_estimate = char_count / self.CHARS_PER_TOKEN
        
        word_count = len(text.split())
        word_based_estimate = word_count * 1.3
        
        estimate = (base_estimate + word_based_estimate) / 2
        estimate *= self.INSURANCE_DOC_FACTOR
        
        return int(estimate)
    
    def estimate_tokens_from_words(self, word_count: int) -> int:
        """Estimate tokens from word count.
        
        Args:
            word_count: Number of words
            
        Returns:
            int: Estimated token count
        """
        return int(word_count * 1.3 * self.INSURANCE_DOC_FACTOR)
    
    def can_fit_in_limit(self, text: str, limit: int) -> bool:
        """Check if text fits within token limit.
        
        Args:
            text: Text to check
            limit: Maximum token limit
            
        Returns:
            bool: True if text fits within limit
        """
        token_count = self.count_tokens(text)
        return token_count <= limit
    
    def split_by_token_limit(
        self, 
        text: str, 
        limit: int,
        overlap: int = 0
    ) -> list[str]:
        """Split text into chunks that fit within token limit.
        
        This is a simple line-based splitter that preserves paragraph boundaries.
        
        Args:
            text: Text to split
            limit: Maximum tokens per chunk
            overlap: Number of tokens to overlap between chunks
            
        Returns:
            list[str]: List of text chunks
        """
        if self.can_fit_in_limit(text, limit):
            return [text]
        
        chunks = []
        lines = text.split('\n')
        current_chunk = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self.count_tokens(line)
            
            # If single line exceeds limit, split it by sentences
            if line_tokens > limit:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Split long line by sentences
                sentences = re.split(r'([.!?]+\s+)', line)
                sentence_chunk = []
                sentence_tokens = 0
                
                for sentence in sentences:
                    sent_tokens = self.count_tokens(sentence)
                    if sentence_tokens + sent_tokens > limit and sentence_chunk:
                        chunks.append(''.join(sentence_chunk))
                        sentence_chunk = [sentence]
                        sentence_tokens = sent_tokens
                    else:
                        sentence_chunk.append(sentence)
                        sentence_tokens += sent_tokens
                
                if sentence_chunk:
                    chunks.append(''.join(sentence_chunk))
                continue
            
            # Check if adding this line exceeds limit
            if current_tokens + line_tokens > limit and current_chunk:
                chunks.append('\n'.join(current_chunk))
                
                # Handle overlap
                if overlap > 0 and current_chunk:
                    overlap_lines = []
                    overlap_tokens = 0
                    for prev_line in reversed(current_chunk):
                        prev_tokens = self.count_tokens(prev_line)
                        if overlap_tokens + prev_tokens <= overlap:
                            overlap_lines.insert(0, prev_line)
                            overlap_tokens += prev_tokens
                        else:
                            break
                    current_chunk = overlap_lines
                    current_tokens = overlap_tokens
                else:
                    current_chunk = []
                    current_tokens = 0
            
            current_chunk.append(line)
            current_tokens += line_tokens
        
        # Add remaining chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        LOGGER.debug(
            f"Split text into {len(chunks)} chunks",
            extra={"limit": limit, "overlap": overlap}
        )
        
        return chunks

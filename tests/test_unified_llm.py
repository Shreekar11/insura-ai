"""Test unified LLM client functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.unified_llm import UnifiedLLMClient, LLMProvider, create_llm_client
from app.utils.exceptions import APIClientError


@pytest.mark.asyncio
async def test_unified_llm_with_gemini():
    """Test unified LLM client with Gemini provider."""
    client = UnifiedLLMClient(
        provider="gemini",
        api_key="test_gemini_key",
        model="gemini-2.0-flash",
        timeout=60,
        max_retries=3
    )
    
    assert client.provider == LLMProvider.GEMINI
    assert client.fallback_client is None


@pytest.mark.asyncio
async def test_unified_llm_with_openrouter():
    """Test unified LLM client with OpenRouter provider."""
    client = UnifiedLLMClient(
        provider="openrouter",
        api_key="test_openrouter_key",
        model="google/gemini-2.0-flash-001",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        timeout=60,
        max_retries=3
    )
    
    assert client.provider == LLMProvider.OPENROUTER
    assert client.fallback_client is None


@pytest.mark.asyncio
async def test_unified_llm_with_fallback():
    """Test unified LLM client with fallback enabled."""
    client = UnifiedLLMClient(
        provider="openrouter",
        api_key="test_openrouter_key",
        model="google/gemini-2.0-flash-001",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        fallback_to_gemini=True,
        gemini_api_key="test_gemini_key",
        gemini_model="gemini-2.0-flash",
        timeout=60,
        max_retries=3
    )
    
    assert client.provider == LLMProvider.OPENROUTER
    assert client.fallback_client is not None


@pytest.mark.asyncio
async def test_unified_llm_generate_content_gemini():
    """Test content generation with Gemini provider."""
    with patch('app.core.unified_llm.GeminiClient') as mock_gemini:
        mock_instance = AsyncMock()
        mock_instance.generate_content = AsyncMock(return_value="Generated text")
        mock_gemini.return_value = mock_instance
        
        client = UnifiedLLMClient(
            provider="gemini",
            api_key="test_key",
            model="gemini-2.0-flash"
        )
        
        result = await client.generate_content(
            contents="Test prompt",
            system_instruction="Test instruction"
        )
        
        assert result == "Generated text"
        mock_instance.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_unified_llm_generate_content_openrouter():
    """Test content generation with OpenRouter provider."""
    with patch('app.core.unified_llm.OpenRouterClient') as mock_openrouter:
        mock_instance = AsyncMock()
        mock_instance.generate_content = AsyncMock(return_value="Generated text")
        mock_openrouter.return_value = mock_instance
        
        client = UnifiedLLMClient(
            provider="openrouter",
            api_key="test_key",
            model="google/gemini-2.0-flash-001",
            base_url="https://openrouter.ai/api/v1/chat/completions"
        )
        
        result = await client.generate_content(
            contents="Test prompt",
            system_instruction="Test instruction"
        )
        
        assert result == "Generated text"
        mock_instance.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_create_llm_client_factory():
    """Test factory function for creating unified LLM client."""
    client = create_llm_client(
        provider="gemini",
        api_key="test_key",
        model="gemini-2.0-flash"
    )
    
    assert isinstance(client, UnifiedLLMClient)
    assert client.provider == LLMProvider.GEMINI


@pytest.mark.asyncio
async def test_invalid_provider():
    """Test that invalid provider raises error."""
    with pytest.raises(ValueError):
        UnifiedLLMClient(
            provider="invalid_provider",
            api_key="test_key",
            model="test_model"
        )

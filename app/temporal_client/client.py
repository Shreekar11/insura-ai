"""Temporal client configuration and connection management."""

from temporalio.client import Client as TemporalClient

from app.config import settings

# Global Temporal client manager instance
_temporal_manager = TemporalClientManager()

class TemporalClientManager:
    """Manages Temporal client connection."""

    _client: TemporalClient | None = None

    async def get_client(self) -> TemporalClient:
        """Get or create Temporal client instance.

        Returns:
            TemporalClient: Connected Temporal client
        """
        if self._client is None:
            self._client = await TemporalClient.connect(
                f"{settings.temporal_host}:{settings.temporal_port}",
                namespace=settings.temporal_namespace,
            )
        return self._client

    async def close(self) -> None:
        """Close Temporal client connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


async def get_temporal_client() -> TemporalClient:
    """Get Temporal client instance.

    Returns:
        TemporalClient: Connected Temporal client
    """
    return await _temporal_manager.get_client()


async def close_temporal_client() -> None:
    """Close Temporal client connection."""
    await _temporal_manager.close()


# Convenience property for direct access
async def temporal_client() -> TemporalClient:
    """Convenience function to get Temporal client.

    Returns:
        TemporalClient: Connected Temporal client
    """
    return await get_temporal_client()


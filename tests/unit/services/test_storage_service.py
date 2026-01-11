import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile
from io import BytesIO
from app.services.storage_service import StorageService
from app.core.exceptions import AppError

@pytest.fixture
def storage_service():
    return StorageService()

@pytest.fixture
def mock_upload_file():
    content = b"test content"
    file = BytesIO(content)
    return MagicMock(spec=UploadFile, filename="test.pdf", content_type="application/pdf", read=MagicMock(return_value=content), seek=MagicMock())

@pytest.mark.asyncio
async def test_upload_file_success(storage_service, mock_upload_file):
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"Key": "documents/test.pdf"})
        
        result = await storage_service.upload_file(mock_upload_file, "documents", "test.pdf")
        
        assert result == {"Key": "documents/test.pdf"}
        mock_post.assert_called_once()
        mock_upload_file.read.assert_called_once()

@pytest.mark.asyncio
async def test_upload_file_failure(storage_service, mock_upload_file):
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
        
        with pytest.raises(AppError, match="Upload failed: Bad Request"):
            await storage_service.upload_file(mock_upload_file, "documents", "test.pdf")

@pytest.mark.asyncio
async def test_get_signed_url_success(storage_service):
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200, 
            json=lambda: {"signedURL": "/storage/v1/object/sign/documents/test.pdf?token=123"}
        )
        
        url = await storage_service.get_signed_url("documents", "test.pdf")
        
        assert "http" in url
        assert "documents/test.pdf?token=123" in url

@pytest.mark.asyncio
async def test_get_signed_url_failure(storage_service):
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500, text="Server Error")
        
        with pytest.raises(AppError, match="Signed URL generation failed: Server Error"):
            await storage_service.get_signed_url("documents", "test.pdf")

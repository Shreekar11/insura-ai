"""Storage service for handling Supabase storage operations."""

import httpx
from typing import Dict, Any, Optional
from fastapi import UploadFile
from app.core.config import settings
from app.utils.logging import get_logger
from app.core.exceptions import AppError

LOGGER = get_logger(__name__)

class StorageService:
    """Service for managing files in Supabase storage."""

    def __init__(self):
        self.url = settings.supabase_url
        self.service_role_key = settings.supabase_service_role_key
        self.base_api_url = f"{self.url}/storage/v1"
        self.headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    async def upload_file(
        self, 
        file: UploadFile, 
        bucket: str, 
        path: str
    ) -> Dict[str, Any]:
        """Upload a file to Supabase storage.

        Args:
            file: The file to upload.
            bucket: Target bucket name.
            path: Target path within the bucket.

        Returns:
            Dict containing the upload result.

        Raises:
            AppError: If the upload fails.
        """
        upload_url = f"{self.base_api_url}/object/{bucket}/{path}"
        
        try:
            content = await file.read()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    upload_url,
                    headers={**self.headers, "Content-Type": file.content_type},
                    content=content,
                    timeout=settings.http_timeout
                )
                
                if response.status_code != 200:
                    LOGGER.error(
                        f"Failed to upload file to Supabase: {response.text}",
                        extra={"bucket": bucket, "path": path, "status_code": response.status_code}
                    )
                    raise AppError(f"Upload failed: {response.text}")
                
                return response.json()
        except Exception as e:
            LOGGER.error(f"Error uploading file to Supabase: {str(e)}", exc_info=True)
            raise AppError(f"Storage upload error: {str(e)}", original_error=e)
        finally:
            await file.seek(0)  # Reset file pointer for future use

    async def get_signed_url(
        self, 
        bucket: str, 
        path: str, 
        expires_in: int = 3600
    ) -> Dict[str, Any]:
        """Generate a signed URL and return public URL of the document

        Args:
            bucket: Bucket name.
            path: Object path.
            expires_in: Expiration time in seconds.

        Returns:
            The public URL and signed URL.

        Raises:
            AppError: If URL generation fails.
        """
        url = f"{self.base_api_url}/object/sign/{bucket}/{path}"
        public_url = f"{self.base_api_url}/object/{bucket}/{path}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json={"expiresIn": expires_in},
                    timeout=settings.http_timeout
                )
                
                if response.status_code != 200:
                    LOGGER.error(
                        f"Failed to generate signed URL: {response.text}",
                        extra={"bucket": bucket, "path": path, "status_code": response.status_code}
                    )
                    raise AppError(f"Signed URL generation failed: {response.text}")
                
                data = response.json()
                signed_path = data.get("signedURL")
                if not signed_path:
                    raise AppError("Supabase response did not contain signedURL")
                
                # Supabase returns a relative path like /storage/v1/object/sign/documents/file.pdf?token=...
                # We need to prepend the full Supabase URL if it's not absolute
                if signed_path.startswith("/"):
                    return {
                        "signed_url": f"{self.url}{signed_path}",
                        "public_url": public_url
                    }
                return {
                    "signed_url": signed_path,
                    "public_url": public_url
                }
                
        except Exception as e:
            LOGGER.error(f"Error generating signed URL: {str(e)}", exc_info=True)
            raise AppError(f"Signed URL error: {str(e)}", original_error=e)

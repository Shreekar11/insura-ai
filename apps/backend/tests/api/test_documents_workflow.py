import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import status
from app.main import app
from app.api.v1.endpoints.documents import get_document_service, get_user_service
from app.services.document_service import DocumentService
from app.schemas.auth import JWTClaims

@pytest.fixture
def mock_document_service():
    service = AsyncMock(spec=DocumentService)
    return service

@pytest.fixture
def mock_user_service():
    service = AsyncMock()
    user = MagicMock()
    user.id = uuid4()
    service.get_or_create_user_from_jwt.return_value = user
    return service

def test_list_documents_with_workflow_id(test_client, mock_document_service, mock_user_service):
    # Setup
    app.dependency_overrides[get_document_service] = lambda: mock_document_service
    app.dependency_overrides[get_user_service] = lambda: mock_user_service
    
    workflow_id = uuid4()
    mock_response = {
        "total": 1,
        "documents": [
            {
                "id": str(uuid4()),
                "status": "processed",
                "file_path": "path/to/doc.pdf",
                "document_name": "test.pdf",
                "page_count": 5,
                "created_at": "2023-01-01T00:00:00Z"
            }
        ]
    }
    mock_document_service.list_documents.return_value = mock_response
    
    # Mock JWT verification
    with patch("app.core.jwt.JWTVerifier.verify_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = JWTClaims(
            sub=str(uuid4()),
            email="test@example.com",
            role="user",
            exp=1234567890,
            iat=1234567890,
            iss="supabase",
        )
        
        response = test_client.get(
            f"/api/v1/documents/?workflow_id={workflow_id}",
            headers={"Authorization": "Bearer fake_token"}
        )
    
        # Verify
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["total"] == 1
        
        # Verify service call
        mock_document_service.list_documents.assert_called_once()
        _, kwargs = mock_document_service.list_documents.call_args
        assert kwargs['workflow_id'] == workflow_id
    data = response.json()["data"]
    assert data["total"] == 1
    
    # Verify service call
    mock_document_service.list_documents.assert_called_once()
    _, kwargs = mock_document_service.list_documents.call_args
    assert kwargs['workflow_id'] == workflow_id

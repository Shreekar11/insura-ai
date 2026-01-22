"""JWT Authentication Middleware for FastAPI.

This middleware verifies the JWT access token in the Authorization header
using Supabase JWT keys and attaches the user information to the request state.
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import jwt

from app.core.jwt import jwt_verifier
from app.core.jwks import jwks_service
from app.schemas.auth import CurrentUser
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Paths that don't require authentication
EXCLUDED_PATHS = {
    "/health",
    "/health/",
    "/docs",
    "/docs/",
    "/openapi.json",
    "/openapi.json/",
    "/",
}

class JWTAuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for JWT authentication.
    
    Verifies Bearer token in 'Authorization' header and populates request.state.user.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)
            
        # Skip authentication for excluded paths
        if request.url.path in EXCLUDED_PATHS or request.url.path.startswith("/health"):
            return await call_next(request)
            
        auth_header = request.headers.get("Authorization")
        
        if not auth_header:
            LOGGER.warning(f"Missing Authorization header for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authorization header missing"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not auth_header.startswith("Bearer "):
            LOGGER.warning(f"Invalid Authorization header format for {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication scheme. Use Bearer token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        token = auth_header.split(" ")[1]
        
        try:
            # Verify the token
            claims = await jwt_verifier.verify_token(token)
            
            # Attach user to request state
            request.state.user = CurrentUser(
                id=claims.sub,
                email=claims.email,
                role=claims.role or "user",
                app_metadata=claims.app_metadata,
                user_metadata=claims.user_metadata,
            )
            
            LOGGER.debug(f"Authenticated user {claims.sub} via middleware")
            
            # Continue to the next handler
            response = await call_next(request)
            return response
            
        except jwt.InvalidTokenError as e:
            LOGGER.warning(f"Invalid token for {request.url.path}: {e}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            LOGGER.error(f"Unexpected error in JWT middleware: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Authentication internal error"},
            )

"""Authentication dependencies for FastAPI routes.

This module provides FastAPI dependency injection functions for
Supabase JWT token verification and user authentication.
"""

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.jwt import jwt_verifier, JWTClaims
from app.schemas.auth import CurrentUser
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> CurrentUser:
    """Get the current authenticated user from JWT token.

    This dependency:
    - Extracts Bearer token from Authorization header
    - Verifies JWT signature and claims
    - Returns CurrentUser object with user information

    Args:
        credentials: HTTP Authorization credentials (automatically injected)

    Returns:
        CurrentUser: Authenticated user information

    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if not credentials:
        LOGGER.warning("No authorization credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Verify and decode the JWT token
        claims = await jwt_verifier.verify_token(token)

        # Convert JWT claims to CurrentUser object
        user = CurrentUser(
            id=claims.sub,
            email=claims.email,
            role=claims.role or "user",
            app_metadata=claims.app_metadata,
            user_metadata=claims.user_metadata,
        )

        LOGGER.debug(f"Authenticated user: {user.id} ({user.email})")
        return user

    except jwt.InvalidTokenError as e:
        LOGGER.warning(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        LOGGER.error(f"Unexpected authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        ) from e


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[CurrentUser]:
    """Get the current user if authenticated, None otherwise.

    This dependency works like get_current_user but doesn't raise
    exceptions for missing or invalid tokens. Useful for routes
    that work with both authenticated and anonymous users.

    Args:
        credentials: HTTP Authorization credentials (automatically injected)

    Returns:
        CurrentUser or None: User info if authenticated, None if not
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        # Return None instead of raising exception
        return None


async def get_current_user_or_401(
    user: Optional[CurrentUser] = Depends(get_current_user_optional)
) -> CurrentUser:
    """Get current user or raise 401 if not authenticated.

    Alternative to get_current_user that uses the optional dependency
    but still requires authentication. Useful for more complex auth logic.

    Args:
        user: Current user from optional dependency

    Returns:
        CurrentUser: Authenticated user information

    Raises:
        HTTPException: If user is not authenticated
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(required_role: str):
    """Create a dependency that requires a specific user role.

    Args:
        required_role: The role required for access

    Returns:
        Dependency function that checks user role

    Example:
        admin_only = require_role("admin")

        @app.get("/admin")
        async def admin_route(user: CurrentUser = Depends(admin_only)):
            return {"message": "Admin access granted"}
    """
    async def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role != required_role:
            LOGGER.warning(f"Access denied for user {user.id}: insufficient role '{user.role}', required '{required_role}'")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}",
            )
        return user

    return role_checker


def require_any_role(*required_roles: str):
    """Create a dependency that requires any of the specified roles.

    Args:
        required_roles: Roles that are allowed access

    Returns:
        Dependency function that checks if user has any required role

    Example:
        editor_or_admin = require_any_role("editor", "admin")

        @app.get("/edit")
        async def edit_route(user: CurrentUser = Depends(editor_or_admin)):
            return {"message": "Edit access granted"}
    """
    async def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in required_roles:
            LOGGER.warning(f"Access denied for user {user.id}: role '{user.role}' not in allowed roles {required_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
            )
        return user

    return role_checker


# Pre-defined role dependencies for common use cases
require_admin = require_role("admin")
require_moderator = require_any_role("moderator", "admin")
require_user = require_any_role("user", "moderator", "admin")

"""Authentication schemas for Supabase JWT tokens.

This module defines Pydantic models for user authentication,
JWT claims, and authentication responses.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr


class UserBase(BaseModel):
    """Base user model with common fields."""

    supabase_user_id: str = Field(..., description="Supabase user ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User's full name")


class UserCreate(UserBase):
    """User creation model."""

    pass


class UserUpdate(BaseModel):
    """User update model with optional fields."""

    email: Optional[EmailStr] = Field(None, description="User email address")
    full_name: Optional[str] = Field(None, description="User's full name")


class UserResponse(UserBase):
    """User response model with database fields."""

    id: UUID = Field(..., description="Internal user ID")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class JWTClaims(BaseModel):
    """JWT claims extracted from Supabase access token."""

    sub: str = Field(..., description="Subject (user ID)")
    email: EmailStr = Field(..., description="User email")
    role: str = Field(default="authenticated", description="User role")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    iss: str = Field(..., description="Token issuer")

    # Optional Supabase-specific claims
    aud: Optional[str] = Field(None, description="Audience")
    app_metadata: Optional[Dict[str, Any]] = Field(None, description="Application metadata")
    user_metadata: Optional[Dict[str, Any]] = Field(None, description="User metadata")
    session_id: Optional[str] = Field(None, description="Session ID")


class CurrentUser(BaseModel):
    """Current authenticated user information."""

    id: str = Field(..., description="Supabase user ID")
    email: EmailStr = Field(..., description="User email")
    role: str = Field(default="user", description="User role")

    # Optional user metadata
    full_name: Optional[str] = Field(None, description="User's full name")
    app_metadata: Optional[Dict[str, Any]] = Field(None, description="Application metadata")
    user_metadata: Optional[Dict[str, Any]] = Field(None, description="User metadata")


class TokenResponse(BaseModel):
    """Token response from Supabase authentication."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: str = Field(..., description="Refresh token")
    user: Dict[str, Any] = Field(..., description="User information")


class AuthError(BaseModel):
    """Authentication error response."""

    error: str = Field(..., description="Error type")
    error_description: str = Field(..., description="Error description")


class UserProfile(BaseModel):
    """User profile information for API responses."""

    id: str = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="User's full name")
    role: str = Field(default="user", description="User role")
    created_at: datetime = Field(..., description="Account creation date")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")


__all__ = [
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "JWTClaims",
    "CurrentUser",
    "TokenResponse",
    "AuthError",
    "UserProfile",
]

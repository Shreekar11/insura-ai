"""JWT verification utilities for Supabase authentication.

This module provides JWT decoding and verification functionality
using Supabase's JWKS keys and PyJWT library.
"""

import time
from typing import Dict, Any, Optional

import jwt
from pydantic import BaseModel

from app.core.config import settings
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class JWTClaims(BaseModel):
    """Decoded JWT claims from Supabase."""

    sub: str  # User ID
    email: str
    role: str = "authenticated"
    exp: int  # Expiry timestamp
    iat: int  # Issued at timestamp
    iss: str  # Issuer
    aud: str = ""  # Audience (optional)

    # Additional Supabase-specific claims
    app_metadata: Optional[Dict[str, Any]] = None
    user_metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class JWTVerifier:
    """JWT verifier for Supabase access tokens.

    This class handles:
    - JWT decoding with signature verification
    - Claims validation (exp, iss, etc.)
    - Key rotation support via JWKS
    """

    def __init__(self, supabase_url: str):
        """Initialize JWT verifier.

        Args:
            supabase_url: Supabase project URL for issuer validation
        """
        self.supabase_url = supabase_url.rstrip("/")
        self.expected_issuer = f"{self.supabase_url}/auth/v1"

        LOGGER.info(f"JWT verifier initialized for issuer: {self.expected_issuer}")

    async def verify_token(self, token: str) -> JWTClaims:
        """Verify and decode a Supabase JWT token.

        Args:
            token: JWT access token from Authorization header

        Returns:
            Decoded and validated JWT claims

        Raises:
            jwt.InvalidTokenError: If token is invalid or expired
            ValueError: If token format is incorrect
            RuntimeError: If JWKS keys cannot be fetched
        """
        try:
            # Decode header to get key ID without verification
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            if not kid:
                raise ValueError("JWT header missing 'kid' (key ID)")

            # Get the signing key
            jwk_key = await jwks_service.get_key(kid)
            if not jwk_key:
                raise jwt.InvalidTokenError(f"No matching key found for kid: {kid}")

            # Convert JWK to PEM format for PyJWT
            public_key = self._jwk_to_pem(jwk_key)

            # Decode and verify the token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=None,  # Supabase tokens don't use audience
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "require": ["sub", "email", "exp", "iat", "iss"]
                }
            )

            # Additional issuer validation
            if payload.get("iss") != self.expected_issuer:
                raise jwt.InvalidIssuerError(f"Invalid issuer: {payload.get('iss')}")

            # Convert to Pydantic model for type safety
            claims = JWTClaims(**payload)

            LOGGER.debug(f"Successfully verified token for user: {claims.sub}")
            return claims

        except jwt.ExpiredSignatureError as e:
            LOGGER.warning(f"Token expired: {e}")
            raise jwt.InvalidTokenError("Token has expired") from e
        except jwt.InvalidIssuerError as e:
            LOGGER.warning(f"Invalid issuer: {e}")
            raise jwt.InvalidTokenError("Invalid token issuer") from e
        except jwt.InvalidSignatureError as e:
            LOGGER.warning(f"Invalid signature: {e}")
            raise jwt.InvalidTokenError("Invalid token signature") from e
        except jwt.InvalidTokenError as e:
            LOGGER.warning(f"Invalid token: {e}")
            raise
        except Exception as e:
            LOGGER.error(f"Unexpected error during token verification: {e}")
            raise jwt.InvalidTokenError("Token verification failed") from e

    def _jwk_to_pem(self, jwk_key) -> str:
        """Convert JWK RSA key to PEM format for PyJWT.

        Args:
            jwk_key: JWK key object

        Returns:
            PEM-encoded public key string

        Raises:
            ValueError: If key format is unsupported
        """
        if jwk_key.kty != "RSA":
            raise ValueError(f"Unsupported key type: {jwk_key.kty}")

        try:
            # Import cryptography components
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend

            # Decode base64url components
            import base64

            def base64url_decode(input_str: str) -> bytes:
                """Decode base64url string to bytes."""
                # Add padding if needed
                padding = 4 - (len(input_str) % 4)
                if padding != 4:
                    input_str += "=" * padding

                return base64.urlsafe_b64decode(input_str)

            # Extract RSA components
            n_bytes = base64url_decode(jwk_key.n)
            e_bytes = base64url_decode(jwk_key.e)

            # Convert to integers
            n = int.from_bytes(n_bytes, byteorder="big")
            e = int.from_bytes(e_bytes, byteorder="big")

            # Create RSA public key
            public_numbers = rsa.RSAPublicNumbers(e, n)
            public_key = public_numbers.public_key(default_backend())

            # Convert to PEM format
            pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            return pem.decode("utf-8")

        except Exception as e:
            raise ValueError(f"Failed to convert JWK to PEM: {e}") from e

    def is_token_expired(self, claims: JWTClaims) -> bool:
        """Check if token claims indicate expiration.

        Args:
            claims: Decoded JWT claims

        Returns:
            True if token is expired
        """
        current_time = int(time.time())
        return claims.exp < current_time


# Global JWT verifier instance
jwt_verifier = JWTVerifier(supabase_url=settings.supabase_url)

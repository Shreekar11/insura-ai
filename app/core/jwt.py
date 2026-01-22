"""JWT verification utilities for Supabase authentication.

This module provides JWT decoding and verification functionality
using Supabase's JWKS keys and PyJWT library.
"""

import time
from typing import Dict, Any, Optional

import jwt
from pydantic import BaseModel

from app.core.config import settings
from app.core.jwks import jwks_service
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

    def __init__(self, supabase_url: str, jwt_secret: str = ""):
        """Initialize JWT verifier.

        Args:
            supabase_url: Supabase project URL for issuer validation
            jwt_secret: Supabase JWT secret for HS256 verification
        """
        self.supabase_url = supabase_url.rstrip("/")
        self.expected_issuer = f"{self.supabase_url}/auth/v1"
        self.jwt_secret = jwt_secret

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
            # Decode header to get algorithm and key ID
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            kid = header.get("kid")

            key = None
            algorithms = []

            # Handle HS256 (Shared Secret) - Default for Supabase Auth
            if alg == "HS256":
                if not self.jwt_secret:
                    raise ValueError("HS256 token received but SUPABASE_JWT_SECRET is not configured")
                key = self.jwt_secret
                algorithms = ["HS256"]

            # Handle RS256/ES256 (Asymmetric Keys)
            elif alg in ["RS256", "ES256"]:
                if not kid:
                    raise ValueError("JWT header missing 'kid' (key ID)")

                # Get the signing key from JWKS
                jwk_key = await jwks_service.get_key(kid)
                if not jwk_key:
                    # This handles edge cases where header might be misleading or user wants fallback
                    if self.jwt_secret:
                         LOGGER.warning(f"Key {kid} not found in JWKS, attempting fallback to HS256 verification")
                         try:
                             return self._verify_with_secret(token)
                         except Exception:
                             pass # Fallback failed, raise original error
                    
                    raise jwt.InvalidTokenError(f"No matching key found for kid: {kid}")

                # Convert JWK to PEM
                key = self._jwk_to_pem(jwk_key)
                algorithms = [alg]
            
            else:
                raise jwt.InvalidTokenError(f"Unsupported algorithm: {alg}")

            # Decode and verify the token
            payload = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience="authenticated",
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

    def _verify_with_secret(self, token: str) -> JWTClaims:
        """Helper to verify token with shared secret."""
        payload = jwt.decode(
            token,
            self.jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={
                "verify_exp": True, 
                "verify_iat": True,
                "verify_iss": True,
                "require": ["sub", "email", "exp", "iat", "iss"]
            }
        )
        if payload.get("iss") != self.expected_issuer:
            raise jwt.InvalidIssuerError(f"Invalid issuer: {payload.get('iss')}")
        return JWTClaims(**payload)

    def _jwk_to_pem(self, jwk_key) -> str:
        """Convert JWK key to PEM format for PyJWT.

        Args:
            jwk_key: JWK key object

        Returns:
            PEM-encoded public key string

        Raises:
            ValueError: If key format is unsupported
        """
        if jwk_key.kty not in ["RSA", "EC"]:
            raise ValueError(f"Unsupported key type: {jwk_key.kty}")

        try:
            # Import cryptography components
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa, ec
            from cryptography.hazmat.backends import default_backend

            # Decode base64url components
            import base64

            def base64url_decode(input_str: str) -> bytes:
                """Decode base64url string to bytes."""
                if not input_str:
                    return b""
                # Add padding if needed
                padding = 4 - (len(input_str) % 4)
                if padding != 4:
                    input_str += "=" * padding

                return base64.urlsafe_b64decode(input_str)

            if jwk_key.kty == "RSA":
                # Extract RSA components
                n_bytes = base64url_decode(jwk_key.n)
                e_bytes = base64url_decode(jwk_key.e)

                # Convert to integers
                n = int.from_bytes(n_bytes, byteorder="big")
                e = int.from_bytes(e_bytes, byteorder="big")

                # Create RSA public key
                public_numbers = rsa.RSAPublicNumbers(e, n)
                public_key = public_numbers.public_key(default_backend())
            
            elif jwk_key.kty == "EC":
                # Extract EC components
                x_bytes = base64url_decode(jwk_key.x)
                y_bytes = base64url_decode(jwk_key.y)
                
                # Determine curve
                if jwk_key.crv == "P-256":
                    curve = ec.SECP256R1()
                elif jwk_key.crv == "P-384":
                    curve = ec.SECP384R1()
                elif jwk_key.crv == "P-521":
                     curve = ec.SECP521R1()
                else:
                    raise ValueError(f"Unsupported curve: {jwk_key.crv}")

                # Create EC public key
                public_numbers = ec.EllipticCurvePublicNumbers(
                    x=int.from_bytes(x_bytes, byteorder="big"),
                    y=int.from_bytes(y_bytes, byteorder="big"),
                    curve=curve
                )
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
jwt_verifier = JWTVerifier(
    supabase_url=settings.supabase_url,
    jwt_secret=settings.supabase_jwt_secret
)

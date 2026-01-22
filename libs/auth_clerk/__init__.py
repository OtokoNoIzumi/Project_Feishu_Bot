"""
Clerk Authentication Library.

Provides JWT verification for Clerk-authenticated users.
"""

from .clerk_jwt_auth import ClerkJWTAuth, ClerkJWTConfig

__all__ = ["ClerkJWTAuth", "ClerkJWTConfig"]

from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth
from typing import Optional, List, Callable
from functools import wraps
from models.users import UserRole, TokenPayload
from config.firebase import db
import os

security = HTTPBearer(auto_error=False)

# Development mode flag
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


class AuthError(HTTPException):
    """Custom authentication error."""
    def __init__(self, detail: str, status_code: int = 401):
        super().__init__(status_code=status_code, detail=detail)


async def verify_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> TokenPayload:
    """
    Verifies Firebase JWT and returns user claims.
    Extracts role from custom claims or Firestore user document.
    
    In DEV_MODE, authentication is bypassed with a test user.
    """
    # Development mode bypass
    if DEV_MODE:
        return TokenPayload(
            uid="dev-user-123",
            email="dev@example.com",
            name="Development User",
            role=UserRole.ADMIN,  # Grant admin access in dev mode
            email_verified=True
        )
    
    if not credentials:
        raise AuthError("Missing authorization header")
    
    try:
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(credentials.credentials)
        
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
        name = decoded_token.get("name", "")
        email_verified = decoded_token.get("email_verified", False)
        
        # Get role from custom claims first
        role_str = decoded_token.get("role", None)
        
        # If no custom claim, check Firestore users collection
        if not role_str:
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                role_str = user_data.get("role", "farmer")
            else:
                role_str = "farmer"  # Default role
        
        # Convert to enum
        try:
            role = UserRole(role_str.lower())
        except ValueError:
            role = UserRole.FARMER
        
        return TokenPayload(
            uid=uid,
            email=email,
            name=name,
            role=role,
            email_verified=email_verified,
            exp=decoded_token.get("exp")
        )
        
    except auth.ExpiredIdTokenError:
        raise AuthError("Token has expired")
    except auth.RevokedIdTokenError:
        raise AuthError("Token has been revoked")
    except auth.InvalidIdTokenError as e:
        raise AuthError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise AuthError(f"Authentication failed: {str(e)}")


async def verify_token_optional(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> Optional[TokenPayload]:
    """
    Optionally verifies token - returns None if no token provided.
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None
    
    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
        return TokenPayload(
            uid=decoded_token.get("uid"),
            email=decoded_token.get("email"),
            name=decoded_token.get("name", ""),
            role=UserRole(decoded_token.get("role", "farmer").lower()),
            email_verified=decoded_token.get("email_verified", False)
        )
    except Exception:
        return None


def require_roles(allowed_roles: List[UserRole]):
    """
    Dependency factory that requires specific roles.
    Usage: Depends(require_roles([UserRole.LENDER, UserRole.ADMIN]))
    """
    async def role_checker(user: TokenPayload = Depends(verify_token)) -> TokenPayload:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}"
            )
        return user
    return role_checker


def require_farmer():
    """Dependency that requires farmer role."""
    return require_roles([UserRole.FARMER, UserRole.ADMIN])


def require_lender():
    """Dependency that requires lender role."""
    return require_roles([UserRole.LENDER, UserRole.ADMIN])


def require_admin():
    """Dependency that requires admin role."""
    return require_roles([UserRole.ADMIN])


async def get_current_user_id(user: TokenPayload = Depends(verify_token)) -> str:
    """Returns just the user ID from the token."""
    return user.uid


def check_resource_ownership(resource_user_id: str, current_user: TokenPayload) -> bool:
    """
    Check if user owns the resource or is admin.
    Returns True if user has access, False otherwise.
    """
    if current_user.role == UserRole.ADMIN:
        return True
    return resource_user_id == current_user.uid


async def set_user_role(uid: str, role: UserRole) -> bool:
    """
    Set custom claims for a user's role.
    Should be called by admin endpoints.
    """
    try:
        auth.set_custom_user_claims(uid, {"role": role.value})
        # Also update Firestore
        db.collection("users").document(uid).set(
            {"role": role.value},
            merge=True
        )
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set role: {str(e)}")
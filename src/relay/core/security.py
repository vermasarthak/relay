import bcrypt
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from jose import jwt, JWTError
from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from relay.core.config import settings
from relay.db.session import get_db
from relay.models.entities import User, Membership, Tenant

security = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

def create_session_token(user_id: str, email: str, tenant_ids: List[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.session_expire_hours)
    to_encode = {
        "sub": user_id,
        "email": email,
        "tenants": tenant_ids,
        "exp": expire
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def decode_session_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

def compute_args_hash(arguments: dict) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

class AuthenticatedContext:
    def __init__(self, user: User, tenant: Tenant, role: str):
        self.user = user
        self.tenant = tenant
        self.role = role

def get_current_user_and_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db)
) -> AuthenticatedContext:
    token = None
    
    # Check Bearer token first
    if credentials:
        token = credentials.credentials
    else:
        # Fall back to secure cookie
        token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(status_code=401, detail="Authentication credentials required")

    payload = decode_session_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session token payload")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account not found or inactive")

    # Determine requested tenant from header or default to user's first tenant
    requested_tenant_id = request.headers.get("x-tenant-id") or request.query_params.get("tenant_id")
    
    user_memberships = db.query(Membership).filter(Membership.user_id == user.id).all()
    if not user_memberships:
        raise HTTPException(status_code=403, detail="User has no tenant memberships")

    matched_membership = None
    if requested_tenant_id:
        for m in user_memberships:
            if m.tenant_id == requested_tenant_id:
                matched_membership = m
                break
        if not matched_membership:
            raise HTTPException(
                status_code=403, 
                detail=f"Access denied: User is not authorized for tenant '{requested_tenant_id}'"
            )
    else:
        matched_membership = user_memberships[0]

    tenant = db.query(Tenant).filter(Tenant.id == matched_membership.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return AuthenticatedContext(user=user, tenant=tenant, role=matched_membership.role)

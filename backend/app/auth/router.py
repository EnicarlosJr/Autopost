from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.deps import require_user
from app.core.ratelimit import login_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["authentication"])

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    key = f"{request.client.host if request.client else '?'}|{email}"
    wait = login_limiter.retry_after(key)
    if wait:
        raise HTTPException(429, f"Muitas tentativas. Tente novamente em {max(1, wait // 60)} min.", headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.email == email)) if "@" in email else None
    if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
        login_limiter.fail(key)
        raise HTTPException(401, "E-mail ou senha incorretos")
    login_limiter.reset(key)
    return {"access_token": create_access_token(user.email)}

@router.get("/me")
def current_user(user: User = Depends(require_user)):
    return {"authenticated": True, "email": user.email}

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

@router.post("/password")
def change_password(data: PasswordChange, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}|{user.email}|password"
    if login_limiter.retry_after(key):
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    if not verify_password(data.current_password, user.password_hash):
        login_limiter.fail(key)
        raise HTTPException(400, "A senha atual está incorreta")
    if data.new_password == data.current_password:
        raise HTTPException(400, "A nova senha precisa ser diferente da atual")
    login_limiter.reset(key)
    user.password_hash = hash_password(data.new_password)  # mesma sessão da dependência require_user
    db.commit()
    return {"changed": True}

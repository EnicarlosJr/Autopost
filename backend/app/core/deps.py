from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import read_access_token
from app.database.session import get_db
from app.models.user import User

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Valida o token e confirma que o usuário ainda existe e está ativo."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    subject = read_access_token(token) if token else None
    user = db.scalar(select(User).where(User.email == subject)) if subject else None
    if user is None or not user.is_active:
        raise HTTPException(401, "Authentication required")
    return user

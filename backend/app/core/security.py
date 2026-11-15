import os
from datetime import datetime, timedelta, timezone
import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 12

def _secret() -> str:
    return os.getenv("JWT_SECRET", "")

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)

def create_access_token(subject: str) -> str:
    secret = _secret()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    expires = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": subject, "exp": expires}, secret, algorithm=JWT_ALGORITHM)

def read_access_token(token: str) -> str | None:
    secret = _secret()
    # Sem segredo forte, nenhum token é aceito (evita tokens assinados com chave vazia).
    if len(secret) < 32:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None

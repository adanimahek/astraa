from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from .config import settings
from .db import users

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
ROLES = ("Administrator", "Traffic Operator")

def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def check_pw(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())

def make_token(email: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.token_hours)
    return jwt.encode({"sub": email, "exp": exp}, settings.jwt_secret, algorithm="HS256")

def public(u: dict) -> dict:
    return {"name": u["name"], "email": u["email"], "role": u["role"]}

def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "Not authenticated")
    try:
        email = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    u = users.find_one({"email": email})
    if not u:
        raise HTTPException(401, "User not found")
    return u

def admin_only(u: dict = Depends(current_user)) -> dict:
    if u["role"] != "Administrator":
        raise HTTPException(403, "Administrator access required")
    return u

def seed_admin():
    users.create_index("email", unique=True)
    if not users.find_one({"email": settings.admin_email}):
        users.insert_one({"name": "Admin", "email": settings.admin_email, "role": "Administrator",
                          "password": hash_pw(settings.admin_password), "created_at": datetime.now(timezone.utc)})

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "Traffic Operator"

@router.post("/login")
def login(body: LoginIn):
    u = users.find_one({"email": body.email.lower()})
    if not u or not check_pw(body.password, u["password"]):
        raise HTTPException(401, "Invalid email or password")
    return {"token": make_token(u["email"]), "user": public(u)}

@router.get("/me")
def me(u: dict = Depends(current_user)):
    return public(u)

@router.post("/users")
def create_user(body: UserIn, _: dict = Depends(admin_only)):
    if body.role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    if users.find_one({"email": body.email.lower()}):
        raise HTTPException(409, "Email already exists")
    doc = {"name": body.name, "email": body.email.lower(), "role": body.role,
           "password": hash_pw(body.password), "created_at": datetime.now(timezone.utc)}
    users.insert_one(doc)
    return public(doc)

@router.get("/users")
def list_users(_: dict = Depends(admin_only)):
    return [public(u) for u in users.find()]

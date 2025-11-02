# app/core/security.py
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

class User(BaseModel):
    id: int
    email: str

def current_user() -> User:
    # Vervang door je echte auth (JWT/session). Nu: stub user 1.
    return User(id=1, email="demo@example.com")

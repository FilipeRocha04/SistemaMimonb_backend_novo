from pydantic import BaseModel, EmailStr
from pydantic import ConfigDict
from typing import Optional
import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None
    papel: Optional[str] = "garcom"  # role, defaults to 'garcom'


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    papel: Optional[str] = None
    username: Optional[str] = None


class UserRead(BaseModel):
    # Pydantic v2: use model_config with from_attributes to support ORM objects
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: Optional[str]
    papel: str
    criado_em: Optional[datetime.datetime]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    identifier: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

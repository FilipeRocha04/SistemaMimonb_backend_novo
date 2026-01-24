from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean
from sqlalchemy.sql import func
from app.db.session import Base
import enum


class RoleEnum(str, enum.Enum):
    admin = "admin"
    garcom = "garcom"
    pizzaiolo = "pizzaiolo"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    # optional username to identify users more easily in the UI
    username = Column(String(150), unique=True, index=True, nullable=True)
    # senha_hash column in your MySQL DB
    senha_hash = Column(String(255), nullable=False)
    # papel (role) column in your DB: e.g. 'admin' or 'garcom'
    papel = Column(Enum(RoleEnum), nullable=False, server_default=RoleEnum.garcom.value)
    # criado_em timestamp column
    criado_em = Column(DateTime(timezone=True), server_default=func.now())


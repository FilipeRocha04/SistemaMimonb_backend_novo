from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Numeric, BigInteger
from sqlalchemy.sql import func
from app.db.session import Base


class Produto(Base):
    __tablename__ = "produtos"

    # DB shows this column as BIGINT(20) — use BigInteger to match the existing
    # schema so foreign keys and create_all align with the DB.
    id = Column(BigInteger, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    categoria = Column(String(100), nullable=True)
    # unit of measure (stored as string to avoid ENUM mismatches). Examples: 'ml','g','un','l'
    unidade = Column(String(10), nullable=True)
    # numeric value representing the quantity for the unit (e.g. 100 for 100ml)
    unidade_valor = Column('unidade_valor', Numeric(10, 2), nullable=True, default=0)
    # the actual DB column is named `preco_atual` (DECIMAL(10,2)); map the
    # attribute `preco` to that column name so SQLAlchemy INSERT/UPDATE uses
    # the existing column instead of a missing `preco` column.
    preco = Column('preco_atual', Numeric(10, 2), nullable=False, default=0.0)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

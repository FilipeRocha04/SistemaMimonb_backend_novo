from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.db.session import Base


class ProdutoPreco(Base):
    __tablename__ = "produto_precos"

    id = Column(Integer, primary_key=True, index=True)
    # produtos.id in the DB is BIGINT(20) — use BigInteger here to match the
    # referenced column type (ensures foreign key can be created).
    produto_id = Column(BigInteger, ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False)
    preco = Column(Float, nullable=False)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())

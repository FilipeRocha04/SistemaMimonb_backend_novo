from sqlalchemy import Column, Integer, Float, ForeignKey, BigInteger
from app.db.session import Base

class ProdutoPrecoQuantidade(Base):
    __tablename__ = "produto_precos_quantidade"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(BigInteger, ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False)
    quantidade = Column(Integer, nullable=False)
    preco = Column(Float, nullable=False)

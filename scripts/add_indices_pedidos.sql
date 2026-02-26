-- Índices recomendados para otimizar buscas e filtros na tabela pedidos
CREATE INDEX idx_pedidos_data_pedido ON pedidos (data_pedido);
CREATE INDEX idx_pedidos_cliente_id ON pedidos (cliente_id);
CREATE INDEX idx_pedidos_status ON pedidos (status);

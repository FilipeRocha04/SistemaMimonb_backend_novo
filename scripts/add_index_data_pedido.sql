-- Criação de índice para otimizar buscas pela data do pedido
CREATE INDEX idx_pedidos_data_pedido ON pedidos (data_pedido);

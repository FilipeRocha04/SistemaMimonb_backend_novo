-- Adiciona a coluna 'metade' na tabela pedido_items
ALTER TABLE pedido_items ADD COLUMN metade TEXT;

-- Atualiza os registros existentes: se quantidade = 0.5, metade = 'metade'
UPDATE pedido_items SET metade = 'metade' WHERE quantidade = 0.5;

ALTER TABLE pedido_items ADD COLUMN metade_tmp BOOLEAN NOT NULL DEFAULT 0;


ALTER TABLE pedido_items DROP COLUMN metade;

ALTER TABLE pedido_items CHANGE metade_tmp metade BOOLEAN NOT NULL DEFAULT 0;
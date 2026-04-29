-- Script SQL para adicionar campo tipo_divisao à tabela pagamentos
-- Identifica se a divisão foi feita de forma igualitária ou por itens

ALTER TABLE pagamentos 
ADD COLUMN tipo_divisao VARCHAR(20) DEFAULT 'igualitaria';

-- Verificar se a coluna foi criada
PRAGMA table_info(pagamentos);

-- Migração para múltiplos pagadores e múltiplas formas de pagamento
-- 1. Tabela de pagadores
CREATE TABLE IF NOT EXISTS pagadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT
);

-- 2. Tabela intermediária: pagamento_pagador_forma
CREATE TABLE IF NOT EXISTS pagamento_pagador_forma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pagamento_id INTEGER NOT NULL,
    pagador_id INTEGER NOT NULL,
    forma_pagamento TEXT NOT NULL,
    valor REAL NOT NULL,
    FOREIGN KEY (pagamento_id) REFERENCES pagamentos(id),
    FOREIGN KEY (pagador_id) REFERENCES pagadores(id)
);

-- Opcional: Adicionar coluna pagador_id na tabela pagamentos para compatibilidade
-- ALTER TABLE pagamentos ADD COLUMN pagador_id INTEGER;
-- ALTER TABLE pagamentos ADD FOREIGN KEY (pagador_id) REFERENCES pagadores(id);

-- Se quiser migrar dados antigos, insira pagadores padrão e relacione pagamentos existentes.
-- Exemplo:
-- INSERT INTO pagadores (nome) VALUES ('Pagador Padrão');
-- UPDATE pagamentos SET pagador_id = 1 WHERE pagador_id IS NULL;

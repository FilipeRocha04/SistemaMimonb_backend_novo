-- Adicionar constraint UNIQUE ao campo nome da tabela clientes
-- Este script remove registros duplicados (mantendo o mais antigo) e depois adiciona a constraint

-- Passo 1: Remover registros duplicados, mantendo apenas o primeiro (id mais baixo)
DELETE FROM clientes
WHERE id NOT IN (
    SELECT MIN(id)
    FROM clientes
    GROUP BY LOWER(nome)
);

-- Passo 2: Adicionar constraint UNIQUE no campo nome
ALTER TABLE clientes
ADD CONSTRAINT uk_clientes_nome UNIQUE (nome);

-- Passo 3: Criar índice se não existir (SQLAlchemy já cria automaticamente com unique=True)
-- ALTER TABLE clientes ADD INDEX idx_clientes_nome (nome);

-- Script para adicionar coluna 'pagar_depois' à tabela pedidos
-- Execute este script no SQLite: sqlite3 mimonb.db < add_pagar_depois.sql

ALTER TABLE pedidos ADD COLUMN pagar_depois SMALLINT NOT NULL DEFAULT 0;

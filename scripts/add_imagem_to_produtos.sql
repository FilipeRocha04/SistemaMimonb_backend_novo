-- Add imagem column to produtos table to store image metadata (URL or object key)
-- Run this against your MySQL database. Backup before running in production.

ALTER TABLE produtos
  ADD COLUMN imagem VARCHAR(512) NULL;

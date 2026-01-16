-- Migration: add 'outros' to produtos.categoria
-- IMPORTANT: backup your database before running this in production.
-- Check current column type (runs in MySQL):
-- SHOW CREATE TABLE produtos;
-- or
-- SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS
--  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'produtos' AND COLUMN_NAME = 'categoria';

-- If the column is already an ENUM, run a MODIFY to include 'outros'. Replace the enum list below with the full list of allowed values in your table.
ALTER TABLE produtos
  MODIFY COLUMN categoria ENUM('forneria','napolitana','dolce','sobremesa','especial','bebida','outros','vinhos') NULL;

-- If the column is currently VARCHAR and you prefer to keep it text-based (safer), you can instead run:
-- ALTER TABLE produtos MODIFY COLUMN categoria VARCHAR(100) NULL;
-- That will allow any string including 'outros'.

-- After running this, verify:
-- SELECT categoria, COUNT(*) FROM produtos GROUP BY categoria ORDER BY categoria;

-- NOTE: On some hosting platforms you may not be allowed to ALTER ENUMs. If the ALTER fails, please export a DB backup and run the ALTER using your DB admin tool or contact the host.

SELECT column_name, data_type, is_nullable
FROM information_schema.COLUMNS
WHERE table_schema = DATABASE() AND table_name = 'pedidos' AND column_name = 'endereco';
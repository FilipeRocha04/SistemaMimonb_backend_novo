-- Adicionar 'pago' ao ENUM de status na tabela pedidos
ALTER TABLE pedidos MODIFY COLUMN status ENUM('pendente','em_preparo','pronto','aguardando','entregue','cancelado','pago') NOT NULL DEFAULT 'pendente';

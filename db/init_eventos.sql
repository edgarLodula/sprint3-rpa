-- Pilar 2 (Sprint 3): tabela de eventos/alertas de anomalia.
-- Roda no MESMO banco `digital_twin` criado por db/init.sql da sprint2-RPA
-- (tabelas ativo/tag/leitura_sensor/localizacao/rpa_log). Não recria nada
-- de lá — só adiciona esta tabela nova, referenciando tag/leitura_sensor.

CREATE TABLE IF NOT EXISTS evento_alerta (
    id SERIAL PRIMARY KEY,
    tag_id INT REFERENCES tag(id) ON DELETE CASCADE,
    leitura_id BIGINT REFERENCES leitura_sensor(id) ON DELETE SET NULL,
    sensor VARCHAR(30) NOT NULL,
    valor_medido FLOAT NOT NULL,
    limite_violado FLOAT NOT NULL,
    severidade VARCHAR(20) NOT NULL,
    mensagem TEXT,
    sugestao_acao TEXT,
    status_anterior VARCHAR(20),
    status_novo VARCHAR(20),
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evento_alerta_tag
    ON evento_alerta(tag_id, criado_em DESC);

-- Ponte com o Pilar 1 (scraping): contexto de referência dos catálogos
-- raspados (WEG/Menzel/RS Delivers), quando existir para o sensor do
-- desvio. Coluna nova, adicionada de forma idempotente sem afetar linhas
-- já existentes.
ALTER TABLE evento_alerta ADD COLUMN IF NOT EXISTS contexto_tecnico TEXT;

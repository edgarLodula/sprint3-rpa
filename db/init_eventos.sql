-- Pilar 2 (Sprint 3): tabela de eventos/alertas de anomalia.
-- Roda no MESMO banco `digital_twin` criado por db/init.sql da sprint2-RPA
-- (tabelas ativo/tag/leitura_sensor/localizacao/rpa_log). Não recria nada
-- de lá — só adiciona esta tabela nova, referenciando tag/leitura_sensor.

CREATE TABLE IF NOT EXISTS evento_alerta (
    id SERIAL PRIMARY KEY,
    tag_id INT REFERENCES tag(id) ON DELETE CASCADE,
    leitura_id BIGINT REFERENCES leitura_sensor(id) ON DELETE SET NULL,
    sensor VARCHAR(30) NOT NULL,
    valor_medido FLOAT,
    limite_violado FLOAT,
    severidade VARCHAR(20) NOT NULL,
    mensagem TEXT,
    sugestao_acao TEXT,
    status_anterior VARCHAR(20),
    status_novo VARCHAR(20),
    criado_em TIMESTAMP DEFAULT NOW()
);

-- valor_medido/limite_violado ficam sem valor em desvios "multivariado"
-- (detectados só pelo modelo de ML, sem um único sensor estourando limite
-- fixo) — ver deteccao_ml/ml_score abaixo.
ALTER TABLE evento_alerta ALTER COLUMN valor_medido DROP NOT NULL;
ALTER TABLE evento_alerta ALTER COLUMN limite_violado DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evento_alerta_tag
    ON evento_alerta(tag_id, criado_em DESC);

-- Ponte com o Pilar 1 (scraping): contexto de referência dos catálogos
-- raspados (WEG/Menzel/RS Delivers), quando existir para o sensor do
-- desvio. Coluna nova, adicionada de forma idempotente sem afetar linhas
-- já existentes.
ALTER TABLE evento_alerta ADD COLUMN IF NOT EXISTS contexto_tecnico TEXT;

-- Camada de ML (deteccao_anomalia_ml.py): todo evento passa pelo mesmo
-- modelo (IsolationForest treinado no histórico do próprio ativo), então
-- fica registrado se o ML concorda com o desvio de regra e o quão anômala
-- a leitura ficou (score menor = mais anômalo). Fica NULL quando não havia
-- histórico suficiente pra treinar o modelo naquela rodada.
ALTER TABLE evento_alerta ADD COLUMN IF NOT EXISTS deteccao_ml BOOLEAN;
ALTER TABLE evento_alerta ADD COLUMN IF NOT EXISTS ml_score FLOAT;

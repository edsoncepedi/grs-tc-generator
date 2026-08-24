-- Tabelas para o banco de dados tc_generator
-- O banco de dados já foi criado pelo script script_init_db.py

-- Criação da tabela de satélites
--
-- Os campos orbitais são opcionais: um satélite sem norad_id nem TLE continua
-- servindo para cadastrar telecomandos, mas não entra no agendamento
-- automático — não há como prever passagens de algo cuja órbita não se conhece.
--
-- norad_id é a fonte preferida (o TLE é buscado no CelesTrak e fica sempre
-- atualizado); tle_line1/tle_line2 existem para satélites fora do catálogo
-- público ou para fixar um TLE específico em testes, e têm precedência quando
-- preenchidos.
CREATE TABLE satellites (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'maintenance')),
    norad_id INTEGER UNIQUE,
    tle_line1 VARCHAR(69),
    tle_line2 VARCHAR(69)
);

-- Criação da tabela de usuários/operadores
CREATE TABLE operators (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'operator' CHECK (role IN ('admin', 'operator', 'viewer')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended'))
);

-- Criação da tabela de passagens agendadas
--
-- O plano produzido pelo TC Scheduler: quando cada satélite estará visível e
-- qual dessas janelas a estação vai de fato usar. Fica no banco (e não só na
-- memória do scheduler) para sobreviver a um restart e para que a interface
-- consiga mostrar quando cada telecomando sai.
--
-- Uma janela é descartada como 'missed' se o AOS passar sem que a estação
-- consiga assumir a passagem — o que distingue "não rastreamos" de
-- "rastreamos e falhou".
CREATE TABLE scheduled_passes (
    id SERIAL PRIMARY KEY,
    satellite_id INTEGER NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
    aos_time TIMESTAMP WITH TIME ZONE NOT NULL,
    los_time TIMESTAMP WITH TIME ZONE NOT NULL,
    culmination_time TIMESTAMP WITH TIME ZONE NOT NULL,
    max_elevation_deg DOUBLE PRECISION NOT NULL,
    aos_azimuth_deg DOUBLE PRECISION NOT NULL,
    los_azimuth_deg DOUBLE PRECISION NOT NULL,
    -- Epoch dos elementos orbitais usados: quanto mais velho, menos confiável
    -- a previsão. Guardado para permitir auditar uma passagem que falhou.
    tle_epoch TIMESTAMP WITH TIME ZONE,
    data_source VARCHAR(10) CHECK (data_source IN ('omm', 'tle')),
    status VARCHAR(20) NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'active', 'completed', 'missed', 'cancelled')),
    status_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_pass_window CHECK (los_time > aos_time)
);

-- Criação da tabela de posição corrente dos satélites
--
-- Uma linha por satélite, sobrescrita a cada ciclo de rastreamento (não é
-- histórico). Responde "onde está cada satélite agora" sem que a interface
-- precise saber propagar órbita.
--
-- status_message guarda o motivo quando o cálculo falha para um satélite
-- específico (TLE ausente, erro de propagação, CelesTrak fora do ar sem
-- cache), para que uma falha isolada fique visível em vez de virar silêncio.
CREATE TABLE satellite_tracking_status (
    satellite_id INTEGER PRIMARY KEY REFERENCES satellites(id) ON DELETE CASCADE,
    latitude_deg DOUBLE PRECISION,
    longitude_deg DOUBLE PRECISION,
    altitude_km DOUBLE PRECISION,
    azimuth_deg DOUBLE PRECISION,
    elevation_deg DOUBLE PRECISION,
    range_km DOUBLE PRECISION,
    is_visible BOOLEAN NOT NULL DEFAULT FALSE,
    tle_epoch TIMESTAMP WITH TIME ZONE,
    data_source VARCHAR(10) CHECK (data_source IN ('omm', 'tle')),
    status_message TEXT,
    checked_at TIMESTAMP WITH TIME ZONE
);

-- Criação da tabela de telecomandos
CREATE TABLE telecommands (
    id SERIAL PRIMARY KEY,
    satellite_id INTEGER NOT NULL REFERENCES satellites(id) ON DELETE CASCADE,
    operator_id INTEGER NOT NULL DEFAULT 1 REFERENCES operators(id) ON DELETE SET DEFAULT,
    command_type VARCHAR(50) NOT NULL,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'queued', 'sent', 'confirmed', 'failed')),
    status_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    confirmed_at TIMESTAMP WITH TIME ZONE,
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    metadata JSONB,
    -- Passagem em que este comando vai ser transmitido. ON DELETE SET NULL
    -- porque cancelar uma passagem não pode apagar o telecomando: ele volta
    -- para a fila e é reagendado no ciclo seguinte.
    scheduled_pass_id INTEGER REFERENCES scheduled_passes(id) ON DELETE SET NULL
);

-- Criação da tabela de logs de execução
CREATE TABLE execution_logs (
    id SERIAL PRIMARY KEY,
    telecommand_id INTEGER REFERENCES telecommands(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES operators(id) ON DELETE SET NULL
);

-- Índices para melhorar o desempenho das consultas
CREATE INDEX idx_telecommands_satellite_id ON telecommands(satellite_id);
CREATE INDEX idx_telecommands_status ON telecommands(status);
CREATE INDEX idx_telecommands_created_at ON telecommands(created_at);
CREATE INDEX idx_telecommands_operator_id ON telecommands(operator_id);
CREATE INDEX idx_telecommands_scheduled_pass_id ON telecommands(scheduled_pass_id);
CREATE INDEX idx_execution_logs_telecommand_id ON execution_logs(telecommand_id);
-- O scheduler busca por status a cada ciclo, e por AOS para achar a próxima
-- passagem a assumir.
CREATE INDEX idx_scheduled_passes_status ON scheduled_passes(status);
CREATE INDEX idx_scheduled_passes_aos_time ON scheduled_passes(aos_time);
CREATE INDEX idx_scheduled_passes_satellite_id ON scheduled_passes(satellite_id);

-- Função para atualizar o campo updated_at automaticamente
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers para atualizar automaticamente o campo updated_at
CREATE TRIGGER update_satellites_modtime
BEFORE UPDATE ON satellites
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

CREATE TRIGGER update_scheduled_passes_modtime
BEFORE UPDATE ON scheduled_passes
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Inserção de dados de exemplo
-- Senha: password123 (hash bcrypt)
INSERT INTO operators (username, email, full_name, password_hash, role) VALUES
('admin', 'admin@tcgenerator.com', 'Administrador do Sistema', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin'),
('operator1', 'operator1@tcgenerator.com', 'Operador 1', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'operator'),
('operator2', 'operator2@tcgenerator.com', 'Operador 2', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'operator');

-- Inserção de satélites de exemplo
--
-- norad_id fica NULL de propósito: um NORAD ID errado faria a estação apontar
-- para outro objeto sem nenhum erro visível, o que é pior do que não apontar.
-- Preencha com o identificador real de cada satélite antes de contar com o
-- agendamento automático:
--     UPDATE satellites SET norad_id = <id> WHERE code = 'SAT-001';
-- Consulte em https://celestrak.org/satcat/search.php
INSERT INTO satellites (name, code, description, status) VALUES
('FloripaSat-1', 'SAT-001', 'Satélite de pesquisa científica', 'active'),
('GOLDS-UFSC', 'SAT-COM-001', 'Satélite de comunicação geoestacionário', 'active'),
('Catarina-A1', 'SAT-OBS-001', 'Satélite de observação terrestre', 'maintenance'),
('Catarina-A2', 'SAT-OBS-002', 'Satélite de observação terrestre', 'maintenance');

-- Inserção de telecomandos de exemplo
-- Nota: Os IDs de satélite e operador são baseados nas inserções acima
-- INSERT INTO telecommands (satellite_id, operator_id, command_type, parameters, status, priority, created_at) VALUES
-- (1, 2, 'RESET', '{"subsystem": "power", "force": true}', 'confirmed', 1, NOW() - INTERVAL '2 hours'),
-- (1, 2, 'DATA_DOWNLINK', '{"data_type": "telemetry", "priority": "high"}', 'sent', 3, NOW() - INTERVAL '1 hour'),
-- (2, 3, 'ANTENNA_DEPLOY', '{"antenna_id": 1, "deploy_sequence": [1,2,3,4]}', 'pending', 1, NOW() - INTERVAL '30 minutes'),
-- (3, 2, 'CAMERA_CAPTURE', '{"resolution": "high", "exposure": 0.5, "filter": "visible"}', 'failed', 5, NOW() - INTERVAL '15 minutes');

-- Script para popular a tabela telecommands com comandos reais do FloripaSat-2A

INSERT INTO telecommands (satellite_id, operator_id, command_type, parameters, status, priority, metadata)
VALUES
-- 1. Comando para ligar aquecedor de bateria (baseado na variável eps_bat_heater_1_dc)
(1, 1, 'SET_HEATER_1_DUTY_CYCLE', '{"value": 100, "unit": "%"}', 'pending', 8, '{"reason": "Cold internal temperature detected", "subsystem": "EPS"}'),

-- 2. Comando para resetar o sistema OBDH (baseado na variável obdh_mcu_rst_count)
(1, 1, 'SYSTEM_RESET', '{"target": "OBDH", "mode": "hard_reset"}', 'pending', 10, '{"reason": "Software watchdog manual trigger"}'),

-- 3. Ajuste de MPPT (baseado na variável eps_mppt_1_dc)
(1, 1, 'SET_MPPT_MODE', '{"mppt_id": 1, "duty_cycle": 85}', 'sent', 5, '{"reason": "Optimize solar energy collection"}'),

-- 4. Comando de Ping (Teste de comunicação)
(1, 1, 'PING', '{"payload": "0x55AA"}', 'confirmed', 1, '{"confirmed_at": "2025-12-22T18:40:00Z"}'),

-- 5. Alteração de intervalo de Beacon (Economia de energia)
(1, 1, 'SET_BEACON_INTERVAL', '{"seconds": 60}', 'queued', 7, '{"reason": "Low battery mode"}'),

-- 6. Limpeza de log de erros (Manutenção)
(1, 1, 'CLEAR_LOGS', '{"target": "all"}', 'pending', 3, '{"reason": "Routine maintenance"}'),

-- 7. Ativação de carga útil (Payload)
(1, 1, 'START_EXPERIMENT', '{"experiment_id": "LORA_TEST", "duration_min": 15}', 'failed', 6, '{"status_message": "Satellite in eclipse, power low"}'),

-- 8. Configuração de ganho de rádio (baseado na variável lora_fsat2a_rssi)
(1, 1, 'SET_RADIO_GAIN', '{"radio_id": 1, "gain_db": 20}', 'pending', 5, '{"reason": "Improve signal-to-noise ratio"}'),

-- 9. Ajuste de aquecedor de bateria 2 (baseado na variável eps_bat_heater_2_dc)
(1, 1, 'SET_HEATER_2_DUTY_CYCLE', '{"value": 50, "unit": "%"}', 'pending', 8, '{"subsystem": "EPS", "reason": "Thermal balancing"}'),

-- 10. Sincronização de relógio (baseado na variável obdh_timestamp)
(1, 1, 'SYNC_CLOCK', '{"unix_timestamp": 1734889200}', 'sent', 9, '{"reason": "Drift correction"}');

-- Inserção de logs de execução de exemplo
INSERT INTO execution_logs (telecommand_id, status, message, details, created_by) VALUES
(1, 'success', 'Comando RESET executado com sucesso', '{"execution_time_ms": 125, "memory_used_kb": 2048}', 2),
(2, 'processing', 'Iniciando downlink de dados', '{"data_size_mb": 15.5, "estimated_time_s": 45}', 2),
(4, 'error', 'Falha ao capturar imagem', '{"error_code": 503, "error_message": "Camera not responding"}', 3);

-- Criação de visualizações úteis
CREATE VIEW vw_recent_telecommands AS
SELECT 
    t.id,
    s.name AS satellite_name,
    s.code AS satellite_code,
    o.username AS operator_username,
    t.command_type,
    t.status,
    t.created_at,
    t.sent_at,
    t.confirmed_at
FROM 
    telecommands t
    JOIN satellites s ON t.satellite_id = s.id
    JOIN operators o ON t.operator_id = o.id
ORDER BY 
    t.created_at DESC
LIMIT 100;

-- Permissões
GRANT ALL PRIVILEGES ON DATABASE tc_generator TO admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin;

-- Comentários para documentação
COMMENT ON TABLE telecommands IS 'It stores the remote commands sent to the satellites.';
COMMENT ON COLUMN telecommands.parameters IS 'Command parameters in JSON format.';
COMMENT ON COLUMN telecommands.metadata IS 'Additional metadata for the command';

-- Função para obter estatísticas de comandos por satélite
CREATE OR REPLACE FUNCTION get_satellite_command_stats(days_interval INTEGER DEFAULT 30)
RETURNS TABLE (
    satellite_id INTEGER,
    satellite_name VARCHAR,
    satellite_code VARCHAR,
    total_commands BIGINT,
    pending_commands BIGINT,
    sent_commands BIGINT,
    confirmed_commands BIGINT,
    failed_commands BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id AS satellite_id,
        s.name AS satellite_name,
        s.code AS satellite_code,
        COUNT(t.id)::BIGINT AS total_commands,
        SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END)::BIGINT AS pending_commands,
        SUM(CASE WHEN t.status = 'sent' THEN 1 ELSE 0 END)::BIGINT AS sent_commands,
        SUM(CASE WHEN t.status = 'confirmed' THEN 1 ELSE 0 END)::BIGINT AS confirmed_commands,
        SUM(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END)::BIGINT AS failed_commands
    FROM 
        satellites s
        LEFT JOIN telecommands t ON s.id = t.satellite_id
    WHERE 
        t.created_at >= (CURRENT_DATE - (days_interval || ' days')::INTERVAL)
    GROUP BY 
        s.id, s.name, s.code
    ORDER BY 
        total_commands DESC;
END;
$$ LANGUAGE plpgsql;

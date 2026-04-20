-- ============================================================
-- Database: b6810045589
-- Food Delivery IoT Monitoring System
-- ============================================================

CREATE DATABASE IF NOT EXISTS b6810045589
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE b6810045589;

-- ------------------------------------------------------------
-- Table: env_data
-- Stores environmental sensor readings from ESP32 (DHT11, MQ2, KY-018)
-- Each row represents one reading cycle from one transporter.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS env_data (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    transporter_id    INT             NOT NULL,
    humidity          INT             NOT NULL COMMENT 'DHT11 relative humidity (%)',
    temperature       INT             NOT NULL COMMENT 'DHT11 temperature (°C)',
    gas_concentration INT             NOT NULL COMMENT 'MQ2 estimated gas ppm',
    gas_raw           INT             NOT NULL COMMENT 'MQ2 raw ADC value',
    gas_alert         TINYINT         NOT NULL DEFAULT 1 COMMENT '1 = DOUT HIGH (alert), 0 = safe',
    brightness        DECIMAL(5,1)    NOT NULL COMMENT 'KY-018 lux-equivalent value',
    ldr_raw           INT             NOT NULL COMMENT 'KY-018 raw ADC value',
    received_at       DATETIME        NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    INDEX idx_env_transporter_time (transporter_id, received_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- Table: gps_data
-- Stores GPS coordinates from the delivery person's phone
-- sent via WebSocket → Node-RED bridge.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gps_data (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    transporter_id   INT             NOT NULL,
    lat              DOUBLE          NOT NULL COMMENT 'Latitude in decimal degrees',
    longitude        DOUBLE          NOT NULL COMMENT 'Longitude in decimal degrees',
    gps_timestamp    BIGINT          NOT NULL COMMENT 'Unix timestamp (ms) from phone',
    source           VARCHAR(50)     NOT NULL DEFAULT 'unknown' COMMENT 'Data source: phone, gtfs, etc.',
    received_at      DATETIME        NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    INDEX idx_gps_transporter_time (transporter_id, received_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- View: freshness_score
-- Computes a 0-100 freshness score per active transporter
-- using the last hour of sensor data.
-- Formula: 100 - (avg_gas/10) - (MAX(0, avg_humidity-65)*0.5) - (gas_alert_count*2)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW freshness_score AS
SELECT
    e.transporter_id,
    COUNT(*)                                          AS reading_count,
    ROUND(AVG(e.humidity),        1)                  AS avg_humidity,
    ROUND(AVG(e.temperature),     1)                  AS avg_temperature,
    ROUND(AVG(e.gas_concentration), 0)                AS avg_gas_ppm,
    SUM(CASE WHEN e.gas_alert = 1 THEN 1 ELSE 0 END)  AS gas_alert_count,
    ROUND(AVG(e.brightness),      1)                  AS avg_brightness,
    GREATEST(0, LEAST(100,
        100
        - (AVG(e.gas_concentration) / 10.0)
        - (GREATEST(0, AVG(e.humidity) - 65) * 0.5)
        - (SUM(CASE WHEN e.gas_alert = 1 THEN 1 ELSE 0 END) * 2)
    ))                                                AS score
FROM env_data e
WHERE e.received_at >= NOW() - INTERVAL 1 HOUR
GROUP BY e.transporter_id;

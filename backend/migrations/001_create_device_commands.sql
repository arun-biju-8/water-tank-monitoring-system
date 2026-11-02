-- ==============================================================================
-- Migration: 001_create_device_commands.sql
-- Purpose: Adds bidirectional command execution table for remote buzzer control
-- Safety: Preserves existing water_readings table and all existing historical data
-- ==============================================================================

CREATE TABLE IF NOT EXISTS device_commands (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL DEFAULT 'esp32-tank-01',
    command_type VARCHAR(32) NOT NULL,
    command_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_device_commands_id ON device_commands (id);
CREATE INDEX IF NOT EXISTS ix_device_commands_device_id ON device_commands (device_id);
CREATE INDEX IF NOT EXISTS ix_device_commands_command_status ON device_commands (command_status);
CREATE INDEX IF NOT EXISTS ix_device_commands_created_at ON device_commands (created_at);


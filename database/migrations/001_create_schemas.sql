-- MATCHPOINT Data Warehouse
-- Migration: 001
-- Purpose: Initialize Medallion Architecture schemas

BEGIN;

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE SCHEMA IF NOT EXISTS silver;

CREATE SCHEMA IF NOT EXISTS gold;

COMMIT;
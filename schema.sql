-- ============================================================================
-- VettingBridge Database Initialization & Schema Definition
-- PostgreSQL 15+ compatible
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enums
CREATE TYPE user_role AS ENUM (
    'BUYER',
    'SUPPLIER',
    'INSPECTOR',
    'SYSTEM_ADMIN'
);

CREATE TYPE verification_status AS ENUM (
    'PENDING',
    'IN_REVIEW',
    'VERIFIED',
    'REJECTED',
    'SUSPENDED'
);

CREATE TYPE escrow_state AS ENUM (
    'INITIATED',
    'FUNDS_LOCKED',
    'INSPECTION_PENDING',
    'RELEASED',
    'DISPUTED'
);

CREATE TYPE inspection_status AS ENUM (
    'ASSIGNED',
    'SCHEDULED',
    'IN_PROGRESS',
    'PASSED',
    'FAILED',
    'REJECTED'
);

CREATE TYPE token_type AS ENUM (
    'QUICK_PASS',
    'FACILITY_PASSPORT',
    'INSPECTOR_DISPATCH',
    'ACTION_RELEASE'
);

-- 1. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Entity Profiles Table (Buyers, Suppliers, Inspector Agencies)
CREATE TABLE entity_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_name VARCHAR(255) NOT NULL,
    registration_number VARCHAR(100) NOT NULL,
    jurisdiction_country VARCHAR(3) NOT NULL, -- ISO-3166-1 alpha-3
    verification_status verification_status NOT NULL DEFAULT 'PENDING',
    public_signing_key TEXT, -- Public key for signature verification
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Compliance Vault (Encrypted document references & KYB metadata)
CREATE TABLE compliance_vault (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entity_profiles(id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL, -- KYB, EXPORT_CERTIFICATE, TAX_ID, etc.
    document_uri VARCHAR(512) NOT NULL, -- S3/GCS encrypted object path
    document_sha256 VARCHAR(64) NOT NULL, -- Canonical checksum
    encryption_key_id VARCHAR(128) NOT NULL, -- KMS Key Identifier
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    blockchain_tx_anchor VARCHAR(128), -- Ledger notarization TX
    verification_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Orders Table
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(64) NOT NULL UNIQUE,
    buyer_id UUID NOT NULL REFERENCES entity_profiles(id),
    supplier_id UUID NOT NULL REFERENCES entity_profiles(id),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    subtotal_amount NUMERIC(15, 2) NOT NULL CHECK (subtotal_amount > 0),
    platform_fee_percent NUMERIC(5, 2) NOT NULL DEFAULT 2.00 CHECK (platform_fee_percent >= 1.50 AND platform_fee_percent <= 3.00),
    platform_fee_amount NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    total_amount NUMERIC(15, 2) NOT NULL CHECK (total_amount >= subtotal_amount),
    escrow_state escrow_state NOT NULL DEFAULT 'INITIATED',
    funding_deadline TIMESTAMPTZ,
    inspection_deadline TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 5. Escrow Accounts Table
CREATE TABLE escrow_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL UNIQUE REFERENCES orders(id) ON DELETE RESTRICT,
    locked_amount NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    buyer_fee_absorbed NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    supplier_fee_deducted NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    payout_account_ref VARCHAR(128),
    smart_contract_address VARCHAR(128),
    deposit_tx_hash VARCHAR(128),
    release_tx_hash VARCHAR(128),
    locked_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. Inspections Table
CREATE TABLE inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    inspector_id UUID NOT NULL REFERENCES users(id),
    status inspection_status NOT NULL DEFAULT 'ASSIGNED',
    proof_document_uri VARCHAR(512),
    proof_sha256 VARCHAR(64),
    digital_signature TEXT, -- Cryptographic signature from inspector
    signature_algorithm VARCHAR(32) DEFAULT 'Ed25519',
    report_data JSONB DEFAULT '{}'::jsonb,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 7. Secure Tokens & QRL Registry
CREATE TABLE secure_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_type token_type NOT NULL,
    entity_id UUID REFERENCES entity_profiles(id),
    order_id UUID REFERENCES orders(id),
    jws_token TEXT NOT NULL UNIQUE,
    nonce VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    claims JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 8. Immutable Audit Trail & Notarization Log
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    actor_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    blockchain_batch_id VARCHAR(128),
    blockchain_tx_anchor VARCHAR(128),
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Indexes for high-frequency queries
CREATE INDEX idx_orders_buyer ON orders(buyer_id);
CREATE INDEX idx_orders_supplier ON orders(supplier_id);
CREATE INDEX idx_orders_escrow_state ON orders(escrow_state);
CREATE INDEX idx_escrow_accounts_order ON escrow_accounts(order_id);
CREATE INDEX idx_inspections_order ON inspections(order_id);
CREATE INDEX idx_secure_tokens_expires_at ON secure_tokens(expires_at) WHERE is_revoked = FALSE;
CREATE INDEX idx_audit_logs_order ON audit_logs(order_id);
CREATE INDEX idx_compliance_vault_entity ON compliance_vault(entity_id);

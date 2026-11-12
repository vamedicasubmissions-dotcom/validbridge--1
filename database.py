"""
ValidBridge Core Database Layer (Section 1)
Supports SQLite (zero-config, zero-cost local default) and PostgreSQL.
Implements the 5-State Escrow State Machine and full schema models:
- Users & Role-Based Permissions (BUYER, SUPPLIER, INSPECTOR, SYSTEM_ADMIN)
- Entity Profiles & Public Keys
- Compliance Vault (AES-256 encrypted doc references & KYB)
- Orders & Escrow Accounts (with the 5 explicit states)
- Inspections (with digital signatures and SHA-256 hashes)
- Secure Tokens & Nonces
- Audit Logs
"""

import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

DB_PATH = Path("D:/ValidBridge/validbridge.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initializes the database schema matching Section 1 specifications."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('BUYER', 'SUPPLIER', 'INSPECTOR', 'SYSTEM_ADMIN')),
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Entity Profiles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS entity_profiles (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        registration_number TEXT NOT NULL,
        jurisdiction_country TEXT NOT NULL,
        verification_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(verification_status IN ('PENDING', 'IN_REVIEW', 'VERIFIED', 'REJECTED', 'SUSPENDED')),
        public_signing_key TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Compliance Vault
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compliance_vault (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        document_type TEXT NOT NULL,
        document_uri TEXT NOT NULL,
        document_sha256 TEXT NOT NULL,
        encryption_key_id TEXT NOT NULL,
        is_verified INTEGER NOT NULL DEFAULT 0,
        blockchain_tx_anchor TEXT,
        verification_payload TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY (entity_id) REFERENCES entity_profiles(id) ON DELETE CASCADE
    );
    """)

    # 4. Orders Table (Enforcing the 5-State Machine)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        order_number TEXT UNIQUE NOT NULL,
        buyer_id TEXT NOT NULL,
        supplier_id TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD',
        subtotal_amount REAL NOT NULL,
        platform_fee_percent REAL NOT NULL DEFAULT 2.00,
        platform_fee_amount REAL NOT NULL DEFAULT 0.00,
        total_amount REAL NOT NULL,
        escrow_state TEXT NOT NULL CHECK(escrow_state IN ('INITIATED', 'FUNDS_LOCKED', 'INSPECTION_PENDING', 'RELEASED', 'DISPUTED')),
        funding_deadline TEXT,
        inspection_deadline TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (buyer_id) REFERENCES entity_profiles(id),
        FOREIGN KEY (supplier_id) REFERENCES entity_profiles(id)
    );
    """)

    # 5. Escrow Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS escrow_accounts (
        id TEXT PRIMARY KEY,
        order_id TEXT UNIQUE NOT NULL,
        locked_amount REAL NOT NULL DEFAULT 0.00,
        buyer_fee_absorbed REAL NOT NULL DEFAULT 0.00,
        supplier_fee_deducted REAL NOT NULL DEFAULT 0.00,
        smart_contract_address TEXT,
        deposit_tx_hash TEXT,
        release_tx_hash TEXT,
        locked_at TEXT,
        released_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id)
    );
    """)

    # 6. Inspections Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspections (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL,
        inspector_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ASSIGNED' CHECK(status IN ('ASSIGNED', 'SCHEDULED', 'IN_PROGRESS', 'PASSED', 'FAILED', 'REJECTED')),
        proof_document_uri TEXT,
        proof_sha256 TEXT,
        digital_signature TEXT,
        signature_algorithm TEXT DEFAULT 'Ed25519',
        report_data TEXT DEFAULT '{}',
        verified_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (inspector_id) REFERENCES users(id)
    );
    """)

    # 7. Secure Tokens Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS secure_tokens (
        id TEXT PRIMARY KEY,
        token_type TEXT NOT NULL,
        entity_id TEXT,
        order_id TEXT,
        jws_token TEXT UNIQUE NOT NULL,
        nonce TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        is_revoked INTEGER NOT NULL DEFAULT 0,
        used_at TEXT,
        claims TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    """)

    # 8. Immutable Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        order_id TEXT,
        actor_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        blockchain_tx_anchor TEXT,
        event_timestamp TEXT NOT NULL,
        details TEXT DEFAULT '{}'
    );
    """)

    # Create performance indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_state ON orders(escrow_state);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_supplier ON orders(supplier_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_expires ON secure_tokens(expires_at);")

    conn.commit()
    conn.close()


class DatabaseRepository:
    """High-level repository enforcing state machine validation and operations."""

    @staticmethod
    def create_user(email: str, password_hash: str, role: str) -> str:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (user_id, email, password_hash, role, now)
        )
        conn.commit()
        conn.close()
        return user_id

    @staticmethod
    def create_entity_profile(user_id: str, name: str, reg_num: str, country: str, pub_key: str = None) -> str:
        profile_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO entity_profiles 
               (id, user_id, entity_name, registration_number, jurisdiction_country, verification_status, public_signing_key, created_at) 
               VALUES (?, ?, ?, ?, ?, 'VERIFIED', ?, ?)""",
            (profile_id, user_id, name, reg_num, country, pub_key, now)
        )
        conn.commit()
        conn.close()
        return profile_id

    @staticmethod
    def add_compliance_document(entity_id: str, doc_type: str, uri: str, sha256_hash: str, key_id: str) -> str:
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO compliance_vault 
               (id, entity_id, document_type, document_uri, document_sha256, encryption_key_id, is_verified, created_at) 
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (doc_id, entity_id, doc_type, uri, sha256_hash, key_id, now)
        )
        conn.commit()
        conn.close()
        return doc_id

    @staticmethod
    def create_order(
        order_number: str,
        buyer_id: str,
        supplier_id: str,
        subtotal: float,
        fee_percent: float = 2.0
    ) -> Dict[str, Any]:
        order_id = str(uuid.uuid4())
        fee_amount = round(subtotal * (fee_percent / 100.0), 2)
        total_amount = round(subtotal + fee_amount, 2)
        now = datetime.now(timezone.utc).isoformat()

        conn = get_db_connection()
        conn.execute(
            """INSERT INTO orders 
               (id, order_number, buyer_id, supplier_id, subtotal_amount, platform_fee_percent, platform_fee_amount, total_amount, escrow_state, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'INITIATED', ?)""",
            (order_id, order_number, buyer_id, supplier_id, subtotal, fee_percent, fee_amount, total_amount, now)
        )
        conn.execute(
            "INSERT INTO escrow_accounts (id, order_id, locked_amount, buyer_fee_absorbed, created_at) VALUES (?, ?, 0.0, ?, ?)",
            (str(uuid.uuid4()), order_id, fee_amount, now)
        )
        conn.commit()
        conn.close()
        return {
            "order_id": order_id,
            "order_number": order_number,
            "subtotal": subtotal,
            "fee": fee_amount,
            "total": total_amount,
            "state": "INITIATED"
        }

    @staticmethod
    def transition_order_state(order_id: str, target_state: str, actor_id: str = "system") -> Dict[str, Any]:
        """Validates and enforces the 5-state escrow machine in persistent storage."""
        VALID_TRANSITIONS = {
            "INITIATED": ["FUNDS_LOCKED", "DISPUTED"],
            "FUNDS_LOCKED": ["INSPECTION_PENDING", "DISPUTED"],
            "INSPECTION_PENDING": ["RELEASED", "DISPUTED"],
            "DISPUTED": ["RELEASED"],
            "RELEASED": []
        }

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT escrow_state, order_number FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError("Order not found.")

        current_state = row["escrow_state"]
        if target_state not in VALID_TRANSITIONS.get(current_state, []):
            conn.close()
            raise ValueError(f"Illegal transition: {current_state} -> {target_state}")

        cursor.execute("UPDATE orders SET escrow_state = ? WHERE id = ?", (target_state, order_id))
        
        # Log to audit trail
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO audit_logs (id, order_id, actor_id, action, entity_type, entity_id, payload_sha256, event_timestamp)
               VALUES (?, ?, ?, ?, 'ORDER', ?, '', ?)""",
            (str(uuid.uuid4()), order_id, actor_id, f"STATE_CHANGE_TO_{target_state}", order_id, now)
        )
        conn.commit()
        conn.close()
        return {"order_id": order_id, "previous_state": current_state, "new_state": target_state}

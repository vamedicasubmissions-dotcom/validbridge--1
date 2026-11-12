# ValidBridge

**ValidBridge** ([validbridge.com](https://validbridge.com)) is an institutional-grade B2B cross-border trade facilitation platform and cryptographic trust bridge.

## Architecture & Subsystems

| Module | File | Purpose |
| :--- | :--- | :--- |
| **System Specification** | [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Blueprint, state machine graphs, security specs, and fee structure. |
| **Database Schema** | [`schema.sql`](schema.sql) | PostgreSQL DDL with Enums, tables for Users, Profiles, Vault, Escrow, Inspections, and Tokens. |
| **Escrow & Fee Engine** | [`escrow_engine.py`](escrow_engine.py) | 5-State Escrow State Machine and 1.5%–3.0% Pass-Through Fee Calculator. |
| **Dynamic QRL Engine** | [`qr_engine.py`](qr_engine.py) | JWS-based cryptographic token generator/verifier and SVG QR badge renderer with `validbridge.com` URLs. |
| **AI Assistant & Alerts** | [`ai_assistant.py`](ai_assistant.py) | Proactive notification generator and deadline escalation guardrails. |
| **Merkle Audit Vault** | [`audit_vault.py`](audit_vault.py) | Merkle Tree builder and blockchain notarization ledger anchor for immutable audit trails. |
| **Smart Contract (Solidity)** | [`contracts/ValidBridgeEscrow.sol`](contracts/ValidBridgeEscrow.sol) | Production EVM multi-party escrow contract with conditional inspector releases. |
| **Interactive Web UI** | [`index.html`](index.html) | Client portal demonstrating zero-cost window shopping, live deal rooms, dynamic QR code rendering, and AI alerts. |
| **REST API Server** | [`server.py`](server.py) | Zero-cost catalog, order lifecycle, inspector dispatch, QRL verification, and dispute routes. |

## Verification & Testing

Run all unit, API, and EVM contract tests:

```powershell
python -m unittest test_core.py test_api_direct.py test_contract_simulation.py
```

## Running the Web Application

To launch the local web portal:
```powershell
python server.py
```
Then navigate in your browser to:
`http://localhost:8080/`

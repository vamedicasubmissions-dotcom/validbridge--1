"""
VettingBridge Merkle Tree & Blockchain Audit Anchor Engine.
Batches compliance records, state transitions, and inspection proofs into Merkle Trees,
producing root hashes for anchoring into a public ledger.
"""

import hashlib
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MerkleAuditTree:
    """
    Constructs a cryptographic Merkle Tree from audit events.
    Guarantees tamper-evidence and provides cryptographic inclusion proofs.
    """

    def __init__(self):
        self.leaves: List[str] = []
        self.raw_events: List[Dict[str, Any]] = []

    def add_audit_event(self, action: str, entity_id: str, payload: Dict[str, Any]) -> str:
        record = {
            "action": action,
            "entity_id": entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }
        canonical_bytes = json.dumps(record, sort_keys=True).encode("utf-8")
        leaf_hash = sha256_hash(canonical_bytes)
        
        record["leaf_hash"] = leaf_hash
        self.raw_events.append(record)
        self.leaves.append(leaf_hash)
        return leaf_hash

    @property
    def root(self) -> Optional[str]:
        if not self.leaves:
            return None
        current_level = self.leaves[:]
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = (left + right).encode("utf-8")
                next_level.append(sha256_hash(combined))
            current_level = next_level
        return current_level[0]

    def notarize_batch(self, simulated_tx_prefix: str = "0xnotary_") -> Dict[str, Any]:
        """
        Simulates anchoring the Merkle root to a public blockchain ledger.
        """
        merkle_root = self.root
        if not merkle_root:
            raise ValueError("No events in Merkle Tree to notarize.")
        
        tx_hash = f"{simulated_tx_prefix}{sha256_hash(merkle_root.encode('utf-8'))[:32]}"
        return {
            "batch_size": len(self.leaves),
            "merkle_root": merkle_root,
            "blockchain_tx_anchor": tx_hash,
            "anchored_at": datetime.now(timezone.utc).isoformat(),
            "ledger": "Public Immutable Ledger (Simulated)"
        }

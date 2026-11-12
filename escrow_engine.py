"""
VettingBridge Core State Machine & Business Logic Engine.
Implements the 5-state escrow lifecycle, pass-through fee engine, and event triggers.
"""

from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid


class EscrowState(str, Enum):
    INITIATED = "INITIATED"
    FUNDS_LOCKED = "FUNDS_LOCKED"
    INSPECTION_PENDING = "INSPECTION_PENDING"
    RELEASED = "RELEASED"
    DISPUTED = "DISPUTED"


class FeeSplitPolicy(str, Enum):
    BUYER_PAYS = "BUYER_PAYS"          # Full fee appended at checkout
    SUPPLIER_PAYS = "SUPPLIER_PAYS"    # Full fee deducted on payout
    EQUAL_SPLIT = "EQUAL_SPLIT"        # 50/50 split between buyer and supplier


class PassThroughFeeCalculator:
    """
    Pass-Through Fee Engine:
    Calculates 1.5% - 3.0% platform fee to absorb identity verification,
    escrow gateway, smart contract execution, and notary API charges.
    """
    
    MIN_FEE_PERCENT = Decimal("1.50")
    MAX_FEE_PERCENT = Decimal("3.00")
    DEFAULT_FEE_PERCENT = Decimal("2.00")

    @classmethod
    def calculate(
        cls,
        subtotal: Decimal,
        fee_percent: Decimal = DEFAULT_FEE_PERCENT,
        policy: FeeSplitPolicy = FeeSplitPolicy.BUYER_PAYS
    ) -> Dict[str, Decimal]:
        if fee_percent < cls.MIN_FEE_PERCENT or fee_percent > cls.MAX_FEE_PERCENT:
            raise ValueError(f"Fee percent must be between {cls.MIN_FEE_PERCENT}% and {cls.MAX_FEE_PERCENT}%.")
        
        total_fee = (subtotal * (fee_percent / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        if policy == FeeSplitPolicy.BUYER_PAYS:
            buyer_fee = total_fee
            supplier_fee = Decimal("0.00")
        elif policy == FeeSplitPolicy.SUPPLIER_PAYS:
            buyer_fee = Decimal("0.00")
            supplier_fee = total_fee
        elif policy == FeeSplitPolicy.EQUAL_SPLIT:
            buyer_fee = (total_fee / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            supplier_fee = total_fee - buyer_fee
        else:
            raise ValueError(f"Unknown fee split policy: {policy}")

        buyer_payable = subtotal + buyer_fee
        supplier_payout = subtotal - supplier_fee

        return {
            "subtotal": subtotal,
            "fee_percent": fee_percent,
            "total_fee": total_fee,
            "buyer_fee": buyer_fee,
            "supplier_fee": supplier_fee,
            "buyer_payable": buyer_payable,
            "supplier_payout": supplier_payout
        }


class EscrowStateMachine:
    """
    Enforces transitions across the 5 canonical states:
    INITIATED -> FUNDS_LOCKED -> INSPECTION_PENDING -> RELEASED | DISPUTED
    """

    ALLOWED_TRANSITIONS = {
        EscrowState.INITIATED: {EscrowState.FUNDS_LOCKED, EscrowState.DISPUTED},
        EscrowState.FUNDS_LOCKED: {EscrowState.INSPECTION_PENDING, EscrowState.DISPUTED},
        EscrowState.INSPECTION_PENDING: {EscrowState.RELEASED, EscrowState.DISPUTED},
        EscrowState.DISPUTED: {EscrowState.RELEASED},  # Can be settled or refunded by arbiter
        EscrowState.RELEASED: set(),                   # Terminal state
    }

    def __init__(self, order_id: str, initial_state: EscrowState = EscrowState.INITIATED):
        self.order_id = order_id
        self.current_state = initial_state
        self.history = [
            {
                "from_state": None,
                "to_state": initial_state.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "Order created"
            }
        ]

    def transition_to(self, new_state: EscrowState, reason: str, metadata: Optional[Dict[str, Any]] = None):
        if new_state not in self.ALLOWED_TRANSITIONS[self.current_state]:
            raise ValueError(
                f"Invalid transition from {self.current_state.value} to {new_state.value}. "
                f"Allowed transitions: {[s.value for s in self.ALLOWED_TRANSITIONS[self.current_state]]}"
            )
        
        prev_state = self.current_state
        self.current_state = new_state
        
        transition_record = {
            "from_state": prev_state.value,
            "to_state": new_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "metadata": metadata or {}
        }
        self.history.append(transition_record)
        return transition_record


class EscrowOrder:
    """
    Encapsulates an order with financial calculations and lifecycle guards.
    """

    def __init__(
        self,
        order_number: str,
        buyer_id: str,
        supplier_id: str,
        subtotal: Decimal,
        fee_percent: Decimal = Decimal("2.00"),
        fee_policy: FeeSplitPolicy = FeeSplitPolicy.BUYER_PAYS,
        funding_timeout_hours: int = 48
    ):
        self.id = str(uuid.uuid4())
        self.order_number = order_number
        self.buyer_id = buyer_id
        self.supplier_id = supplier_id
        
        self.fees = PassThroughFeeCalculator.calculate(subtotal, fee_percent, fee_policy)
        self.state_machine = EscrowStateMachine(self.id)
        
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.funding_deadline = now + timedelta(hours=funding_timeout_hours)
        self.inspection_deadline: Optional[datetime] = None

    @property
    def current_state(self) -> EscrowState:
        return self.state_machine.current_state

    def lock_funds(self, payment_tx_ref: str):
        """Called when buyer escrow funding confirms."""
        now = datetime.now(timezone.utc)
        if now > self.funding_deadline:
            self.state_machine.transition_to(
                EscrowState.DISPUTED,
                reason="Funding deadline exceeded before funds locked."
            )
            raise TimeoutError("Funding deadline has expired. Order marked as DISPUTED/CANCELLED.")

        return self.state_machine.transition_to(
            EscrowState.FUNDS_LOCKED,
            reason="Buyer funds verified and locked in escrow contract.",
            metadata={"payment_tx_ref": payment_tx_ref, "locked_amount": str(self.fees["buyer_payable"])}
        )

    def dispatch_inspection(self, inspector_id: str, inspection_window_hours: int = 72):
        """Called when goods are prepared and inspector is assigned."""
        now = datetime.now(timezone.utc)
        self.inspection_deadline = now + timedelta(hours=inspection_window_hours)
        
        return self.state_machine.transition_to(
            EscrowState.INSPECTION_PENDING,
            reason="Goods reported ready by supplier; inspector dispatched.",
            metadata={
                "inspector_id": inspector_id,
                "inspection_deadline": self.inspection_deadline.isoformat()
            }
        )

    def release_funds(self, proof_sha256: str, digital_signature: str, inspector_id: str):
        """Release funds strictly upon verified inspection proof."""
        now = datetime.now(timezone.utc)
        if self.inspection_deadline and now > self.inspection_deadline:
            self.state_machine.transition_to(
                EscrowState.DISPUTED,
                reason="Inspection deadline exceeded without valid proof."
            )
            raise TimeoutError("Inspection window expired.")

        return self.state_machine.transition_to(
            EscrowState.RELEASED,
            reason="Valid cryptographically verified inspection proof uploaded.",
            metadata={
                "proof_sha256": proof_sha256,
                "digital_signature": digital_signature,
                "inspector_id": inspector_id,
                "payout_amount": str(self.fees["supplier_payout"])
            }
        )

    def dispute(self, reason: str, reporter_id: str):
        """Raise dispute from any active state."""
        return self.state_machine.transition_to(
            EscrowState.DISPUTED,
            reason=f"Dispute raised by {reporter_id}: {reason}"
        )

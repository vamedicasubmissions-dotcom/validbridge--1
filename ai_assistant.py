"""
VettingBridge Automated AI Assistant & Smart Notification Engine.
Monitors transactions, checks deal momentum, and triggers proactive alerts.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from escrow_engine import EscrowOrder, EscrowState


class NotificationChannel:
    WEBSOCKET = "WEBSOCKET"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


class ProactiveAIEngine:
    """
    Evaluates order states, time-to-deadlines, and context to produce
    intelligent notifications for Buyers, Suppliers, and Inspectors.
    """

    @classmethod
    def evaluate_order(cls, order: EscrowOrder, current_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = current_time or datetime.now(timezone.utc)
        notifications = []

        # 1. Buyer Action Trigger: Payment required on INITIATED
        if order.current_state == EscrowState.INITIATED:
            remaining_funding = order.funding_deadline - now
            hours_left = max(0, int(remaining_funding.total_seconds() // 3600))
            
            if remaining_funding.total_seconds() > 0:
                urgency = "HIGH" if hours_left <= 24 else "NORMAL"
                notifications.append({
                    "recipient_role": "BUYER",
                    "recipient_id": order.buyer_id,
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "urgency": urgency,
                    "channel": [NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL, NotificationChannel.SMS],
                    "title": f"Payment Escrow Lock Required (Deadline in {hours_left}h)",
                    "message": (
                        f"Order {order.order_number} has completed KYB verification. "
                        f"Please lock ${order.fees['buyer_payable']} (including pass-through fee of "
                        f"${order.fees['buyer_fee']}) into escrow to secure the transaction."
                    ),
                    "action_required": "LOCK_FUNDS",
                    "action_url": f"/orders/{order.id}/checkout"
                })
            else:
                notifications.append({
                    "recipient_role": "SYSTEM_ADMIN",
                    "order_id": order.id,
                    "urgency": "CRITICAL",
                    "channel": [NotificationChannel.WEBSOCKET],
                    "title": f"Order {order.order_number} Funding Timeout Expired",
                    "message": "Order exceeded funding deadline and is queued for cancellation."
                })

        # 2. Supplier Action Trigger: Funds locked, prepare goods
        elif order.current_state == EscrowState.FUNDS_LOCKED:
            notifications.append({
                "recipient_role": "SUPPLIER",
                "recipient_id": order.supplier_id,
                "order_id": order.id,
                "order_number": order.order_number,
                "urgency": "HIGH",
                "channel": [NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL],
                "title": f"Funds Locked (${order.fees['buyer_payable']}): Prepare Goods for Dispatch",
                "message": (
                    f"Buyer has fully funded the escrow for order {order.order_number}. "
                    f"Funds are securely locked in smart escrow. Please prepare the consignment and "
                    f"mark as ready for third-party inspection."
                ),
                "action_required": "PREPARE_SHIPMENT",
                "action_url": f"/orders/{order.id}/fulfillment"
            })

        # 3. Inspector Dispatch Trigger: Single-use QR token ready
        elif order.current_state == EscrowState.INSPECTION_PENDING:
            if order.inspection_deadline:
                remaining_inspection = order.inspection_deadline - now
                hours_left = max(0, int(remaining_inspection.total_seconds() // 3600))
                
                notifications.append({
                    "recipient_role": "INSPECTOR",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "urgency": "HIGH",
                    "channel": [NotificationChannel.WEBSOCKET, NotificationChannel.PUSH, NotificationChannel.EMAIL],
                    "title": f"New Inspection Assignment: Order {order.order_number}",
                    "message": (
                        f"Consignment is ready for physical verification. "
                        f"A dynamic single-use access QR token has been generated. "
                        f"Inspection upload window closes in {hours_left}h."
                    ),
                    "action_required": "CONDUCT_INSPECTION",
                    "action_url": f"/inspections/dispatch/{order.id}"
                })

        # 4. Success State: Funds Released
        elif order.current_state == EscrowState.RELEASED:
            notifications.append({
                "recipient_role": "SUPPLIER",
                "recipient_id": order.supplier_id,
                "order_id": order.id,
                "order_number": order.order_number,
                "urgency": "NORMAL",
                "channel": [NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL],
                "title": f"Escrow Released: Payout of ${order.fees['supplier_payout']} Initiated",
                "message": f"Inspection passed. Escrow funds have been settled to your payout account."
            })
            notifications.append({
                "recipient_role": "BUYER",
                "recipient_id": order.buyer_id,
                "order_id": order.id,
                "order_number": order.order_number,
                "urgency": "NORMAL",
                "channel": [NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL],
                "title": f"Order {order.order_number} Completed",
                "message": "Inspection passed and certified report is available for download."
            })

        return notifications

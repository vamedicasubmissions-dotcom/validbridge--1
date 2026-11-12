"""
VettingBridge HTTP REST API Server
Built with standard library http.server (zero third-party dependencies required).
Implements endpoints for:
- Browsing & Catalog (pure read operation, zero 3rd-party/escrow cost)
- Orders & Escrow state management (Initiation, Lock, Inspection, Release, Dispute)
- Cryptographic QR & QRL Verification
- Compliance Webhook simulation
- AI Proactive Alerts query
"""

import os
import sys
import json
from decimal import Decimal
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from typing import Dict, Any

from escrow_engine import (
    EscrowOrder,
    EscrowState,
    PassThroughFeeCalculator,
    FeeSplitPolicy
)
from qr_engine import SecureTokenEngine, generate_qr_svg_placeholder
from ai_assistant import ProactiveAIEngine

SECRET_KEY = "validbridge-production-signing-key-secret"
token_engine = SecureTokenEngine(secret_key=SECRET_KEY, base_url="https://validbridge.com")

# In-memory storage for demonstration / prototype
ORDERS_DB: Dict[str, EscrowOrder] = {}
CATALOG_ITEMS = [
    {
        "id": "prod-101",
        "title": "Industrial Grade Solar Inverters (50kW)",
        "supplier_id": "supp-001",
        "supplier_name": "Apex Clean Energy Ltd",
        "supplier_jurisdiction": "DEU",
        "verified_badge": True,
        "unit_price_usd": 4200.00,
        "moq": 10
    },
    {
        "id": "prod-102",
        "title": "Medical Grade Nitrile Gloves (Box of 1000)",
        "supplier_id": "supp-002",
        "supplier_name": "MediSafe Global Supplies",
        "supplier_jurisdiction": "MYS",
        "verified_badge": True,
        "unit_price_usd": 68.50,
        "moq": 500
    },
    {
        "id": "prod-103",
        "title": "High-Torque EV Motor Assemblies",
        "supplier_id": "supp-003",
        "supplier_name": "ElectraDrive Motion Corp",
        "supplier_jurisdiction": "JPN",
        "verified_badge": True,
        "unit_price_usd": 1850.00,
        "moq": 25
    }
]


def serialize_order(order: EscrowOrder) -> Dict[str, Any]:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "buyer_id": order.buyer_id,
        "supplier_id": order.supplier_id,
        "state": order.current_state.value,
        "fees": {
            "subtotal": str(order.fees["subtotal"]),
            "fee_percent": str(order.fees["fee_percent"]),
            "total_fee": str(order.fees["total_fee"]),
            "buyer_fee": str(order.fees["buyer_fee"]),
            "supplier_fee": str(order.fees["supplier_fee"]),
            "buyer_payable": str(order.fees["buyer_payable"]),
            "supplier_payout": str(order.fees["supplier_payout"]),
        },
        "funding_deadline": order.funding_deadline.isoformat(),
        "inspection_deadline": order.inspection_deadline.isoformat() if order.inspection_deadline else None,
        "history": order.state_machine.history
    }


class VettingBridgeAPIHandler(BaseHTTPRequestHandler):

    def _send_json(self, status_code: int, data: Any):
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_svg(self, status_code: int, svg_content: str):
        response_bytes = svg_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)

        # Healthcheck
        if path == "/health":
            self._send_json(200, {
                "service": "ValidBridge API (validbridge.com)",
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return

        # Serve Web UI
        if path == "/" or path == "/index.html":
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                index_path = os.path.join(base_dir, "index.html")
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self._send_json(500, {"error": f"Failed to load UI: {str(e)}"})
                return

        # 1. Browsing & Catalog (Window-Shopping: $0 API / Escrow cost)
        if path == "/api/catalog":
            self._send_json(200, {
                "zero_cost_window_shopping": True,
                "count": len(CATALOG_ITEMS),
                "items": CATALOG_ITEMS
            })
            return

        # 2. Get Single Order Details
        if path.startswith("/api/orders/") and len(path.split("/")) == 4:
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            self._send_json(200, serialize_order(order))
            return

        # 3. AI Alerts for an order
        if path.startswith("/api/orders/") and path.endswith("/alerts"):
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            alerts = ProactiveAIEngine.evaluate_order(order)
            self._send_json(200, {"order_id": order_id, "active_alerts": alerts})
            return

        # 4. Cryptographic Link / Token Verification Endpoint
        if path == "/v1/verify":
            token_list = query_params.get("token")
            if not token_list or not token_list[0]:
                self._send_json(400, {"error": "Missing 'token' query parameter."})
                return
            token = token_list[0]
            try:
                verified_claims = token_engine.verify_token(token)
                self._send_json(200, {
                    "valid": True,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "token_data": verified_claims
                })
            except Exception as e:
                self._send_json(401, {"valid": False, "error": str(e)})
            return

        # 5. Render Vector QR Badge for a Token
        if path == "/api/qr/render":
            token_list = query_params.get("token")
            title = query_params.get("title", ["VERIFIED CREDENTIAL"])[0]
            if not token_list:
                self._send_json(400, {"error": "Missing 'token' query param."})
                return
            deep_link = f"https://validbridge.com/v1/verify?token={token_list[0]}"
            svg = generate_qr_svg_placeholder(deep_link, title)
            self._send_svg(200, svg)
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON payload: {str(e)}"})
            return

        # 1. Initiate Order (Just-in-Time trigger)
        if path == "/api/orders/initiate":
            buyer_id = body.get("buyer_id")
            supplier_id = body.get("supplier_id")
            subtotal = Decimal(str(body.get("subtotal", "1000.00")))
            fee_percent = Decimal(str(body.get("fee_percent", "2.00")))
            order_number = f"VB-{datetime.now().strftime('%Y%m%d')}-{len(ORDERS_DB)+101}"

            order = EscrowOrder(
                order_number=order_number,
                buyer_id=buyer_id,
                supplier_id=supplier_id,
                subtotal=subtotal,
                fee_percent=fee_percent,
                fee_policy=FeeSplitPolicy.BUYER_PAYS
            )
            ORDERS_DB[order.id] = order

            # Trigger JIT KYB Webhook simulation
            kyb_dispatch = {
                "event": "ORDER_INITIATED",
                "order_id": order.id,
                "buyer_id": buyer_id,
                "supplier_id": supplier_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "KYB_WEBHOOK_TRIGGERED"
            }

            self._send_json(201, {
                "order": serialize_order(order),
                "jit_webhook": kyb_dispatch
            })
            return

        # 2. Lock Funds in Escrow
        if path.startswith("/api/orders/") and path.endswith("/lock-funds"):
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            tx_ref = body.get("payment_tx_ref", f"tx_{int(datetime.now().timestamp())}")
            try:
                transition = order.lock_funds(payment_tx_ref=tx_ref)
                self._send_json(200, {
                    "message": "Funds locked successfully.",
                    "transition": transition,
                    "order": serialize_order(order)
                })
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        # 3. Dispatch Inspector (Generates single-use dynamic QR Token)
        if path.startswith("/api/orders/") and path.endswith("/dispatch-inspector"):
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            inspector_id = body.get("inspector_id", "insp-global-001")
            window_hours = int(body.get("inspection_window_hours", 72))

            try:
                transition = order.dispatch_inspection(
                    inspector_id=inspector_id,
                    inspection_window_hours=window_hours
                )
                # Generate dynamic single-use token for inspector
                token_data = token_engine.generate_token(
                    token_type="INSPECTOR_DISPATCH",
                    subject_id=order.id,
                    ttl_seconds=window_hours * 3600,
                    extra_claims={"inspector_id": inspector_id, "order_number": order.order_number}
                )
                self._send_json(200, {
                    "message": "Inspector dispatched.",
                    "transition": transition,
                    "order": serialize_order(order),
                    "inspector_qr_token": token_data
                })
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        # 4. Release Escrow Funds (Requires inspection proof)
        if path.startswith("/api/orders/") and path.endswith("/release-funds"):
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            proof_sha256 = body.get("proof_sha256")
            digital_signature = body.get("digital_signature")
            inspector_id = body.get("inspector_id")

            if not proof_sha256 or not digital_signature:
                self._send_json(400, {"error": "Both 'proof_sha256' and 'digital_signature' are required."})
                return

            try:
                transition = order.release_funds(
                    proof_sha256=proof_sha256,
                    digital_signature=digital_signature,
                    inspector_id=inspector_id or "insp-system"
                )
                self._send_json(200, {
                    "message": "Funds released to supplier.",
                    "transition": transition,
                    "order": serialize_order(order)
                })
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        # 5. Raise Dispute
        if path.startswith("/api/orders/") and path.endswith("/dispute"):
            order_id = path.split("/")[3]
            order = ORDERS_DB.get(order_id)
            if not order:
                self._send_json(404, {"error": "Order not found."})
                return
            reason = body.get("reason", "Unspecified dispute")
            reporter_id = body.get("reporter_id", "anonymous")
            try:
                transition = order.dispute(reason=reason, reporter_id=reporter_id)
                self._send_json(200, {
                    "message": "Order placed in DISPUTED state.",
                    "transition": transition,
                    "order": serialize_order(order)
                })
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        # 6. Generate Quick-Pass or Facility QR Token
        if path == "/api/qr/generate":
            token_type = body.get("token_type", "QUICK_PASS")
            subject_id = body.get("subject_id")
            ttl_seconds = int(body.get("ttl_seconds", 86400))
            if not subject_id:
                self._send_json(400, {"error": "'subject_id' is required."})
                return
            token_res = token_engine.generate_token(
                token_type=token_type,
                subject_id=subject_id,
                ttl_seconds=ttl_seconds,
                extra_claims=body.get("claims")
            )
            self._send_json(201, token_res)
            return

        self._send_json(404, {"error": "Not Found"})


def run_server(port: int = None):
    if port is None:
        port = int(os.environ.get("PORT", 8080))
    # Bind to 0.0.0.0 on Render / Cloud so external traffic is accepted
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, VettingBridgeAPIHandler)
    print(f"[ValidBridge] Server running on port {port} (validbridge.com / Render)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[ValidBridge] Server stopping...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()

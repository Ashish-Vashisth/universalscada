import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler


def fingerprint(value: str) -> str:
    if not value:
        return "EMPTY"

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:12]


class handler(BaseHTTPRequestHandler):

    def send_json(self, status_code: int, payload: dict):
        body = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def perform_check(self):
        expected_secret_raw = os.environ.get(
            "CRON_SECRET",
            ""
        )

        authorization_raw = self.headers.get(
            "Authorization",
            ""
        )

        expected_secret = expected_secret_raw.strip()
        authorization = authorization_raw.strip()

        received_secret = ""

        if authorization.startswith("Bearer "):
            received_secret = authorization[7:].strip()

        expected_fingerprint = fingerprint(
            expected_secret
        )

        received_fingerprint = fingerprint(
            received_secret
        )

        diagnostics = {
            "cron_secret_configured": bool(
                expected_secret
            ),
            "expected_secret_length": len(
                expected_secret
            ),
            "authorization_header_received": bool(
                authorization
            ),
            "bearer_prefix_correct": (
                authorization.startswith("Bearer ")
            ),
            "received_secret_length": len(
                received_secret
            ),
            "expected_fingerprint": (
                expected_fingerprint
            ),
            "received_fingerprint": (
                received_fingerprint
            ),
            "values_match": (
                bool(expected_secret)
                and expected_fingerprint
                == received_fingerprint
            ),
        }

        self.send_json(
            200,
            {
                "ok": True,
                "message": (
                    "Authentication comparison completed. "
                    "No secret value is displayed."
                ),
                "diagnostics": diagnostics,
            }
        )

    def do_GET(self):
        self.perform_check()

    def do_POST(self):
        self.perform_check()

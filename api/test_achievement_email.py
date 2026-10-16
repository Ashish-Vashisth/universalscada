import json
import os
from http.server import BaseHTTPRequestHandler

import resend


def split_email_addresses(value: str) -> listif not value:
    if not value:
        return []

    return [
        email.strip()
        for email in value.split(",")
        if email.strip()
    ]


class handler(BaseHTTPRequestHandler):

    def send_json(self, status_code: int, payload: dict):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()
        self.wfile.write(body)

    def is_authorized(self) -> bool:
        expected_secret = os.environ.get(
            "CRON_SECRET",
            "",
        ).strip()

        authorization = self.headers.get(
            "Authorization",
            "",
        ).strip()

        return (
            bool(expected_secret)
            and authorization
            == f"Bearer {expected_secret}"
        )

    def do_GET(self):
        self.send_json(
            405,
            {
                "ok": False,
                "error": "Method not allowed. Use POST.",
            },
        )

    def do_POST(self):
        if not self.is_authorized():
            self.send_json(
                401,
                {
                    "ok": False,
                    "error": "Unauthorized",
                },
            )
            return

        try:
            resend_api_key = os.environ.get(
                "RESEND_API_KEY",
                "",
            ).strip()

            email_from = os.environ.get(
                "ALERT_EMAIL_FROM",
                "",
            ).strip()

            email_to = split_email_addresses(
                os.environ.get(
                    "ALERT_EMAIL_TO",
                    "",
                )
            )

            email_cc = split_email_addresses(
                os.environ.get(
                    "ALERT_EMAIL_CC",
                    "",
                )
            )

            reply_to = os.environ.get(
                "ALERT_EMAIL_REPLY_TO",
                "",
            ).strip()

            missing_variables = []

            if not resend_api_key:
                missing_variables.append(
                    "RESEND_API_KEY"
                )

            if not email_from:
                missing_variables.append(
                    "ALERT_EMAIL_FROM"
                )

            if not email_to:
                missing_variables.append(
                    "ALERT_EMAIL_TO"
                )

            if missing_variables:
                self.send_json(
                    500,
                    {
                        "ok": False,
                        "error": (
                            "Required environment variables "
                            "are missing."
                        ),
                        "missing_variables": (
                            missing_variables
                        ),
                    },
                )
                return

            resend.api_key = resend_api_key

            district = "Ayodhya"
            report_date = "13 October 2026"

            subject = (
                "Achievement Update: "
                f"{district} Achieved Zero "
                "Inactive/Disconnected Sites"
            )

            text_body = (
                "Dear Team,\n\n"
                "Achievement Update: "
                f"{district} district has achieved a "
                "Zero/Inactive or Disconnected Site "
                f"count of '0' dated {report_date}.\n\n"
                "This is an automatically generated "
                "notification based on the daily "
                "monitoring report.\n\n"
                "Regards\n"
                "Instrumentation & Automation Team"
            )

   ml_body = f"""
            <div style="
                font-family: Arial, Helvetica, sans-serif;
                font-size: 15px;
                line-height: 1.6;
                color: #111827;
            ">
                <p>Dear Team,</p>

                <p>
                    <strong>Achievement Update:</strong>
                    {district} district has achieved a
                    Zero/Inactive or Disconnected Site
                    count of <strong>'0'</strong> dated
                    {report_date}.
                </p>

                <p>
                    This is an automatically generated
                    notification based on the daily
                    monitoring report.
                </p>

                <p>
                    Regards<br>
                    Instrumentation &amp; Automation Team
                </p>
            </div>
            """

            email_params = {
                "from": email_from,
                "to": email_to,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }

            if email_cc:
                email_params["cc"] = email_cc

            if reply_to:
                email_params["reply_to"] = reply_to

            response = resend.Emails.send(
                email_params
            )

            provider_id = None

            if isinstance(response, dict):
                provider_id = response.get("id")
            else:
                provider_id = getattr(
                    response,
                    "id",
                    None,
                )

            self.send_json(
                200,
                {
                    "ok": True,
                    "message": (
                        "Test achievement email "
                        "submitted successfully."
                    ),
                    "email_provider_id": provider_id,
                    "to_recipient_count": len(
                        email_to
                    ),
                    "cc_recipient_count": len(
                        email_cc
                    ),
                },
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                },
            )

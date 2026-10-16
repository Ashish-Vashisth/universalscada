import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler

import resend


ALLOWED_DISTRICTS = {
    "ayodhya": {
        "display_name": "Ayodhya",
        "to_variable": "ALERT_EMAIL_TO_AYODHYA",
        "cc_variable": "ALERT_EMAIL_CC_AYODHYA",
    },
    "sultanpur": {
        "display_name": "Sultanpur",
        "to_variable": "ALERT_EMAIL_TO_SULTANPUR",
        "cc_variable": "ALERT_EMAIL_CC_SULTANPUR",
    },
    "deoria": {
        "display_name": "Deoria",
        "to_variable": "ALERT_EMAIL_TO_DEORIA",
        "cc_variable": "ALERT_EMAIL_CC_DEORIA",
    },
}


def split_email_addresses(value: str) -> list:
    """
    Converts comma-separated email addresses into a clean list.
    """

    if not value:
        return []

    return [
        email.strip()
        for email in value.split(",")
        if email.strip()
    ]


def remove_duplicate_addresses(addresses: list) -> list:
    """
    Removes duplicate email addresses while preserving order.
    Email matching is case-insensitive.
    """

    unique_addresses = []
    seen_addresses = set()

    for address in addresses:
        normalized_address = address.strip().lower()

        if (
            normalized_address
            and normalized_address not in seen_addresses
        ):
            seen_addresses.add(normalized_address)
            unique_addresses.append(address.strip())

    return unique_addresses


class handler(BaseHTTPRequestHandler):

    def send_json(
        self,
        status_code: int,
        payload: dict,
    ):
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
        """
        Checks whether the request contains the correct
        CRON_SECRET as a Bearer token.
        """

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

    def read_json_body(self) -> dict:
        """
        Reads and validates the JSON request body.
        """

        content_length_value = self.headers.get(
            "Content-Length",
            "0",
        )

        try:
            content_length = int(content_length_value)
        except ValueError:
            content_length = 0

        if content_length <= 0:
            return {}

        raw_body = self.rfile.read(content_length)

        if not raw_body:
            return {}

        return json.loads(
            raw_body.decode("utf-8")
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
            request_data = self.read_json_body()

            district_input = str(
                request_data.get(
                    "district",
                    "",
                )
            ).strip()

            if not district_input:
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": (
                            "The district field is required."
                        ),
                        "allowed_districts": [
                            "Ayodhya",
                            "Sultanpur",
                            "Deoria",
                        ],
                    },
                )
                return

            district_key = district_input.lower()

            if district_key not in ALLOWED_DISTRICTS:
                self.send_json(
                    400,
                    {
                        "ok": False,
                        "error": (
                            "The district is not supported."
                        ),
                        "received_district": district_input,
                        "allowed_districts": [
                            "Ayodhya",
                            "Sultanpur",
                            "Deoria",
                        ],
                    },
                )
                return

            district_configuration = (
                ALLOWED_DISTRICTS[district_key]
            )

            district = district_configuration[
                "display_name"
            ]

            report_date = str(
                request_data.get(
                    "report_date",
                    "",
                )
            ).strip()

            if not report_date:
                report_date = datetime.now().strftime(
                    "%d %B %Y"
                )

            resend_api_key = os.environ.get(
                "RESEND_API_KEY",
                "",
            ).strip()

            email_from = os.environ.get(
                "ALERT_EMAIL_FROM",
                "",
            ).strip()

            reply_to = os.environ.get(
                "ALERT_EMAIL_REPLY_TO",
                "",
            ).strip()

            district_to_variable = (
                district_configuration["to_variable"]
            )

            district_cc_variable = (
                district_configuration["cc_variable"]
            )

            email_to = split_email_addresses(
                os.environ.get(
                    district_to_variable,
                    "",
                )
            )

            common_cc = split_email_addresses(
                os.environ.get(
                    "ALERT_EMAIL_CC",
                    "",
                )
            )

            district_specific_cc = (
                split_email_addresses(
                    os.environ.get(
                        district_cc_variable,
                        "",
                    )
                )
            )

            email_to = remove_duplicate_addresses(
                email_to
            )

            email_cc = remove_duplicate_addresses(
                common_cc + district_specific_cc
            )

            to_addresses_lowercase = {
                address.lower()
                for address in email_to
            }

            email_cc = [
                address
                for address in email_cc
                if address.lower()
                not in to_addresses_lowercase
            ]

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
                    district_to_variable
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
                        "district": district,
                        "missing_variables": (
                            missing_variables
                        ),
                    },
                )
                return

            resend.api_key = resend_api_key

            subject = (
                "Achievement Update: "
                f"{district} Achieved Zero "
                "Inactive/Disconnected Sites"
            )

            text_body = (
                "Dear Team,\n\n"
                "Achievement Update-JJM SWSM: "
                f"{district} district has successfully achieved a "
                "Zero/Inactive/Disconnected OHT "
                f"bringing the count down to '0' {report_date}.\n\n"
                "This is an automatically generated "
                "notification based on the daily "
                "monitoring report.\n\n"
                "Regards\n"
                "Instrumentation & Automation Team"
            )

            html_body = f"""
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
                    "district": district,
                    "report_date": report_date,
                    "email_provider_id": provider_id,
                    "to_recipient_count": len(
                        email_to
                    ),
                    "cc_recipient_count": len(
                        email_cc
                    ),
                },
            )

        except json.JSONDecodeError:
            self.send_json(
                400,
                {
                    "ok": False,
                    "error": (
                        "Invalid JSON request body."
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

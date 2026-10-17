import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import resend

from api.daily_zero_sites import (
    DISTRICT_URLS,
    find_col_contains,
    flatten_columns,
    normalize_columns,
    read_source_from_url,
)


AYODHYA_THRESHOLD = 151
SULTANPUR_THRESHOLD = 115

ALERT_TYPE = "PORTAL_DISCONNECTION"
ALERT_DISTRICT = "ALL_DISTRICTS"


def split_email_addresses(value: str) -> list:
    if not value:
        return []

    return [
        email.strip()
        for email in value.split(",")
        if email.strip()
    ]


def remove_duplicate_addresses(addresses: list) -> list:
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


def get_supabase_settings() -> tuple:
    supabase_url = os.environ.get(
        "SUPABASE_URL",
        "",
    ).strip().rstrip("/")

    service_role_key = os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY",
        "",
    ).strip()

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is not configured."
        )

    if not service_role_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not configured."
        )

    return supabase_url, service_role_key


def get_supabase_headers(
    service_role_key: str,
) -> dict:
    return {
        "apikey": service_role_key,
        "Authorization": (
            f"Bearer {service_role_key}"
        ),
        "Content-Type": "application/json",
    }


def notification_already_sent(
    alert_date: str,
) -> bool:
    supabase_url, service_role_key = (
        get_supabase_settings()
    )

    endpoint = (
        f"{supabase_url}/rest/v1/"
        "email_notification_history"
    )

    params = {
        "select": "id",
        "alert_date": f"eq.{alert_date}",
        "alert_type": f"eq.{ALERT_TYPE}",
        "district": f"eq.{ALERT_DISTRICT}",
        "limit": "1",
    }

    response = requests.get(
        endpoint,
        headers=get_supabase_headers(
            service_role_key
        ),
        params=params,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "Could not check notification history. "
            f"Supabase status {response.status_code}: "
            f"{response.text}"
        )

    return bool(response.json())


def save_notification_marker(
    alert_date: str,
    email_provider_id,
):
    supabase_url, service_role_key = (
        get_supabase_settings()
    )

    endpoint = (
        f"{supabase_url}/rest/v1/"
        "email_notification_history"
        "?on_conflict=alert_date,alert_type,district"
    )

    headers = get_supabase_headers(
        service_role_key
    )

    headers["Prefer"] = (
        "resolution=ignore-duplicates,"
        "return=minimal"
    )

    payload = {
        "alert_date": alert_date,
        "alert_type": ALERT_TYPE,
        "district": ALERT_DISTRICT,
        "email_provider_id": email_provider_id,
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "Email was submitted, but the notification "
            "marker could not be saved. "
            f"Supabase status {response.status_code}: "
            f"{response.text}"
        )


def calculate_today_zero_count(
    source_df: pd.DataFrame,
) -> int:
    """
    Calculates TODAY ZERO SITES using the same rule
    as the Streamlit dashboard:

    Valid Scheme ID and Scheme Name
    AND
    Today Water Production is zero or blank.
    """

    df = flatten_columns(source_df)
    norm = normalize_columns(df)

    scheme_id_col = find_col_contains(
        norm,
        "schemeid",
    )

    scheme_name_col = find_col_contains(
        norm,
        "schemename",
    )

    today_prod_col = find_col_contains(
        norm,
        "today",
        "waterproduction",
        "meter3",
    )

    work_df = df[
        [
            scheme_id_col,
            scheme_name_col,
            today_prod_col,
        ]
    ].copy()

    work_df.columns = [
        "Scheme Id",
        "Scheme Name",
        "Today Water Production",
    ]

    work_df["Today Water Production"] = (
        pd.to_numeric(
            work_df["Today Water Production"],
            errors="coerce",
        )
    )

    valid_scheme = (
        work_df["Scheme Id"].notna()
        & work_df["Scheme Name"].notna()
        & (
            work_df["Scheme Id"]
            .astype(str)
            .str.strip()
            .str.lower()
            != "none"
        )
        & (
            work_df["Scheme Name"]
            .astype(str)
            .str.strip()
            .str.lower()
            != "none"
        )
        & (
            work_df["Scheme Id"]
            .astype(str)
            .str.strip()
            != ""
        )
        & (
            work_df["Scheme Name"]
            .astype(str)
            .str.strip()
            != ""
        )
    )

    today_zero_mask = (
        valid_scheme
        & (
            work_df["Today Water Production"]
            .fillna(0)
            == 0
        )
    )

    today_zero_df = work_df.loc[
        today_zero_mask
    ].copy()

    today_zero_df = (
        today_zero_df.drop_duplicates(
            subset=["Scheme Id"],
            keep="first",
        )
    )

    return len(today_zero_df)


def send_disconnection_email(
    report_date_display: str,
) -> dict:
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

    email_to = split_email_addresses(
        os.environ.get(
            "PORTAL_DISCONNECTION_EMAIL_TO",
            "",
        )
    )

    email_cc = split_email_addresses(
        os.environ.get(
            "PORTAL_DISCONNECTION_EMAIL_CC",
            "",
        )
    )

    email_to = remove_duplicate_addresses(
        email_to
    )

    email_cc = remove_duplicate_addresses(
        email_cc
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
            "PORTAL_DISCONNECTION_EMAIL_TO"
        )

    if missing_variables:
        raise RuntimeError(
            "Required environment variables "
            "are missing: "
            + ", ".join(missing_variables)
        )

    resend.api_key = resend_api_key

    subject = (
        "JJM Portal Disconnection Alert - "
        "Ayodhya, Sultanpur and Deoria"
    )

    text_body = (
        "Dear Team,\n\n"
        "The Entire Sites of Ayodhya, Sultanpur "
        "and Deoria appears to be disconnected "
        "at JJM Portal dated "
        f"{report_date_display}. "
        "Please prioritize a review of this issue "
        "to ensure a timely resolution.\n\n"
        "This is an automatically generated "
        "notification based on the live "
        "monitoring status.\n\n"
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
            The Entire Sites of Ayodhya, Sultanpur
            and Deoria appears to be disconnected
            at JJM Portal dated
            {report_date_display}.
            Please prioritize a review of this
            issue to ensure a timely resolution.
        </p>

        <p>
            This is an automatically generated
            notification based on the live
            monitoring status.
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

    if isinstance(response, dict):
        provider_id = response.get("id")
    else:
        provider_id = getattr(
            response,
            "id",
            None,
        )

    if not provider_id:
        raise RuntimeError(
            "Resend did not return an email provider ID."
        )

    return {
        "provider_id": provider_id,
        "to_recipient_count": len(email_to),
        "cc_recipient_count": len(email_cc),
    }


def run_portal_disconnection_check() -> dict:
    now_ist = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    alert_date = now_ist.date().isoformat()

    report_date_display = now_ist.strftime(
        "%d %B %Y"
    )

    ayodhya_df = read_source_from_url(
        DISTRICT_URLS["AYODHYA"]
    )

    sultanpur_df = read_source_from_url(
        DISTRICT_URLS["SULTANPUR"]
    )

    ayodhya_count = calculate_today_zero_count(
        ayodhya_df
    )

    sultanpur_count = calculate_today_zero_count(
        sultanpur_df
    )

    ayodhya_condition = (
        ayodhya_count >= AYODHYA_THRESHOLD
    )

    sultanpur_condition = (
        sultanpur_count
        >= SULTANPUR_THRESHOLD
    )

    both_conditions_satisfied = (
        ayodhya_condition
        and sultanpur_condition
    )

    result = {
        "alert_date": alert_date,
        "report_date": report_date_display,
        "alert_type": ALERT_TYPE,
        "today_zero_sites": {
            "AYODHYA": {
                "count": ayodhya_count,
                "threshold": AYODHYA_THRESHOLD,
                "condition_satisfied": (
                    ayodhya_condition
                ),
            },
            "SULTANPUR": {
                "count": sultanpur_count,
                "threshold": SULTANPUR_THRESHOLD,
                "condition_satisfied": (
                    sultanpur_condition
                ),
            },
        },
        "both_conditions_satisfied": (
            both_conditions_satisfied
        ),
        "email_status": "NOT_SENT",
    }

    if not both_conditions_satisfied:
        result["email_status"] = (
            "CONDITIONS_NOT_SATISFIED"
        )

        result["message"] = (
            "The combined disconnection condition "
            "was not satisfied."
        )

        return result

    if notification_already_sent(
        alert_date=alert_date
    ):
        result["email_status"] = (
            "ALREADY_SENT"
        )

        result["message"] = (
            "Today's portal disconnection email "
            "has already been sent."
        )

        return result

    email_result = send_disconnection_email(
        report_date_display=report_date_display
    )

    save_notification_marker(
        alert_date=alert_date,
        email_provider_id=(
            email_result["provider_id"]
        ),
    )

    result["email_status"] = "EMAIL_SENT"

    result["email_provider_id"] = (
        email_result["provider_id"]
    )

    result["to_recipient_count"] = (
        email_result["to_recipient_count"]
    )

    result["cc_recipient_count"] = (
        email_result["cc_recipient_count"]
    )

    result["message"] = (
        "Portal disconnection email submitted "
        "successfully."
    )

    return result


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

    def execute_check(self):
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
            result = (
                run_portal_disconnection_check()
            )

            self.send_json(
                200,
                {
                    "ok": True,
                    **result,
                },
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                },
            )

    def do_GET(self):
        self.execute_check()

    def do_POST(self):
        self.execute_check()


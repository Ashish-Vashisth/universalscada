import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

import requests
import resend

from api.daily_zero_sites import (
    DISTRICT_URLS,
    build_zero_sites,
    read_source_from_url,
)


DISTRICT_CONFIG = {
    "AYODHYA": {
        "display_name": "Ayodhya",
        "to_variable": "ALERT_EMAIL_TO_AYODHYA",
        "cc_variable": "ALERT_EMAIL_CC_AYODHYA",
    },
    "SULTANPUR": {
        "display_name": "Sultanpur",
        "to_variable": "ALERT_EMAIL_TO_SULTANPUR",
        "cc_variable": "ALERT_EMAIL_CC_SULTANPUR",
    },
    "DEORIA": {
        "display_name": "Deoria",
        "to_variable": "ALERT_EMAIL_TO_DEORIA",
        "cc_variable": "ALERT_EMAIL_CC_DEORIA",
    },
}


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
    alert_type: str,
    district: str,
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
        "alert_type": f"eq.{alert_type}",
        "district": f"eq.{district}",
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

    records = response.json()

    return bool(records)


def save_notification_marker(
    alert_date: str,
    alert_type: str,
    district: str,
    email_provider_id,
):
    supabase_url, service_role_key = (
        get_supabase_settings()
    )

    endpoint = (
        f"{supabase_url}/rest/v1/"
        "email_notification_history"
    )

    headers = get_supabase_headers(
        service_role_key
    )

    headers["Prefer"] = (
        "return=minimal,"
        "resolution=ignore-duplicates"
    )

    payload = {
        "alert_date": alert_date,
        "alert_type": alert_type,
        "district": district,
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


def send_achievement_email(
    district_key: str,
    report_date_display: str,
):
    configuration = DISTRICT_CONFIG[
        district_key
    ]

    district = configuration[
        "display_name"
    ]

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

    district_to_variable = configuration[
        "to_variable"
    ]

    district_cc_variable = configuration[
        "cc_variable"
    ]

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
        raise RuntimeError(
            "Required environment variables "
            "are missing: "
            + ", ".join(missing_variables)
        )

    resend.api_key = resend_api_key

    subject = (
        "Achievement Update - JJM SWSM: "
        f"{district} Achieved Zero "
        "Inactive/Disconnected Sites"
    )

    text_body = (
        "Dear Team,\n\n"
        "Achievement Update - JJM SWSM: "
        f"{district} district has achieved a "
        "Zero/Inactive or Disconnected Site "
        f"count of '0' dated "
        f"{report_date_display}.\n\n"
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
            <strong>
                Achievement Update - JJM SWSM:
            </strong>
            {district} district has achieved a
            Zero/Inactive or Disconnected Site
            count of <strong>'0'</strong> dated
            {report_date_display}.
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

    if isinstance(response, dict):
        provider_id = response.get("id")
    else:
        provider_id = getattr(
            response,
            "id",
            None,
        )

    return {
        "provider_id": provider_id,
        "to_recipient_count": len(email_to),
        "cc_recipient_count": len(email_cc),
    }


def run_zero_achievement_monitor() -> dict:
    now_ist = datetime.now(
        ZoneInfo("Asia/Kolkata")
    )

    alert_date = now_ist.date().isoformat()

    report_date_display = now_ist.strftime(
        "%d %B %Y"
    )

    result = {
        "alert_date": alert_date

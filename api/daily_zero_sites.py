import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests


DISTRICT_URLS = {
    "AYODHYA": (
        "https://jjm.up.gov.in/SKADA/"
        "Web_SKADA_DIstrict_Agency_Dashboard"
        "?DistrictId=503"
        "&AgencyId=127"
        "&Header=Automation%20System%20Ayodhya%20(UNIVERSAL%20MEP)"
    ),
    "SULTANPUR": (
        "https://jjm.up.gov.in/SKADA/"
        "Web_SKADA_DIstrict_Agency_Dashboard"
        "?DistrictId=505"
        "&AgencyId=127"
        "&Header=Automation%20System%20Sultanpur%20(UNIVERSAL%20MEP)"
    ),
    "DEORIA": (
        "https://jjm.up.gov.in/SKADA/"
        "Web_SKADA_DIstrict_Agency_Dashboard"
        "?DistrictId=516"
        "&AgencyId=127"
        "&Header=Automation%20System%20Deoria%20(UNIVERSAL%20MEP)"
    ),
}


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(
                str(value)
                for value in column_tuple
                if pd.notna(value)
            ).strip()
            for column_tuple in df.columns
        ]

    return df


def normalize_columns(df: pd.DataFrame) -> dict:
    return {
        column: re.sub(r"\s+", "", str(column)).strip().lower()
        for column in df.columns
    }


def find_col_contains(norm_map: dict, *needles: str) -> str:
    for original_column, normalized_column in norm_map.items():
        if all(needle in normalized_column for needle in needles):
            return original_column

    raise KeyError(
        f"Missing column containing fragments: {needles}"
    )


def clean_scheme_id(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    return text


def json_safe_number(value):
    if pd.isna(value):
        return None

    return float(value)


def read_source_from_url(url: str) -> pd.DataFrame:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/129.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=90
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    if not tables:
        raise ValueError(
            "No HTML tables were found on the district dashboard."
        )

    candidates = [
        table
        for table in tables
        if table.shape[1] >= 20
    ]

    if candidates:
        df = max(
            candidates,
            key=lambda table: table.shape[0] * table.shape[1]
        )
    else:
        df = max(
            tables,
            key=lambda table: table.shape[0] * table.shape[1]
        )

    df = flatten_columns(df)

    if df.empty:
        raise ValueError(
            "The selected district dashboard returned an empty table."
        )

    return df


def build_zero_sites(df: pd.DataFrame) -> pd.DataFrame:
    """
    Exact ZERO/INACTIVE logic copied from the Streamlit app:

    1. Scheme ID and Scheme Name must be valid.
    2. Yesterday and Today must not both be originally blank.
    3. Yesterday production must be zero.
    4. Today production must be zero.
    """

    df = flatten_columns(df)
    norm = normalize_columns(df)

    scheme_id_col = find_col_contains(norm, "schemeid")
    scheme_name_col = find_col_contains(norm, "schemename")
    today_prod_col = find_col_contains(
        norm,
        "today",
        "waterproduction",
        "meter3"
    )
    last_date_col = find_col_contains(
        norm,
        "lastdatareceivedate"
    )

    yesterday_prod_col = None

    for original_column, normalized_column in norm.items():
        if (
            "oht" in normalized_column
            and "watersupply" in normalized_column
            and "meter3" in normalized_column
            and "yesterday" in normalized_column
        ):
            yesterday_prod_col = original_column
            break

    if yesterday_prod_col is None:
        raise KeyError(
            "Could not find the OHT Water Supply Yesterday column."
        )

    work_df = df[
        [
            scheme_id_col,
            scheme_name_col,
            yesterday_prod_col,
            today_prod_col,
            last_date_col,
        ]
    ].copy()

    work_df.columns = [
        "Scheme Id",
        "Scheme Name",
        "Yesterday Water Production (m^3)",
        "Today Water Production (m^3)",
        "Last Data Receive Date",
    ]

    work_df["Yesterday Water Production (m^3)"] = pd.to_numeric(
        work_df["Yesterday Water Production (m^3)"],
        errors="coerce",
    )

    work_df["Today Water Production (m^3)"] = pd.to_numeric(
        work_df["Today Water Production (m^3)"],
        errors="coerce",
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

    both_originally_blank = (
        work_df["Yesterday Water Production (m^3)"].isna()
        & work_df["Today Water Production (m^3)"].isna()
    )

    zero_mask = (
        valid_scheme
        & ~both_originally_blank
        & (
            work_df["Yesterday Water Production (m^3)"]
            .fillna(0)
            == 0
        )
        & (
            work_df["Today Water Production (m^3)"]
            .fillna(0)
            == 0
        )
    )

    zero_df = work_df.loc[zero_mask].copy()

    zero_df["Scheme Id"] = zero_df["Scheme Id"].apply(
        clean_scheme_id
    )

    zero_df["Scheme Name"] = (
        zero_df["Scheme Name"]
        .astype(str)
        .str.strip()
    )

    zero_df["Last Data Receive Date"] = (
        zero_df["Last Data Receive Date"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    zero_df["Site Status"] = "ZERO/INACTIVE SITE"

    zero_df = zero_df.drop_duplicates(
        subset=["Scheme Id"],
        keep="first"
    )

    zero_df.reset_index(drop=True, inplace=True)

    return zero_df


def dataframe_to_records(zero_df: pd.DataFrame) -> list:
    records = []

    for _, row in zero_df.iterrows():
        records.append(
            {
                "scheme_id": clean_scheme_id(row["Scheme Id"]),
                "scheme_name": str(row["Scheme Name"]).strip(),
                "yesterday_water_production": json_safe_number(
                    row["Yesterday Water Production (m^3)"]
                ),
                "today_water_production": json_safe_number(
                    row["Today Water Production (m^3)"]
                ),
                "last_data_receive_date": str(
                    row["Last Data Receive Date"]
                ).strip(),
                "site_status": "ZERO/INACTIVE SITE",
            }
        )

    return records


def save_district_snapshot(
    report_date: str,
    district: str,
    records: list
) -> int:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    rpc_url = (
        f"{supabase_url}/rest/v1/rpc/"
        "replace_daily_zero_sites"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }

    body = {
        "p_report_date": report_date,
        "p_district": district,
        "p_sites": records,
    }

    response = requests.post(
        rpc_url,
        headers=headers,
        json=body,
        timeout=90,
    )

    if not response.ok:
        raise RuntimeError(
            f"Supabase RPC failed with status "
            f"{response.status_code}: {response.text}"
        )

    result = response.json()

    if isinstance(result, int):
        return result

    return len(records)


def save_failure_summary(
    report_date: str,
    district: str,
    error_message: str
):
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    endpoint = (
        f"{supabase_url}/rest/v1/"
        "daily_zero_site_summary"
        "?on_conflict=report_date,district"
    )

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    payload = {
        "report_date": report_date,
        "district": district,
        "zero_site_count": 0,
        "run_status": "FAILED",
        "error_message": error_message[:1000],
        "captured_at": datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).isoformat(),
    }

    requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=30,
    )


def run_daily_collection(report_date: str = None) -> dict:
    if not report_date:
        report_date = datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).date().isoformat()

    overall_result = {
        "report_date": report_date,
        "districts": {},
        "success_count": 0,
        "failure_count": 0,
    }

    for district, url in DISTRICT_URLS.items():
        try:
            source_df = read_source_from_url(url)
            zero_df = build_zero_sites(source_df)
            records = dataframe_to_records(zero_df)

            saved_count = save_district_snapshot(
                report_date=report_date,
                district=district,
                records=records,
            )

            overall_result["districts"][district] = {
                "status": "SUCCESS",
                "zero_site_count": saved_count,
                "sites": [
                    {
                        "scheme_id": record["scheme_id"],
                        "scheme_name": record["scheme_name"],
                    }
                    for record in records
                ],
            }

            overall_result["success_count"] += 1

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"

            overall_result["districts"][district] = {
                "status": "FAILED",
                "zero_site_count": None,
                "error": error_message,
            }

            overall_result["failure_count"] += 1

            try:
                save_failure_summary(
                    report_date=report_date,
                    district=district,
                    error_message=error_message,
                )
            except Exception:
                pass

    return overall_result


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

    def get_auth_diagnostics(self) -> dict:
    expected_secret = os.environ.get("CRON_SECRET", "")
    authorization = self.headers.get("Authorization", "")

    expected_secret_clean = expected_secret.strip()
    authorization_clean = authorization.strip()

    return {
        "expected_secret_configured": bool(expected_secret),
        "expected_secret_length": len(expected_secret),
        "expected_secret_clean_length": len(expected_secret_clean),
        "received_header_present": bool(authorization),
        "received_header_length": len(authorization),
        "received_header_clean_length": len(authorization_clean),
        "received_bearer_prefix": authorization_clean.startswith("Bearer "),
    }


def is_authorized(self) -> bool:
    expected_secret = os.environ.get("CRON_SECRET", "").strip()
    authorization = self.headers.get("Authorization", "").strip()

    return (
        bool(expected_secret)
        and authorization == f"Bearer {expected_secret}"
    )

    def do_GET(self):
    if not self.is_authorized():
        self.send_json(
            401,
            {
                "ok": False,
                "error": "Unauthorized",
                "auth_diagnostics": self.get_auth_diagnostics(),
            },
        )
        return

        try:
            result = run_daily_collection()

            status_code = (
                200
                if result["failure_count"] == 0
                else 207
            )

            self.send_json(
                status_code,
                {"ok": True, **result},
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    def do_POST(self):
        if not self.is_authorized():
    self.send_json(
        401,
        {
            "ok": False,
            "error": "Unauthorized",
            "auth_diagnostics": self.get_auth_diagnostics(),
        },
    )
    return

        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )

            request_body = {}

            if content_length > 0:
                raw_body = self.rfile.read(content_length)
                request_body = json.loads(
                    raw_body.decode("utf-8")
                )

            report_date = request_body.get("report_date")

            if report_date:
                datetime.strptime(report_date, "%Y-%m-%d")

            result = run_daily_collection(
                report_date=report_date
            )

            status_code = (
                200
                if result["failure_count"] == 0
                else 207
            )

            self.send_json(
                status_code,
                {"ok": True, **result},
            )

        except ValueError:
            self.send_json(
                400,
                {
                    "ok": False,
                    "error": (
                        "report_date must use YYYY-MM-DD format."
                    ),
                },
            )

        except Exception as exc:
            self.send_json(
                500,
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

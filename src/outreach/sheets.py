"""Read and update the Outreach Tracker. Never creates tabs or headers."""

from __future__ import annotations

import os

from outreach.columns import HEADER_TO_KEY
from outreach.config import ConfigError, Settings
from outreach.models import Lead, SheetData, parse_grid

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._service = None
        self._columns: dict[str, int] = {}

    def load(self) -> SheetData:
        rows = self._values(f"{_quote(self.settings.worksheet)}!A1:T5000")
        data = parse_grid(rows)
        self._columns = _column_index(rows, data.header_row)
        return data

    def save(self, lead: Lead) -> None:
        if not lead.dirty:
            return
        payload = []
        for key in sorted(lead.dirty):
            column = self._columns.get(key)
            if column is None:
                continue
            cell = f"{_quote(self.settings.worksheet)}!{_letter(column)}{lead.row_number}"
            payload.append({"range": cell, "values": [[lead.values.get(key, "")]]})
        if not payload:
            return
        from googleapiclient.errors import HttpError

        try:
            self._api().spreadsheets().values().batchUpdate(
                spreadsheetId=self.settings.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": payload},
            ).execute()
        except HttpError as exc:
            raise ConfigError(f"Could not update row {lead.row_number}: {exc}") from exc
        lead.dirty.clear()

    def _values(self, range_name: str) -> list[list[object]]:
        from googleapiclient.errors import HttpError

        try:
            result = (
                self._api()
                .spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.settings.spreadsheet_id,
                    range=range_name,
                    valueRenderOption="FORMATTED_VALUE",
                )
                .execute()
            )
        except HttpError as exc:
            raise ConfigError(
                f"Could not read '{self.settings.worksheet}'. "
                "If the Grok bot has not created that tab yet, nothing was changed. "
                f"Google said: {exc}"
            ) from exc
        return result.get("values", [])

    def _api(self):
        if self._service is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
            if not path:
                raise ConfigError(
                    "Set GOOGLE_SERVICE_ACCOUNT_FILE to a service account JSON key, "
                    "and share the Client Leads spreadsheet with that account as Editor."
                )
            creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service


def _column_index(rows: list[list[object]], header_row: int | None) -> dict[str, int]:
    if header_row is None or header_row < 1 or header_row > len(rows):
        return {}
    mapping: dict[str, int] = {}
    for index, label in enumerate(rows[header_row - 1], start=1):
        key = HEADER_TO_KEY.get(str(label).strip().casefold())
        if key and key not in mapping:
            mapping[key] = index
    return mapping


def column_letter(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _letter(number: int) -> str:
    return column_letter(number)


def _quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"

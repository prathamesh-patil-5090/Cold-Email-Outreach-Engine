"""Rows from the Outreach Tracker, parsed without assuming the header row number."""

from __future__ import annotations

from dataclasses import dataclass, field

from outreach.columns import COLUMNS, HEADER_TO_KEY


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass
class Lead:
    row_number: int
    values: dict[str, str]
    present: set[str]
    dirty: set[str] = field(default_factory=set)

    def text(self, key: str) -> str:
        return self.values.get(key, "").strip()

    def set_field(self, key: str, value: str) -> None:
        if key not in self.present:
            raise KeyError(key)
        if self.values.get(key, "") == value:
            return
        self.values[key] = value
        self.dirty.add(key)

    @property
    def lead_id(self) -> str:
        return self.text("lead_id")

    @property
    def status(self) -> str:
        return self.text("outreach_status")

    @property
    def status_key(self) -> str:
        return self.status.casefold()

    @property
    def research_done(self) -> bool:
        return self.text("research_status").casefold() == "done"


@dataclass
class SheetData:
    """Parsed tab. `ready` is false when the Lead ID header is absent."""

    header_row: int | None
    leads: list[Lead]
    present: set[str]
    absent: list[str]

    @property
    def ready(self) -> bool:
        return "lead_id" in self.present and self.header_row is not None


def parse_grid(rows: list[list[object]], *, scan_rows: int = 30) -> SheetData:
    """Find the header row by the Lead ID label, wherever the Grok bot placed it."""
    width = max((len(row) for row in rows), default=0)
    padded = [_pad(row, width) for row in rows]
    header_index = _find_header(padded, scan_rows)
    if header_index is None:
        return SheetData(
            header_row=None,
            leads=[],
            present=set(),
            absent=list(COLUMNS.values()),
        )

    header = padded[header_index]
    index_by_key: dict[str, int] = {}
    for index, label in enumerate(header):
        key = HEADER_TO_KEY.get(_cell(label).casefold())
        if key and key not in index_by_key:
            index_by_key[key] = index
    present = set(index_by_key)
    absent = [name for key, name in COLUMNS.items() if key not in present]

    leads: list[Lead] = []
    blank_run = 0
    for offset, row in enumerate(padded[header_index + 1 :], start=header_index + 2):
        values = {key: _cell(row[index]) if index < len(row) else "" for key, index in index_by_key.items()}
        if not any(values.values()):
            blank_run += 1
            if blank_run >= 20:
                break
            continue
        blank_run = 0
        if not values.get("lead_id"):
            continue
        leads.append(Lead(row_number=offset, values=values, present=present))

    return SheetData(
        header_row=header_index + 1,
        leads=leads,
        present=present,
        absent=absent,
    )


def _pad(row: list[object], width: int) -> list[object]:
    items = list(row)
    if len(items) < width:
        items.extend([""] * (width - len(items)))
    return items


def _find_header(rows: list[list[object]], scan_rows: int) -> int | None:
    for index, row in enumerate(rows[:scan_rows]):
        labels = {_cell(cell).casefold() for cell in row}
        if "lead id" in labels:
            return index
    return None

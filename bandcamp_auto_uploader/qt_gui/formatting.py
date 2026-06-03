"""Formatting and validation helpers for the PySide migration."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN


def normalize_price(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    if text.startswith("$"):
        text = text[1:].strip()
    if not text or text == ".":
        return default
    if not re.fullmatch(r"(\d+|\d*\.\d{1,2}|\d+\.)", text):
        return default
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return default
    if amount < 0:
        return default
    amount = min(amount, Decimal("1000"))
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if amount == amount.to_integral():
        return str(int(amount))
    return f"{amount:.2f}"


def format_price(value: object, default: str = "") -> str:
    price = normalize_price(value, default=default)
    return f"${price}" if price else ""


def normalize_release_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return ""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return ""
    return text

import re
from typing import Optional

_LABELED_PATTERN = re.compile(
    r"(?:id|uv|ultraview(?:er)?)\s*[:=\-]?\s*"
    r"(\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}|\d{8,11})\b"
    r"[\s\S]{0,40}?"
    r"(?:pass(?:word)?|mk|mật\s*khẩu|pw|/|\|)\s*[:=\-]?\s*"
    r"([A-Za-z0-9@#$%!]{4,12})\b",
    re.IGNORECASE,
)

_PAIR_PATTERN = re.compile(
    r"\b(\d{2,3}[\s.\-]?\d{3}[\s.\-]?\d{3,4}|\d{8,11})\s*[/|]\s*([A-Za-z0-9@#$%!]{4,12})\b"
)


def normalize_uv_id(raw_id: str) -> str:
    """Strip spaces, dots, and dashes from an UltraViewer ID."""
    return re.sub(r"\D", "", raw_id or "")


def extract_ultraview_credentials(text: str) -> Optional[dict[str, str]]:
    """
    Detect UltraViewer ID (8-11 digits) and Pass (4-12 chars) from chat text.
    Supports formats like:
      - "id 68 412 903 pass 8492"
      - "ultraview: 68412903 / 8492"
      - "uv 68412903 mk 8492"
      - "68 412 903 / 8492"
    """
    if not text:
        return None

    for pattern in (_LABELED_PATTERN, _PAIR_PATTERN):
        match = pattern.search(text)
        if match:
            uv_id = normalize_uv_id(match.group(1))
            uv_pass = match.group(2).strip()
            if 8 <= len(uv_id) <= 11 and 4 <= len(uv_pass) <= 12:
                return {"id": uv_id, "pass": uv_pass}
    return None

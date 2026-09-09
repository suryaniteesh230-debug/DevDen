from __future__ import annotations

import re
import unicodedata


_EMAIL = re.compile(r"(?iu)\b[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}\b")
_PHONE_WORDS = re.compile(r"(?iu)\b(?:phone|mobile|whatsapp|aadhaar|aadhar|otp|email)\b|फोन|मोबाइल|आधार|ईमेल|फ़ोन|മൊബൈൽ|ഫോൺ|ആധാർ|ഇമെയിൽ")
_ADDRESS_WITH_NUMBER = re.compile(
    r"(?iu)(?:\b(?:house|flat|door|street|road|lane|ward|pin(?:code)?)\b|"
    r"मकान|फ्लैट|गली|सड़क|वार्ड|पिन|വീട്|ഫ്ലാറ്റ്|റോഡ്|വാർഡ്|പിൻ)"
    r".{0,40}\d"
)


def normalize_decimal_digits(value: str) -> str:
    output: list[str] = []
    for char in value:
        try:
            output.append(str(unicodedata.decimal(char)))
        except (TypeError, ValueError):
            output.append(char)
    return "".join(output)


def contains_high_risk_pii(value: str) -> bool:
    normalized = normalize_decimal_digits(unicodedata.normalize("NFKC", value))
    if _EMAIL.search(normalized) or _ADDRESS_WITH_NUMBER.search(normalized):
        return True
    digit_groups = [re.sub(r"\D", "", group) for group in re.findall(r"(?:\d[\s().+-]*){6,}", normalized)]
    if any(len(group) >= 10 for group in digit_groups):
        return True
    if _PHONE_WORDS.search(normalized) and any(len(group) >= 4 for group in digit_groups):
        return True
    return False


def conversation_contains_high_risk_pii(current: str, history: list[str]) -> bool:
    return contains_high_risk_pii(current) or any(contains_high_risk_pii(message) for message in history)

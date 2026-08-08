"""
Email, Order ID, and Package extraction module using regular expressions.
Parses, sanitizes, and normalizes email addresses, Order IDs, and package text from messages.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Standard Regex pattern for detecting email addresses
EMAIL_REGEX = re.compile(
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    re.IGNORECASE
)

# Regex pattern for extracting Order ID numbers (e.g. "Order ID: #10025", "Order #10025", "#10025", "Order ID 10025")
ORDER_ID_REGEX = re.compile(
    r'(?:order\s*id|order\s*#|order|#)\s*[:#\s]*(\d+)',
    re.IGNORECASE
)


def extract_email(text: Optional[str]) -> Optional[str]:
    """
    Extracts the first valid email address found in the provided text.
    Strips trailing punctuation and normalizes to lowercase.

    Args:
        text (str, optional): The input string to scan (message text or caption).

    Returns:
        Optional[str]: The normalized (lowercase, trimmed) email address if found, else None.
    """
    if not text:
        return None

    match = EMAIL_REGEX.search(text)
    if match:
        raw_email = match.group(0).strip()
        email = raw_email.rstrip(".,;!)]>").lower()
        logger.debug(f"Extracted email: '{email}' from text.")
        return email

    return None


def extract_order_id(text: Optional[str]) -> Optional[int]:
    """
    Extracts an Order ID integer from text or message captions.

    Args:
        text (str, optional): Input text string.

    Returns:
        Optional[int]: Order ID integer if found, else None.
    """
    if not text:
        return None

    match = ORDER_ID_REGEX.search(text)
    if match:
        try:
            order_id = int(match.group(1))
            logger.debug(f"Extracted Order ID: {order_id} from text.")
            return order_id
        except ValueError:
            pass

    return None


def extract_package(text: Optional[str]) -> str:
    """
    Extracts package/item description from customer message by stripping email line.

    Args:
        text (str, optional): Input order message text.

    Returns:
        str: Package text description or default fallback.
    """
    if not text:
        return "Standard Package"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    package_lines = []

    for line in lines:
        if EMAIL_REGEX.search(line):
            continue
        if line.lower().startswith(("package:", "item:", "order:")):
            package_lines.append(line.split(":", 1)[-1].strip())
        else:
            package_lines.append(line)

    if package_lines:
        return " | ".join(package_lines[:2])

    return "Standard Package"

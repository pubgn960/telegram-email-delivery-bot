"""
Email extraction module using regular expressions.
Parses, sanitizes, and normalizes email addresses from text and photo captions.
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
        # Strip trailing punctuation often attached in text (e.g. "email@domain.com.")
        email = raw_email.rstrip(".,;!)]>").lower()
        logger.debug(f"Extracted email: '{email}' from text.")
        return email

    return None

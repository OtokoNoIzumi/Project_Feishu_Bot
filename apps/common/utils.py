"""
Shared utilities for the application.
"""

import base64
from datetime import datetime
from typing import List, Optional

from fastapi import UploadFile


def decode_images_b64(images_b64: List[str]) -> List[bytes]:
    """
    Decode a list of Base64 strings to bytes, silently ignoring errors.

    Args:
        images_b64: List of Base64 strings.

    Returns:
        List of decoded bytes for valid strings.
    """
    out: List[bytes] = []
    for s in images_b64 or []:
        if not s:
            continue
        try:
            out.append(base64.b64decode(s))
        except (ValueError, TypeError):
            continue
    return out


def parse_occurred_at(oa_str: str) -> Optional[datetime]:
    """
    Parse occurrences string from LLM result.
    Supports 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD HH:MM'.
    """
    if not oa_str or not isinstance(oa_str, str):
        return None
    try:
        # Handle potential YYYY-MM-DD HH:MM if SS missing
        clean_str = oa_str.replace(" ", "T")
        if len(clean_str) == 16:  # YYYY-MM-DDTHH:MM
            clean_str += ":00"
        return datetime.fromisoformat(clean_str)
    except ValueError:
        return None


async def read_upload_files(images: List[UploadFile]) -> List[bytes]:
    """Read bytes from a list of UploadFiles, silently ignoring errors."""
    images_bytes: List[bytes] = []
    for f in images or []:
        try:
            images_bytes.append(await f.read())
        # pylint: disable=broad-exception-caught
        except Exception:
            continue
    return images_bytes

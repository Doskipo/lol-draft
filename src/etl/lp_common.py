"""Shared Leaguepedia plumbing: authenticated login + exponential backoff.

Import from any LP script:  from lp_common import lp_login, with_backoff
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from mwclient.errors import LoginError
from leaguepedia_parser.site.leaguepedia import leaguepedia

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def lp_login() -> None:
    """Authenticate against Leaguepedia with the bot-password from .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    user, password = os.getenv("LP_USER"), os.getenv("LP_PASS")
    if not user or not password:
        raise RuntimeError("LP_USER / LP_PASS missing from .env — check the file")
    try:
        leaguepedia.site.client.login(user, password)
    except LoginError as e:
        if "BotPasswordSessionProvider" in str(e):
            pass          # already logged in this session — harmless on re-run
        else:
            raise


def with_backoff(fn, *args, max_retries=5, **kwargs):
    """Call fn(*args, **kwargs), retrying on failure with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"gave up after {max_retries} attempts") from e
            wait = 2 ** attempt * 15
            print(f"  attempt {attempt + 1} failed ({e}); retrying in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
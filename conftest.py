"""Global pytest safety boundary.

Tests in this repository create realistic Product/Order rows and some of them commit
those rows intentionally.  Pytest must therefore never inherit the normal local
``data/autoseller.db`` or a production ``DATABASE_URL`` from ``.env``.

This file is loaded by pytest before test modules are imported, which is early
enough to redirect ``app.config`` / ``app.db`` to an isolated temporary SQLite DB.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_TEST_ROOT = Path(tempfile.mkdtemp(prefix="autoseller-pytest-"))
_TEST_DB = Path(os.environ.get("AUTOSELLER_TEST_DB_PATH") or (_TEST_ROOT / "autoseller_test.db")).resolve()
_TEST_DB.parent.mkdir(parents=True, exist_ok=True)

# Hard override, not setdefault: a developer may have DB_PATH/DATABASE_URL in the
# shell or .env.  A test suite must not be allowed to inherit either production
# target accidentally.
os.environ["DB_PATH"] = str(_TEST_DB)
os.environ["DATABASE_URL"] = ""
os.environ["ENV"] = "test"
os.environ["DEBUG"] = "false"

# External side effects stay disabled even if the developer's .env enables them.
for key in (
    "FULFILLMENT_AUTO_PURCHASE_ENABLED",
    "INVENTORY_AUTO_VISIBILITY_ENABLED",
    "INQUIRY_AUTO_ANSWER_ENABLED",
    "IMAGE_AI_AUTO_GENERATE",
    "THREADS_AUTO_REPLY",
):
    os.environ[key] = "false"

# Tests that need credentials must inject explicit fakes/mocks themselves. Keeping
# real marketplace/supplier/social credentials out of pytest also prevents a test
# from making a live call merely because a developer has a populated local .env.
for key in (
    "CLAUDE_API_KEY",
    "OPENAI_API_KEY",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "NAVER_LOGIN_ID",
    "NAVER_LOGIN_PW",
    "NAVER_SEARCH_CLIENT_ID",
    "NAVER_SEARCH_CLIENT_SECRET",
    "COUPANG_ACCESS_KEY",
    "COUPANG_SECRET_KEY",
    "COUPANG_VENDOR_ID",
    "COUPANG_VENDOR_USER_ID",
    "DOMEGGOOK_API_KEY",
    "DOMEGGOOK_USER_ID",
    "DOMEGGOOK_PASSWORD",
    "DOMEMAI_API_KEY",
    "ONCHANNEL_LOGIN_ID",
    "ONCHANNEL_LOGIN_PW",
    "OWNERCLAN_USERNAME",
    "OWNERCLAN_PASSWORD",
    "THREADS_APP_ID",
    "THREADS_APP_SECRET",
    "THREADS_USER_ID",
    "THREADS_ACCESS_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
):
    os.environ[key] = ""


def _cleanup_pytest_root() -> None:
    # A caller-provided AUTOSELLER_TEST_DB_PATH may live outside _TEST_ROOT; only
    # remove the directory we created ourselves.
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


atexit.register(_cleanup_pytest_root)

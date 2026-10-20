"""Runtime settings and policy numbers.

Every number marked VERIFY is a policy figure that changes over time. Confirm it
against the official source before relying on it in production.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AGENTS_CSV = Path(os.getenv("GS_AGENTS_CSV", ROOT / "data" / "agents_sample.csv"))
DB_PATH = Path(os.getenv("GS_DB", ROOT / "gulf_saathi.db"))
PUBLIC_BASE_URL = os.getenv("GS_PUBLIC_BASE_URL", "http://localhost:8000")

# VERIFY: maximum service charge a registered recruiting agent may collect
# from a worker under the Emigration Rules (check emigrate.gov.in).
MAX_SERVICE_FEE_INR = int(os.getenv("GS_MAX_SERVICE_FEE", "30000"))

# VERIFY: GST on that service charge, and the resulting total a worker may be asked
# to pay: 30,000 + 18% = 35,400. All payments to the agent are added up and
# compared with this total.
GST_PERCENT = int(os.getenv("GS_GST_PERCENT", "18"))
FEE_CAP_INR = round(MAX_SERVICE_FEE_INR * (100 + GST_PERCENT) / 100)

# VERIFY: Telangana ex gratia for a Gulf worker's death (TOMCOM / NRI dept).
EX_GRATIA_INR = int(os.getenv("GS_EX_GRATIA", "500000"))

# VERIFY: Pravasi Bharatiya Bima Yojana cover for accidental death / disability.
PBBY_COVER_INR = int(os.getenv("GS_PBBY_COVER", "1000000"))

CHECKIN_INTERVAL_DAYS = int(os.getenv("GS_CHECKIN_DAYS", "7"))
MISSED_CALLS_BEFORE_ESCALATION = int(os.getenv("GS_MISSED_LIMIT", "2"))
MAX_RETRIES = 3

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
ADMIN_TOKEN = os.getenv("GS_ADMIN_TOKEN", "")
VALIDATE_TWILIO_SIGNATURE = os.getenv("GS_VALIDATE_TWILIO", "0") == "1"

# Text-to-speech voice and speech-recognition locale per language. Voice names
# depend on what your telephony provider offers; override them if a call fails.
VOICES = {
    "te": os.getenv("GS_VOICE_TE", "Google.te-IN-Standard-A"),
    "hi": os.getenv("GS_VOICE_HI", "Google.hi-IN-Standard-A"),
    "ur": os.getenv("GS_VOICE_UR", "Google.ur-IN-Standard-A"),
}
LOCALES = {"te": "te-IN", "hi": "hi-IN", "ur": "ur-IN"}

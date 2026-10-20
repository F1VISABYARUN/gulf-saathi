"""Settings and policy numbers.

Every number marked VERIFY is a policy figure that changes over time. Confirm it
against the official source before relying on it in public.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# VERIFY: maximum service charge a registered recruiting agent may collect from a
# worker under the Emigration Rules, plus GST on it: 30,000 + 18% = 35,400. All
# payments to the agent are added up and compared with this total.
MAX_SERVICE_FEE_INR = int(os.getenv("GS_MAX_SERVICE_FEE", "30000"))
GST_PERCENT = int(os.getenv("GS_GST_PERCENT", "18"))
FEE_CAP_INR = round(MAX_SERVICE_FEE_INR * (100 + GST_PERCENT) / 100)

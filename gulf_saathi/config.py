"""Settings and policy numbers.

Policy numbers change over time; each one says where it comes from.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Maximum service charge a registered recruiting agent may collect from a worker:
# Emigration (Amendment) Rules 2017 (Rule 25) and MEA advisories, 30,000 + 18% GST
# = 35,400. Older MEA pages still show the 2009 rule (45 days' wages, max 20,000).
# All payments to the agent are added up and compared with this total.
MAX_SERVICE_FEE_INR = int(os.getenv("GS_MAX_SERVICE_FEE", "30000"))
GST_PERCENT = int(os.getenv("GS_GST_PERCENT", "18"))
FEE_CAP_INR = round(MAX_SERVICE_FEE_INR * (100 + GST_PERCENT) / 100)

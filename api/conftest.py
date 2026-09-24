"""Put `api/`, `integration/`, and `booking-service/` on sys.path so tests can
import `main`, `verdict`, `slots`, the nudge engine, and the booking models
flatly (all three folder names are non-importable). The CV service is not added
-- it shares the module name `config` with the booking service."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

for path in (HERE, os.path.join(ROOT, "integration"), os.path.join(ROOT, "booking-service")):
    if path not in sys.path:
        sys.path.insert(0, path)

"""Put `integration/` and `booking-service/` on sys.path so `tests/` can import
them flatly (both folder names contain a hyphen and are not importable packages).
The CV service is deliberately not added -- it shares the module name `config`
with the booking service and is consumed only via its data contract."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

for path in (HERE, os.path.join(ROOT, "booking-service")):
    if path not in sys.path:
        sys.path.insert(0, path)

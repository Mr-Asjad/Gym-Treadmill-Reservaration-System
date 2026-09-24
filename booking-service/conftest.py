"""Put this package's modules on sys.path so `tests/` can import them flatly
(the folder name 'booking-service' is not an importable package name)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

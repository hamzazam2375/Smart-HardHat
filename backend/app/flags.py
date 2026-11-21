"""validity_flags / motion_flags bits.

PROVISIONAL: same mock convention as scripts/seed_mock_data.py and ml/contract.json.
F26-113 Table 5.1 requires "defined bits only" but does not number them; align with the
firmware packet format when it is frozen.
"""
# validity_flags (per-channel quality)
CO_INVALID = 1
CO_PARTIAL = 2
ENV_INVALID = 4
HEAT_UNSUPPORTED = 8
IMU_INVALID = 16
BATTERY_UNAVAILABLE = 32
GPS_NO_FIX = 64

# motion_flags (event-state bits)
IMPACT = 1
PREALERT = 2
CANCELLED = 4
POSSIBLE_FALL = 8
SOS = 16

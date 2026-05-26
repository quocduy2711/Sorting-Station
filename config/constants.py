"""
Product routing constants.

These are intentionally NOT in .env — they are part of the
application domain logic, not deployment configuration.
"""
from typing import Dict, Set, Tuple

# Product ID → Sorter number
SORT_MAP: Dict[int, int] = {
    1: 1,  # Flat / Blue   → Sorter 1
    2: 1,  # Flat / Green  → Sorter 1
    3: 2,  # Circle / Blue → Sorter 2
    4: 2,  # Circle / Green→ Sorter 2
    5: 3,  # Complex / Blue→ Sorter 3
    6: 3,  # Complex / Green→ Sorter 3
}

# Product ID → (shape, color)
PRODUCT_MAP: Dict[int, Tuple[str, str]] = {
    1: ("Flat",    "Blue"),
    2: ("Flat",    "Green"),
    3: ("Circle",  "Blue"),
    4: ("Circle",  "Green"),
    5: ("Complex", "Blue"),
    6: ("Complex", "Green"),
}

# Set of valid product IDs
VALID_PRODUCT_IDS: Set[int] = set(SORT_MAP.keys())


# ── Conveyor error detection ─────────────────────────────────────────────────
# These thresholds control error detector sensitivity.
# Configurable via environment variables, defaults are conservative.

CONVEYOR_JAM_TIMEOUT_MS: int = int(
    __import__("os").getenv("CONVEYOR_JAM_TIMEOUT_MS", "5000")
)
CONVEYOR_VISION_STALL_TIMEOUT_MS: int = int(
    __import__("os").getenv("CONVEYOR_VISION_STALL_TIMEOUT_MS", "3000")
)
CONVEYOR_SUDDEN_STOP_DEBOUNCE_MS: int = int(
    __import__("os").getenv("CONVEYOR_SUDDEN_STOP_DEBOUNCE_MS", "500")
)

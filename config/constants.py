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

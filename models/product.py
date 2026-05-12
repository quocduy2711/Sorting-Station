"""
Product model for tracking individual items through the sorting system.
"""
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class ProductState(Enum):
    """Product lifecycle states."""
    CREATED = "CREATED"
    WAITING_BLADE = "WAITING_BLADE"
    PASSED_BLADE = "PASSED_BLADE"
    WAITING_CLEAR_ZONE = "WAITING_CLEAR_ZONE"
    READING_ID = "READING_ID"
    ID_CONFIRMED = "ID_CONFIRMED"
    MOVING_TO_SORTER = "MOVING_TO_SORTER"
    SORTING = "SORTING"
    REMOVED = "REMOVED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ProductShape(Enum):
    """Product shape types."""
    FLAT = "Flat"
    CIRCLE = "Circle"
    COMPLEX = "Complex"


class ProductColor(Enum):
    """Product color types."""
    BLUE = "Blue"
    GREEN = "Green"


@dataclass
class Product:
    """
    Represents a physical product moving through the sorting system.
    
    RULE: Only one active product at any time.
    """
    uid: int  # Unique ID for product instance
    vision_id: int  # ID read from vision sensor
    target_sorter: int  # Target sorter (1, 2, or 3)
    shape: ProductShape
    color: ProductColor
    created_at: float = field(default_factory=time.monotonic)
    state: ProductState = field(default=ProductState.CREATED)
    last_state_change: float = field(default_factory=time.monotonic)
    vision_read_at: Optional[float] = None
    sorter_activated_at: Optional[float] = None
    removed_at: Optional[float] = None
    error_message: Optional[str] = None

    def get_age_ms(self) -> float:
        """Get product age in milliseconds."""
        return (time.monotonic() - self.created_at) * 1000

    def get_state_duration_ms(self) -> float:
        """Get duration in current state in milliseconds."""
        return (time.monotonic() - self.last_state_change) * 1000

    def set_state(self, new_state: ProductState) -> None:
        """Update product state and timestamp."""
        self.state = new_state
        self.last_state_change = time.monotonic()

    def __repr__(self) -> str:
        return (f"Product(uid={self.uid}, vision_id={self.vision_id}, "
                f"sorter={self.target_sorter}, {self.shape.value}/{self.color.value}, "
                f"state={self.state.value})")

"""
Product tracking system.

RULE: Only one current product at any time.
RULE: Protected by asyncio.Lock()
"""
import logging
from typing import Optional
from models.product import Product, ProductState


logger = logging.getLogger(__name__)


class ProductTracker:
    """
    Tracks the current product moving through the system.
    
    RULE: Only ONE active product at a time.
    """

    def __init__(self):
        """Initialize product tracker."""
        self.current_product: Optional[Product] = None
        self.product_history: list[Product] = []
        self.next_uid = 1000
        self.products_created = 0
        self.products_completed = 0
        self.products_failed = 0

    def create_product(self, vision_id: int, shape: str, color: str) -> Product:
        """
        Create a new product.
        
        RULE: Cannot create if current product exists.
        
        Args:
            vision_id: ID from vision sensor
            shape: Product shape
            color: Product color
            
        Returns:
            New Product object
            
        Raises:
            RuntimeError if product already exists
        """
        if self.current_product is not None:
            raise RuntimeError("Cannot create product while one is active")
        
        from models.product import ProductShape, ProductColor
        
        uid = self.next_uid
        self.next_uid += 1
        
        product = Product(
            uid=uid,
            vision_id=vision_id,
            target_sorter=0,  # Will be set after ID confirmation
            shape=ProductShape(shape),
            color=ProductColor(color)
        )
        
        self.current_product = product
        self.products_created += 1
        
        logger.info(f"Product created: {product}")
        return product

    def set_current_product_state(self, state: ProductState) -> None:
        """Update current product state."""
        if self.current_product:
            self.current_product.set_state(state)
            logger.debug(f"Product state: {self.current_product.uid} -> {state.value}")

    def complete_product(self) -> None:
        """
        Mark current product as complete and remove from system.
        
        Product is moved to history.
        """
        if self.current_product:
            self.current_product.set_state(ProductState.COMPLETE)
            self.product_history.append(self.current_product)
            self.products_completed += 1
            
            logger.info(f"Product completed: {self.current_product}")
            self.current_product = None

    def fail_product(self, reason: str) -> None:
        """
        Mark current product as failed.
        
        Args:
            reason: Failure reason
        """
        if self.current_product:
            self.current_product.set_state(ProductState.FAILED)
            self.current_product.error_message = reason
            self.product_history.append(self.current_product)
            self.products_failed += 1
            
            logger.error(f"Product failed: {self.current_product.uid} - {reason}")
            self.current_product = None

    def get_current_product(self) -> Optional[Product]:
        """Get the current active product."""
        return self.current_product

    def has_active_product(self) -> bool:
        """Check if there's an active product."""
        return self.current_product is not None

    def get_stats(self) -> dict:
        """Get tracking statistics."""
        return {
            "created": self.products_created,
            "completed": self.products_completed,
            "failed": self.products_failed,
            "active": self.current_product is not None,
        }

    def get_history(self, limit: int = 50) -> list[Product]:
        """Get recent product history."""
        return self.product_history[-limit:]

"""
Sorting logic and product routing.
"""
import logging
from config import SORT_MAP, PRODUCT_MAP, VALID_PRODUCT_IDS


logger = logging.getLogger(__name__)


class SortingLogic:
    """
    Determines product routing and validates product IDs.
    """

    def __init__(self):
        """Initialize sorting logic."""
        self.sort_map = SORT_MAP
        self.product_map = PRODUCT_MAP
        self.valid_ids = VALID_PRODUCT_IDS
        self.invalid_reads = 0

    def validate_product_id(self, product_id: int) -> bool:
        """
        Validate if product ID is in known set.
        
        Args:
            product_id: ID from vision sensor
            
        Returns:
            True if valid
        """
        if product_id not in self.valid_ids:
            self.invalid_reads += 1
            logger.error(f"Invalid product ID: {product_id}")
            return False
        
        return True

    def get_sorter_for_product(self, product_id: int) -> int:
        """
        Get target sorter for a product ID.
        
        Args:
            product_id: ID from vision sensor
            
        Returns:
            Sorter number (1, 2, or 3)
            
        Raises:
            ValueError if ID is invalid
        """
        if not self.validate_product_id(product_id):
            raise ValueError(f"Invalid product ID: {product_id}")
        
        sorter = self.sort_map[product_id]
        logger.debug(f"Product {product_id} -> Sorter {sorter}")
        return sorter

    def get_product_info(self, product_id: int) -> tuple[str, str]:
        """
        Get shape and color for product ID.
        
        Args:
            product_id: ID from vision sensor
            
        Returns:
            Tuple of (shape, color)
            
        Raises:
            ValueError if ID is invalid
        """
        if not self.validate_product_id(product_id):
            raise ValueError(f"Invalid product ID: {product_id}")
        
        shape, color = self.product_map[product_id]
        return shape, color

    def get_all_sorters(self) -> set[int]:
        """Get all active sorters."""
        return set(self.sort_map.values())

    def get_products_for_sorter(self, sorter_id: int) -> set[int]:
        """Get all product IDs that route to a specific sorter."""
        return {pid for pid, sid in self.sort_map.items() if sid == sorter_id}

    def get_invalid_read_count(self) -> int:
        """Get count of invalid product reads."""
        return self.invalid_reads

    def reset_invalid_count(self) -> None:
        """Reset invalid read counter."""
        self.invalid_reads = 0

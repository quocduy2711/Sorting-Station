"""
SortingService — product routing orchestration.

Responsibilities:
- Subscribe to PRODUCT_DETECTED event
- Validate and classify product (resolve sorter)
- Emit PRODUCT_CLASSIFIED → FSM activates sorter
- Emit SORT_COMMAND for actuator output
- Handle invalid product IDs (emit ALARM_TRIGGERED)

RULE: Does NOT touch OutputState directly.
RULE: Does NOT call FSM directly — emits events.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from control.event_manager import Event, EventManager, SystemEvent
from control.sorting_logic import SortingLogic
from control.product_tracking import ProductTracker
from config.constants import PRODUCT_MAP

if TYPE_CHECKING:
    from config.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


class SortingService:
    """
    Owns product classification and routing logic.

    Listens for PRODUCT_DETECTED → resolves sorter → emits PRODUCT_CLASSIFIED.
    """

    def __init__(self, ctx: "RuntimeContext") -> None:
        self._ctx = ctx
        self._em: EventManager = ctx.event_manager
        self._logic: SortingLogic = ctx.sorting_logic
        self._tracker: ProductTracker = ctx.product_tracker

    def register_handlers(self) -> None:
        """Subscribe to relevant events."""
        self._em.subscribe(SystemEvent.PRODUCT_DETECTED, self._on_product_detected)
        self._em.subscribe(SystemEvent.PRODUCT_SORT_DONE, self._on_sort_done)
        self._em.subscribe(SystemEvent.AT_EXIT_TRIGGERED, self._on_at_exit)
        logger.info("SortingService handlers registered")

    async def _on_product_detected(self, event: Event) -> None:
        """
        Handle a new product detected by vision sensor.

        Expected event.data:
            vision_id: int
        """
        vision_id: int = event.data.get("vision_id", 0)
        logger.info(f"SortingService: product detected (vision_id={vision_id})")

        # Validate
        if not self._logic.validate_product_id(vision_id):
            logger.error(f"Invalid product ID from vision: {vision_id}")
            self._em.emit(
                SystemEvent.ALARM_TRIGGERED,
                source="SortingService",
                data={
                    "alarm_type": "INVALID_PRODUCT_ID",
                    "message": f"Unknown product ID: {vision_id}",
                    "severity": "ERROR",
                },
            )
            return

        # Resolve sorter and product metadata
        try:
            sorter_id = self._logic.get_sorter_for_product(vision_id)
            shape, color = self._logic.get_product_info(vision_id)
        except ValueError as exc:
            logger.error(f"SortingService routing error: {exc}")
            return

        # Create product in tracker
        if self._tracker.has_active_product():
            logger.warning(
                "SortingService: product detected while one is active — ignoring"
            )
            return

        product = self._tracker.create_product(
            vision_id=vision_id, shape=shape, color=color
        )
        product.target_sorter = sorter_id

        logger.info(
            f"SortingService: classified product {product.uid} "
            f"({shape}/{color}) → Sorter {sorter_id}"
        )

        # Emit classification event
        self._em.emit(
            SystemEvent.PRODUCT_CLASSIFIED,
            source="SortingService",
            data={
                "product_uid": product.uid,
                "vision_id": vision_id,
                "sorter_id": sorter_id,
                "shape": shape,
                "color": color,
            },
        )

        # Emit sort command for FSM
        self._em.emit(
            SystemEvent.SORT_COMMAND,
            source="SortingService",
            data={"sorter_id": sorter_id, "product_uid": product.uid},
        )

    async def _on_sort_done(self, event: Event) -> None:
        """Handle product successfully sorted."""
        self._tracker.complete_product()
        logger.info("SortingService: product sort complete")

    async def _on_at_exit(self, event: Event) -> None:
        """Handle product reaching exit sensor — increment remover counter.

        RULE: Only count when there's an active product with a known target_sorter.
        RULE: Counter increment is idempotent per product lifecycle
              (product is completed after this, preventing double-count).
        RULE: Write counter to Modbus immediately after increment.
        """
        product = self._tracker.get_current_product()
        if product and hasattr(product, 'target_sorter') and product.target_sorter > 0:
            sorter_id = product.target_sorter
            
            # Increment local counter
            self._tracker.on_product_dropped(sorter_id)
            
            # Get updated count from system state
            system_state = self._ctx.state.system_state
            new_count = system_state.remover_counts.get(sorter_id, 0) if system_state else 0
            
            # Write counter to Modbus for Factory IO display
            output_writer = self._ctx.output_writer
            if output_writer:
                await output_writer.write_counter(sorter_id, new_count)
            
            logger.info(
                f"SortingService: product {product.uid} dropped into "
                f"remover {sorter_id} (count={new_count})"
            )
        else:
            logger.debug("AT_EXIT_TRIGGERED but no active product with target_sorter")

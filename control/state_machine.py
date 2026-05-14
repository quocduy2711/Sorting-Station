"""
System-level state machine.

4 luồng hoạt động chính:
  Luồng 1: Emitter sinh 1 sản phẩm → chờ sản phẩm vào remover → sinh tiếp
  Luồng 2: Entry conveyor → stop blade GIỮ sản phẩm → vision đọc ID
            → Hạ stop blade 2 giây → Nâng lại đợi sản phẩm tiếp theo
  Luồng 3: Phân loại theo vision_id → bật sorter tương ứng
            id 1,2 → sorter1_belt + sorter1_turn
            id 3,4 → sorter2_belt + sorter2_turn
            id 5,6 → sorter3_belt + sorter3_turn
  Luồng 4: at_exit → sản phẩm đã vào remover → tắt sorter → cho emitter sinh tiếp

RULE: Chỉ có StateMachine được ghi OutputState.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from models.system_state import SystemStateEnum, SystemState
from models.output_state import OutputState
from config.constants import SORT_MAP, VALID_PRODUCT_IDS

if TYPE_CHECKING:
    from control.event_manager import EventManager

logger = logging.getLogger(__name__)

# ── Timing constants (seconds) ─────────────────────────────────────────────────
BLADE_OPEN_DURATION_S   = 2.0   # Thời gian mở stop blade để sản phẩm đi qua
EMITTER_PULSE_DURATION_S = 0.2  # Thời gian bật emitter để tạo 1 sản phẩm
SORTER_ACTIVE_TIMEOUT_S  = 15.0 # Thời gian tối đa chờ at_exit (failsafe)


class StateMachine:
    """
    Điều phối 4 luồng hoạt động của trạm phân loại.

    States:
        IDLE          - hệ thống chờ
        STARTING      - khởi động conveyor
        RUNNING       - đang chạy (tất cả 4 luồng hoạt động)
        STOPPED       - dừng
        EMERGENCY_STOP- dừng khẩn cấp
    """

    def __init__(self, system_state: SystemState, output_state: OutputState) -> None:
        self.system_state = system_state
        self.output_state = output_state
        self._em: Optional[EventManager] = None

        # Trạng thái nội bộ
        self._product_in_flight: bool = False   # Có sản phẩm đang trên băng hay chưa
        self._current_vision_id: int = 0        # ID sản phẩm đang xử lý
        self._active_sorter: int = 0            # Sorter đang bật (0 = không có)
        self._sort_task: Optional[asyncio.Task] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Event Handler Registration
    # ──────────────────────────────────────────────────────────────────────────

    def register_handlers(self, em: "EventManager") -> None:
        """Đăng ký lắng nghe các sự kiện từ EventManager."""
        from control.event_manager import SystemEvent
        self._em = em
        em.subscribe(SystemEvent.START_BUTTON_PRESSED, self._on_start)
        em.subscribe(SystemEvent.STOP_BUTTON_PRESSED, self._on_stop)
        em.subscribe(SystemEvent.ESTOP_ACTIVATED, self._on_estop)
        em.subscribe(SystemEvent.ESTOP_CLEARED, self._on_estop_clear)
        em.subscribe(SystemEvent.PRODUCT_DETECTED, self._on_product_detected)
        em.subscribe(SystemEvent.AT_EXIT_TRIGGERED, self._on_at_exit)
        logger.info("StateMachine handlers registered")

    # ──────────────────────────────────────────────────────────────────────────
    # Button handlers
    # ──────────────────────────────────────────────────────────────────────────

    async def _on_start(self, event) -> None:
        if self.system_state.state in (SystemStateEnum.IDLE, SystemStateEnum.STOPPED):
            await self.transition_to(SystemStateEnum.STARTING)
            asyncio.create_task(self._startup_sequence(), name="startup_seq")

    async def _startup_sequence(self) -> None:
        """Khởi động conveyor rồi bắt đầu RUNNING + sinh sản phẩm đầu tiên."""
        await asyncio.sleep(0.5)
        if self.system_state.state == SystemStateEnum.STARTING:
            await self.transition_to(SystemStateEnum.RUNNING)
            # Luồng 1: sinh sản phẩm đầu tiên ngay
            await self._pulse_emitter()

    async def _on_stop(self, event) -> None:
        if self.system_state.state not in (SystemStateEnum.EMERGENCY_STOP, SystemStateEnum.ERROR):
            await self.transition_to(SystemStateEnum.STOPPED)

    async def _on_estop(self, event) -> None:
        await self.transition_to(SystemStateEnum.EMERGENCY_STOP)

    async def _on_estop_clear(self, event) -> None:
        if self.system_state.state == SystemStateEnum.EMERGENCY_STOP:
            await self.transition_to(SystemStateEnum.STOPPED)

    # ──────────────────────────────────────────────────────────────────────────
    # Luồng 2: Vision sensor phát hiện sản phẩm ở stop blade
    # ──────────────────────────────────────────────────────────────────────────

    async def _on_product_detected(self, event) -> None:
        """
        Luồng 2 + 3: Vision sensor đọc được sản phẩm đang bị chặn tại stop blade.

        - Xác định sorter theo vision_id
        - Bật sorter ngay
        - Hạ stop blade → 2 giây → nâng lại
        """
        if self.system_state.state != SystemStateEnum.RUNNING:
            return

        if self._product_in_flight:
            logger.warning("FSM: Product detected but one is already in flight — ignoring")
            return

        vision_id: int = event.data.get("vision_id", 0)
        if vision_id not in VALID_PRODUCT_IDS:
            logger.error(f"FSM: Invalid vision_id={vision_id}")
            return

        # Xác định sorter
        sorter_id = SORT_MAP[vision_id]
        logger.info(f"FSM: Product detected id={vision_id} → Sorter {sorter_id}")

        self._product_in_flight = True
        self._current_vision_id = vision_id
        self._active_sorter = sorter_id

        # Hủy sort task cũ nếu có
        if self._sort_task and not self._sort_task.done():
            self._sort_task.cancel()

        # Luồng 3: bật sorter + Luồng 2: mở cổng
        self._sort_task = asyncio.create_task(
            self._blade_and_sorter_sequence(sorter_id),
            name=f"sort_seq_s{sorter_id}"
        )

    async def _blade_and_sorter_sequence(self, sorter_id: int) -> None:
        """
        Luồng 2 + 3 (tổng hợp):
        1. Bật sorter
        2. Hạ stop blade
        3. Chờ 2 giây
        4. Nâng stop blade lại
        5. Chờ at_exit hoặc timeout failsafe
        """
        try:
            # Luồng 3: bật sorter ngay
            self._set_sorter(sorter_id, True)
            logger.info(f"FSM: Sorter {sorter_id} activated")

            # Luồng 2: hạ stop blade để sản phẩm đi qua
            self.output_state.stop_blade = False
            logger.info("FSM: Stop blade LOWERED")

            # Chờ 2 giây
            await asyncio.sleep(BLADE_OPEN_DURATION_S)

            # Luồng 2: nâng stop blade lại để chặn sản phẩm tiếp theo
            self.output_state.stop_blade = True
            logger.info("FSM: Stop blade RAISED — ready for next product")

            # Failsafe: nếu at_exit không đến sau SORTER_ACTIVE_TIMEOUT_S giây thì tự reset
            await asyncio.sleep(SORTER_ACTIVE_TIMEOUT_S)
            if self._product_in_flight:
                logger.warning(f"FSM: Sorter {sorter_id} timeout — forcing reset")
                await self._reset_sorter(sorter_id)

        except asyncio.CancelledError:
            logger.debug(f"FSM: Sort sequence cancelled for sorter {sorter_id}")

    # ──────────────────────────────────────────────────────────────────────────
    # Luồng 4: at_exit — sản phẩm đã rơi vào remover
    # ──────────────────────────────────────────────────────────────────────────

    async def _on_at_exit(self, event) -> None:
        """
        Luồng 4: Cảm biến at_exit phát hiện sản phẩm đã vào remover.

        - Tắt sorter tương ứng
        - Reset trạng thái product_in_flight
        - Luồng 1: pulse emitter để sinh sản phẩm mới
        """
        if not self._product_in_flight:
            return

        sorter_id = self._active_sorter
        logger.info(f"FSM: at_exit triggered — product in remover, resetting sorter {sorter_id}")

        await self._reset_sorter(sorter_id)

        # Luồng 1: sinh sản phẩm tiếp theo
        if self.system_state.state == SystemStateEnum.RUNNING:
            await asyncio.sleep(0.5)  # Nhỏ delay tránh double-fire
            await self._pulse_emitter()

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _pulse_emitter(self) -> None:
        """Luồng 1: Bật emitter tạo 1 sản phẩm rồi tắt ngay."""
        if self.system_state.state != SystemStateEnum.RUNNING:
            return
        logger.info("FSM: Emitter pulse → creating new product")
        self.output_state.emitter = True
        await asyncio.sleep(EMITTER_PULSE_DURATION_S)
        self.output_state.emitter = False

    def _set_sorter(self, sorter_id: int, active: bool) -> None:
        """Bật/tắt belt + turn của sorter chỉ định."""
        if sorter_id == 1:
            self.output_state.sorter1_belt = active
            self.output_state.sorter1_turn = active
        elif sorter_id == 2:
            self.output_state.sorter2_belt = active
            self.output_state.sorter2_turn = active
        elif sorter_id == 3:
            self.output_state.sorter3_belt = active
            self.output_state.sorter3_turn = active

    async def _reset_sorter(self, sorter_id: int) -> None:
        """Luồng 4: Tắt sorter và reset tracking state."""
        self._set_sorter(sorter_id, False)
        self._product_in_flight = False
        self._current_vision_id = 0
        self._active_sorter = 0
        logger.info(f"FSM: Sorter {sorter_id} deactivated, product_in_flight=False")

    # ──────────────────────────────────────────────────────────────────────────
    # FSM State Transitions
    # ──────────────────────────────────────────────────────────────────────────

    async def transition_to(self, new_state: SystemStateEnum) -> None:
        """Chuyển trạng thái và cập nhật outputs tương ứng."""
        old_state = self.system_state.state
        if old_state == new_state:
            return

        logger.info(f"State transition: {old_state.value} → {new_state.value}")
        self.system_state.set_state(new_state)
        await self._configure_outputs_for_state(new_state)

        # Emit FSM state change event
        if self._em:
            from control.event_manager import SystemEvent
            self._em.emit(
                SystemEvent.FSM_STATE_CHANGED,
                source="StateMachine",
                data={"old_state": old_state.value, "new_state": new_state.value},
            )

    async def _configure_outputs_for_state(self, state: SystemStateEnum) -> None:
        """Cấu hình outputs khi vào trạng thái mới."""
        if state == SystemStateEnum.IDLE:
            self.output_state.emitter = False
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False
            self.output_state.stop_blade = True
            self._disable_all_sorters()

        elif state == SystemStateEnum.STARTING:
            # Bật conveyor, nâng stop blade
            self.output_state.entry_conveyor = True
            self.output_state.exit_conveyor = True
            self.output_state.stop_blade = True

        elif state == SystemStateEnum.RUNNING:
            # Conveyor chạy, stop blade UP (sẵn sàng chặn sản phẩm)
            self.output_state.entry_conveyor = True
            self.output_state.exit_conveyor = True
            self.output_state.stop_blade = True

        elif state in (SystemStateEnum.STOPPED, SystemStateEnum.ERROR):
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False
            self.output_state.stop_blade = True
            self._disable_all_sorters()
            self._product_in_flight = False
            self._active_sorter = 0

        elif state == SystemStateEnum.EMERGENCY_STOP:
            # Tắt tất cả ngay lập tức
            self.output_state.reset_all()
            self._product_in_flight = False
            self._active_sorter = 0
            if self._sort_task and not self._sort_task.done():
                self._sort_task.cancel()

    def _disable_all_sorters(self) -> None:
        """Tắt tất cả sorter outputs."""
        for attr in [
            "sorter1_belt", "sorter1_turn",
            "sorter2_belt", "sorter2_turn",
            "sorter3_belt", "sorter3_turn",
            "remover1", "remover2", "remover3",
        ]:
            setattr(self.output_state, attr, False)

    # ──────────────────────────────────────────────────────────────────────────
    # Status helpers
    # ──────────────────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self.system_state.state == SystemStateEnum.RUNNING

    def is_emergency_stop(self) -> bool:
        return self.system_state.state == SystemStateEnum.EMERGENCY_STOP

    def get_current_state(self) -> SystemStateEnum:
        return self.system_state.state

    @property
    def product_in_flight(self) -> bool:
        return self._product_in_flight

    @property
    def active_sorter(self) -> int:
        return self._active_sorter

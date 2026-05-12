"""
Main entry point for Industrial Control Runtime.

Usage:
    python main.py
"""

import asyncio
import logging
import signal
import sys
from utils import setup_logging
from control.runtime_engine import RuntimeEngine


# Setup logging
setup_logging(logging.INFO)
logger = logging.getLogger(__name__)


class RuntimeController:
    """Controller for runtime lifecycle."""
    
    def __init__(self):
        """Initialize controller."""
        self.engine: RuntimeEngine = None
        self.shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the runtime."""
        logger.info("=== Industrial Control Runtime Starting ===")
        
        # Create engine
        self.engine = RuntimeEngine()
        
        # Initialize
        if not await self.engine.initialize():
            logger.error("Failed to initialize runtime")
            sys.exit(1)
        
        # Run main loop
        try:
            await self.engine.run()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.critical(f"Fatal error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown the runtime."""
        if self.engine:
            await self.engine.shutdown()
        
        logger.info("=== Runtime Stopped ===")

    def handle_signal(self, sig, frame):
        """Handle system signals."""
        logger.info(f"Received signal {sig}")
        self.shutdown_event.set()


async def main():
    """Main entry point."""
    controller = RuntimeController()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown")
        # Cancel all tasks
        for task in asyncio.all_tasks():
            task.cancel()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start runtime
    await controller.start()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("INDUSTRIAL CONTROL RUNTIME - SORTING STATION")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")
        sys.exit(1)

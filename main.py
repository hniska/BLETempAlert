import asyncio
import signal
import logging
import os
from datetime import datetime
from temperature_alarm import TemperatureMonitor
from tui import TemperatureAlarmApp
from logging_config import setup_logging

async def cleanup(app: TemperatureAlarmApp, monitor: TemperatureMonitor):
    """Clean up application resources with timeout protection."""
    logger.info("Starting application cleanup")
    
    try:
        # First cleanup the monitor (includes sensor disconnection)
        if monitor:
            try:
                await asyncio.wait_for(monitor.cleanup(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Monitor cleanup timed out")
            except Exception as e:
                logger.error(f"Error during monitor cleanup: {e}")
        
        # Then cleanup the app
        if app:
            try:
                # Don't call cleanup_and_exit, just do cleanup
                await asyncio.wait_for(app.cleanup(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("App cleanup timed out")
            except Exception as e:
                logger.error(f"Error during app cleanup: {e}")
            
    except Exception as e:
        logger.exception(f"Fatal error during cleanup: {e}")
    finally:
        logger.info("Cleanup completed")

async def main():
    logger = setup_logging(__name__)  # Use the centralized logging setup
    logger.info("Starting main function")
    
    try:
        app = TemperatureAlarmApp()
        monitor = TemperatureMonitor()
        app.monitor = monitor
        
        # Run the app
        await app.run_async()
        
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
    finally:
        # Ensure cleanup happens
        if 'monitor' in locals():
            await monitor.cleanup()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except SystemExit:
        pass  # Handle SystemExit gracefully
    except Exception as e:
        print(f"Fatal error: {e}")

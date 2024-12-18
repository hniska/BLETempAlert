import signal
import sys
from gtts import gTTS
from io import BytesIO
from pasco.pasco_ble_device import PASCOBLEDevice
import time
from typing import Literal, Optional
import sqlite3
from datetime import datetime
import plotext as plt
import os
import asyncio
import logging
from temperature_types import TemperatureBuffer, TemperatureData, BaseTemperatureMonitor, TemperatureUI
from concurrent.futures import ThreadPoolExecutor
import functools
from logging_config import setup_logging
from textual.screen import ModalScreen
from textual.containers import Container
from textual.widgets import Button, Label
from textual.app import ComposeResult  # Add this import
from textual.events import Key
from sound_manager import AsyncSoundPlayer  # Update import
from threading import Event
from config_manager import ConfigManager
from notification_manager import NotificationManager
import pygame
from aiosqlite import Connection as AioConnection
from pathlib import Path
from database_manager import DatabaseManager

ANNOUNCE_PERIOD_S = 15
CHECK_PERIOD_S = 2  # Temperature sampling every 2 seconds

logger = setup_logging(__name__)

# Initialize the global exit flag
exit_flag = Event()

class NotificationPopup(ModalScreen[bool]):
    """A popup notification with a button and alarm sound."""
    
    def __init__(self, message: str) -> None:
        """Initialize the popup with a message.
        
        Args:
            message: The message to display in the popup
        """
        super().__init__()
        self.message = message
        self.alarm = AsyncSoundPlayer("sounds/alarm.mp3", continuous=True)  # Updated to AsyncSoundPlayer

    BINDINGS = [("escape", "dismiss", "Dismiss")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the popup."""
        yield Container(
            Label(self.message),
            Button("OK", variant="primary", id="ok_button"),
            id="popup_container",
        )

    async def on_mount(self) -> None:  # Made async
        """Start the alarm when the popup is mounted."""
        await self.alarm.start()  # Added await

    async def _stop_alarm(self) -> None:  # Made async
        """Stop the alarm sound immediately."""
        if hasattr(self, 'alarm'):
            await self.alarm.stop()  # Added await
            await asyncio.sleep(0.1)  # Changed to asyncio.sleep

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # Made async
        """Handle button press event."""
        if event.button.id == "ok_button":
            await self._stop_alarm()  # Added await
            self.dismiss(True)

    async def on_key(self, event: Key) -> None:  # Made async
        """Handle key press event."""
        if event.key == "escape":
            await self._stop_alarm()  # Added await
            self.dismiss(False)

    async def on_unmount(self) -> None:  # Made async
        """Ensure alarm is stopped when popup is unmounted."""
        await self._stop_alarm()  # Added await

class TemperatureMonitor(BaseTemperatureMonitor):
    def __init__(self, sample_rate: float = 2.0):
        super().__init__(sample_rate)
        self._setup_logging()
        
        # Initialize managers
        config_manager = ConfigManager()
        self.notification_manager = NotificationManager(config_manager.ntfy_config)
        self.db_manager = DatabaseManager(config_manager.data_recording_config)
        self.config_manager = config_manager
        self.tts_player = AsyncSoundPlayer(None)
        
        # Initialize state
        self.recording_enabled = self.config_manager.data_recording_config.enabled
        self.run_id = None
        self.running_tasks = []

    def _setup_logging(self):
        """Set up logging for the temperature monitor"""
        self.logger = logger

    async def monitor_temperature(self, app: TemperatureUI, 
                                direction: Literal['increases', 'decreases'], 
                                target_temp: float) -> None:
        """Monitor temperature and handle announcements and logging"""
        try:
            self.logger.debug("Starting temperature monitoring")
            
            # Initialize database if not already done
            if not self.db_manager.connection:
                await self.db_manager.initialize()
            
            # Create new run and enable recording
            if self.config_manager.data_recording_config.enabled:
                await self.enable_recording(target_temp, direction)
            
            next_read_time = time.time()
            last_announced_temp: Optional[float] = None
            target_reached_flag = False
            start_time = time.time()
            consecutive_errors = 0
            max_consecutive_errors = 5
            self.last_announcement_time = 0

            # Reset exit flag when starting monitoring
            self.exit_flag.clear()

            # Create a monitoring task that doesn't block the event loop
            monitoring_task = asyncio.create_task(self._monitor_loop(
                app, direction, target_temp, next_read_time, last_announced_temp,
                target_reached_flag, start_time, consecutive_errors, max_consecutive_errors
            ))
            self.running_tasks.append(monitoring_task)

        except Exception as e:
            self.logger.exception(f"Error in monitor_temperature: {e}")
            await app.stop_monitoring()

    async def _monitor_loop(self, app, direction, target_temp, next_read_time,
                            last_announced_temp, target_reached_flag, start_time,
                            consecutive_errors, max_consecutive_errors):
        """Internal monitoring loop that runs as a separate task"""
        try:
            while not self.exit_flag.is_set():
                try:
                    if time.time() >= next_read_time:
                        current_temp = await self.safe_read_temperature()
                        current_time = datetime.now()

                        if current_temp is None:
                            consecutive_errors += 1
                            if consecutive_errors >= max_consecutive_errors:
                                self.logger.error("Failed to read temperature")
                                await app.stop_monitoring()
                                break
                            await asyncio.sleep(self.sample_rate / 2)  # Wait half the sample time before retry
                            continue

                        consecutive_errors = 0
                        next_read_time = time.time() + self.sample_rate

                        # Log temperature directly to the database
                        if self.recording_enabled and self.run_id is not None:
                            await self.db_manager.record_temperature(self.run_id, current_temp)

                        target_reached_flag, last_announced_temp = await self._handle_temperature_update(
                            app, current_temp, current_time, 
                            target_temp, direction, last_announced_temp,
                            target_reached_flag, start_time
                        )
                        
                    await asyncio.sleep(min(0.1, self.sample_rate / 10))  # Scale sleep with sample rate
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.logger.exception(f"Error in monitor loop: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.logger.info("Monitor loop cancelled")
        except Exception as e:
            self.logger.exception(f"Fatal error in monitor loop: {e}")
        finally:
            self.logger.info("Monitor loop completed")

    async def safe_read_temperature(self) -> Optional[float]:
        """Safely read temperature from the sensor."""
        if not self.temp_sensor:
            self.logger.warning("Temperature sensor is not initialized.")
            return None
        try:
            return await asyncio.to_thread(self.temp_sensor.read_data, 'Temperature')
        except Exception as e:
            self.logger.warning(f"Error reading temperature: {e}")
            return None

    async def _database_recorder(self):
        """Async task to handle database recording"""
        try:
            self.logger.debug("Starting database recorder task")
            while not self.exit_flag.is_set() or not self.record_queue.empty():
                try:
                    self.logger.debug(f"Waiting for temperature data. Queue size: {self.record_queue.qsize()}")
                    run_id, temperature = await asyncio.wait_for(
                        self.record_queue.get(), 
                        timeout=1.0
                    )
                    self.logger.debug(f"Processing temperature {temperature}°C for run {run_id}")
                    await self._record_to_database(run_id, temperature)
                    self.record_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.logger.error(f"Error in database recorder: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.logger.info("Database recorder cancelled")
            # Process remaining items in queue
            while not self.record_queue.empty():
                try:
                    run_id, temperature = self.record_queue.get_nowait()
                    await self._record_to_database(run_id, temperature)
                    self.record_queue.task_done()
                except Exception as e:
                    self.logger.error(f"Error processing remaining data: {e}")
        except Exception as e:
            self.logger.exception(f"Fatal error in database recorder: {e}")

    async def _record_to_database(self, run_id: int, temperature: float) -> None:  # Changed from _log_to_database
        """Record temperature reading to database."""
        try:
            await self.db_manager.record_temperature(run_id, temperature)
        except Exception as e:
            self.logger.error(f"Error recording to database: {e}")

    async def _handle_temperature_update(
        self, app: 'TemperatureUI', 
        current_temp: float, 
        current_time: datetime,
        target_temp: float,
        direction: Literal['increases', 'decreases'],
        last_announced_temp: Optional[float],
        target_reached_flag: bool,
        start_time: float
    ) -> tuple[bool, Optional[float]]:
        """Handle temperature updates including logging and notifications."""
        try:
            # Update the UI with current temperature
            await app.update_temperature(current_temp, current_time)
            
            # Record temperature directly if enabled
            if self.recording_enabled and self.run_id is not None:
                await self.db_manager.record_temperature(self.run_id, current_temp)
            
            # Update graph
            elapsed_time = time.time() - start_time
            await self.temperature_buffer.add(current_temp, elapsed_time)
            self.logger.debug(f"Added to buffer - Temp: {current_temp}, Time: {elapsed_time}")
            
            # Check if target has been reached
            if not target_reached_flag and target_reached(direction, target_temp, current_temp):
                target_reached_flag = True
                if not self._shutting_down:
                    # Only play sound if voice is enabled
                    if self.config_manager.voice_config.enabled:
                        await self.play_tts_message(f"Target temperature of {target_temp:.1f} degrees has been reached")
                    
                    # Show popup
                    popup = NotificationPopup(f"Target temperature of {target_temp:.1f}°C has been reached!")
                    result = await app.push_screen(popup)
                    
                    # Send notification with high priority for target reached
                    await self.notification_manager.send_notification(
                        message=f"Target temperature of {target_temp:.1f}°C has been reached! Current temperature: {current_temp:.1f}°C",
                        title="Temperature Target Reached",
                        priority="high",
                        tags=["alarm_clock"]
                    )
                    
                    self.logger.info(f"Target temperature {target_temp:.1f}°C reached")

            # Announce temperature changes
            current_time = time.time()
            if (self.config_manager.voice_config.enabled and
                (last_announced_temp is None or 
                (abs(current_temp - last_announced_temp) >= 1.0 and 
                 current_time - self.last_announcement_time >= ANNOUNCE_PERIOD_S))):
                if not self._shutting_down:
                    await self.play_tts_message(f"Current temperature is {current_temp:.1f} degrees")
                    # Send regular temperature updates with default priority
                    await self.notification_manager.send_notification(
                        message=f"Current temperature is {current_temp:.1f}°C",
                        title="Temperature Update",
                        priority="default"
                    )

                self.last_announcement_time = current_time
                last_announced_temp = current_temp
            
            return target_reached_flag, last_announced_temp
            
        except Exception as e:
            self.logger.error(f"Error in temperature update: {e}")
            return target_reached_flag, last_announced_temp

    async def play_tts_message(self, message: str) -> None:
        """Convert text to speech and play it asynchronously."""
        try:
            self.logger.debug(f"Starting TTS playback: '{message}'")
            
            # Convert message to speech and write to BytesIO
            tts = await asyncio.to_thread(lambda: gTTS(text=message, lang='en'))
            fp = BytesIO()
            await asyncio.to_thread(tts.write_to_fp, fp)
            fp.seek(0)
            
            self.logger.debug("Text-to-speech conversion completed")
            
            # Update the sound source and play
            self.tts_player.sound_source = fp
            await self.tts_player.start()
            
            # Wait for sound to finish naturally
            while pygame.mixer.get_busy():
                await asyncio.sleep(0.1)
            
            self.logger.debug("TTS playback completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error in TTS playback: {e}")
            self.logger.debug(f"Detailed error information: {str(e)}", exc_info=True)

    async def initialize(self) -> None:
        """Initialize the monitor including database."""
        await self.db_manager.initialize()

    async def cleanup(self):
        """Clean up resources and ensure all tasks are terminated."""
        try:
            # Set exit flag first to stop all running loops
            self.exit_flag.set()
            
            # Cancel and await all running tasks
            for task in self.running_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        self.logger.debug(f"Task {task} cancelled")
                    except Exception as e:
                        self.logger.error(f"Error awaiting task {task}: {e}")
            self.running_tasks.clear()

            # Clean up sensor connection
            if self.temp_sensor:
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self._disconnect_sensor)
                except Exception as e:
                    self.logger.error(f"Error disconnecting sensor: {e}")
                finally:
                    self.logger.debug("Disconnected from sensor")
                    self.temp_sensor = None

            # Clean up notification manager
            if hasattr(self, 'notification_manager'):
                await self.notification_manager.cleanup()

            # Clean up database connection
            await self.db_manager.close()

            # Add cleanup for tts_player
            if hasattr(self, 'tts_player'):
                await self.tts_player.cleanup()

        except Exception as e:
            self.logger.exception(f"Error during cleanup: {e}")
        finally:
            self.logger.info("Cleanup completed")

    def _disconnect_sensor(self):
        """Safely disconnect the sensor in a synchronous context."""
        if self.temp_sensor:
            try:
                if self.temp_sensor.is_connected():
                    self.temp_sensor.disconnect()
                    time.sleep(0.5)  # Small delay to ensure disconnect completes
            except Exception as e:
                self.logger.error(f"Error in _disconnect_sensor: {e}")

    async def enable_recording(self, target_temp: float, direction: str) -> None:
        """Enable temperature recording to database."""
        try:
            self.logger.debug(f"Enabling recording - Target: {target_temp}°C, Direction: {direction}")
            self.run_id = await self.db_manager.create_run(target_temp, direction)
            self.recording_enabled = True
            self.logger.info(f"Recording enabled with run_id: {self.run_id}")
            
        except Exception as e:
            self.logger.exception(f"Error enabling recording: {e}")
            self.recording_enabled = False
            self.run_id = None

    async def disable_recording(self) -> None:
        """Disable temperature recording."""
        try:
            self.logger.debug("Disabling temperature recording")
            self.recording_enabled = False
            self.run_id = None
            self.logger.info("Recording disabled")
            
        except Exception as e:
            self.logger.exception(f"Error disabling recording: {e}")

    async def toggle_recording(self) -> bool:
        """Toggle recording state."""
        if self.recording_enabled:
            await self.disable_recording()
        else:
            # Can't enable without parameters
            # await self.enable_recording()  # This won't work
            self.logger.error("Cannot enable recording without target temperature and direction")
            return False
        return self.recording_enabled

def signal_handler(sig, frame):
    """
    Handle termination signals by setting the exit flag.

    Args:
        sig: The signal number
        frame: The current stack frame
    """
    print("\nInterrupt received, preparing to exit...")
    exit_flag.set()  # Now correctly references the global exit_flag

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Determine whether the requested target temperature has been reached
def target_reached(direction: Literal['increases', 'decreases'], target_temp: float, current_temp: float) -> bool:
    """
    Determine whether the requested target temperature has been reached.

    Args:
        direction (Literal['increases', 'decreases']): The direction of temperature change.
        target_temp (float): The target temperature.
        current_temp (float): The current temperature.

    Returns:
        bool: True if the target temperature has been reached, False otherwise.
    """
    if direction == 'increases':
        return current_temp >= target_temp
    if direction == 'decreases':
        return current_temp <= target_temp
    return False

# Scan for available PASCO BLE devices and allow the user to select one
def select_sensor() -> Optional[PASCOBLEDevice]:
    """
    Scan for available PASCO BLE devices and allow the user to select one.

    Returns:
        Optional[PASCOBLEDevice]: The selected temperature sensor object, or None if no devices found.
    """
    temp_sensor = PASCOBLEDevice()
    found_devices = temp_sensor.scan()

    if not found_devices:
        print("No Devices Found")
        logger.error("No Devices Found")
        return None

    print('\nDevices Found')   
    for i, ble_device in enumerate(found_devices):
        print(f'{i}: {ble_device.name}')

    if len(found_devices) > 1:
        while True:
            try:
                selection = input('Select a device (enter the number): ').strip()
                selected_index = int(selection)
                if 0 <= selected_index < len(found_devices):
                    break
                else:
                    print(f"Please enter a number between 0 and {len(found_devices) - 1}")
            except ValueError:
                print("Please enter a valid number")
    else:
        selected_index = 0
        print("Only one device found. Automatically selecting it.")

    temp_sensor.connect(found_devices[selected_index])
    print(f"Connected to: {found_devices[selected_index].name}")
    return temp_sensor

async def update_graph(temperature: float, timestamp: float):
    """Thread-safe update of the temperature graph data."""
    await temperature_buffer.add(temperature, timestamp)

async def display_graph():
    """Display the temperature graph."""
    async with graph_lock:
        temperatures, timestamps = await temperature_buffer.get_data()
        plt.clf()
        plt.plot(timestamps, temperatures)
        plt.title("Temperature over Time")
        plt.xlabel("Time (s)")
        plt.ylabel("Temperature (°C)")
        plt.show()

async def graph_display_loop():
    """Continuously update and display the graph."""
    while not exit_flag.is_set():
        await display_graph()
        await asyncio.sleep(5)  # Update every 5 seconds

class ResourceManager:
    """Manage application resources and ensure proper cleanup"""
    
    def __init__(self):
        self.db_connection: Optional[AioConnection] = None
        self.temp_sensor: Optional[PASCOBLEDevice] = None
        self._lock = asyncio.Lock()

    async def cleanup(self):
        """Clean up all resources"""
        async with self._lock:
            if self.temp_sensor:
                try:
                    self.temp_sensor.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting sensor: {e}")
                self.temp_sensor = None

            if self.db_connection:
                try:
                    await self.db_connection.close()
                except Exception as e:
                    logger.error(f"Error closing database: {e}")
                self.db_connection = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

async def setup_signal_handlers(app: TemperatureUI):
    """Set up proper async signal handlers"""
    loop = asyncio.get_running_loop()
    
    def handle_signal():
        logger.info("Received shutdown signal")
        asyncio.create_task(app.stop_monitoring())  # Changed from cleanup_and_exit to stop_monitoring

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Signal handling may not be implemented on some platforms
            logger.warning(f"Signal handling not supported for {sig}")

class TemperatureAlarmApp:
    """The main Temperature Alarm application."""
    
    def __init__(self):
        self.resource_manager = None
        self.monitoring = False
        self.target_temp = None
        self.current_temp = None

    async def on_mount(self) -> None:
        """Handle the app mount event."""
        self.resource_manager = ResourceManager()

    async def update_temperature(self, temperature: float, timestamp: datetime) -> None:
        """Update the temperature display."""
        self.current_temp = temperature
        await self.call_later(self._update_display)

    async def _update_display(self) -> None:
        """Update the display widgets."""
        if hasattr(self, 'temp_display'):
            self.temp_display.update_temperature(self.current_temp)

    async def stop_monitoring(self) -> None:
        """Stop temperature monitoring."""
        try:
            self.monitoring = False
            
            # Disable recording if it was enabled
            if self.recording_enabled:
                await self.disable_recording()
                
            if hasattr(self, 'monitor_button'):
                self.monitor_button.label = "Start Monitoring"
                self.monitor_button.variant = "success"
                
        except Exception as e:
            self.logger.exception(f"Error stopping monitoring: {e}")

    async def cleanup_and_exit(self) -> None:
        """Clean up resources and exit the application."""
        logger.info("Starting cleanup")
        if self.monitoring:
            await self.stop_monitoring()
        if self.resource_manager:
            await self.resource_manager.cleanup()
        self.exit()

async def main():
    logger.info("Starting main function")
    
    try:
        app = TemperatureAlarmApp()
        monitor = TemperatureMonitor()
        app.monitor = monitor
        
        # Initialize monitor (including database)
        await monitor.initialize()
        
        # Run the app
        await app.run_async()
        
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
    finally:
        if 'monitor' in locals():
            await monitor.cleanup()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())

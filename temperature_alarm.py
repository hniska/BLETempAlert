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
from sound_manager import AlarmSound
from threading import Event
from config_manager import ConfigManager
from notification_manager import NotificationManager
import pygame

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
        self.alarm = AlarmSound("alarm.mp3")  # Update path to your MP3 file

    BINDINGS = [("escape", "dismiss", "Dismiss")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the popup."""
        yield Container(
            Label(self.message),
            Button("OK", variant="primary", id="ok_button"),
            id="popup_container",
        )

    def on_mount(self) -> None:
        """Start the alarm when the popup is mounted."""
        self.alarm.start()

    def _stop_alarm(self) -> None:
        """Stop the alarm sound immediately."""
        if hasattr(self, 'alarm'):
            self.alarm.stop()
            # Add a small delay to ensure the sound stops
            time.sleep(0.1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press event."""
        if event.button.id == "ok_button":
            self._stop_alarm()  # Stop alarm before dismissing
            self.dismiss(True)

    def on_key(self, event: Key) -> None:
        """Handle key press event."""
        if event.key == "escape":
            self._stop_alarm()  # Stop alarm before dismissing
            self.dismiss(False)

    def on_unmount(self) -> None:
        """Ensure alarm is stopped when popup is unmounted."""
        self._stop_alarm()

class TemperatureMonitor(BaseTemperatureMonitor):
    def __init__(self, sample_rate: float = 2.0):
        super().__init__(sample_rate)
        self._setup_logging()
        self.thread_pool = ThreadPoolExecutor(max_workers=1)
        self.exit_flag = exit_flag  # Use the global exit flag
        
        # Initialize notification manager with config
        config_manager = ConfigManager()
        self.notification_manager = NotificationManager(config_manager.ntfy_config)
        
        # Store config manager reference
        self.config_manager = config_manager
        
    def _setup_logging(self):
        """Set up logging for the temperature monitor"""
        self.logger = logger

    async def monitor_temperature(self, app: TemperatureUI,  # Changed from TemperatureAlarmApp to TemperatureUI
                                direction: Literal['increases', 'decreases'], 
                                target_temp: float) -> None:
        """Monitor temperature and handle announcements and logging"""
        try:
            self.logger.debug("Starting temperature monitoring")
            next_read_time = time.time()
            last_announced_temp: Optional[float] = None
            target_reached_flag = False
            start_time = time.time()
            consecutive_errors = 0
            max_consecutive_errors = 5
            self.last_announcement_time = 0  # Initialize last announcement time

            # Reset exit flag when starting monitoring
            self.exit_flag.clear()

            # Create a monitoring task that doesn't block the event loop
            self.logger.debug(f"Creating monitoring task direction: {direction}, target_temp: {target_temp} next_read_time: {next_read_time} last_announced_temp: {last_announced_temp} target_reached_flag: {target_reached_flag} start_time: {start_time} consecutive_errors: {consecutive_errors} max_consecutive_errors: {max_consecutive_errors}")
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
                        next_read_time = time.time() + self.sample_rate  # Use sample_rate instead of CHECK_PERIOD_S

                        target_reached_flag, last_announced_temp = await self._handle_temperature_update(
                            app, current_temp, current_time, 
                            target_temp, direction, last_announced_temp,
                            target_reached_flag, start_time
                        )
                        
                    await asyncio.sleep(min(0.1, self.sample_rate / 10))  # Scale sleep with sample rate
                except asyncio.CancelledError:
                    raise  # Re-raise CancelledError to handle it properly
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
        """Safely read temperature from the sensor.

        Returns:
            Optional[float]: The current temperature or None if reading fails.
        """
        if not self.temp_sensor:
            self.logger.warning("Temperature sensor is not initialized.")
            return None
        try:
            return self.temp_sensor.read_data('Temperature')
        except Exception as e:
            self.logger.warning(f"Error reading temperature: {e}")
            return None

    async def cleanup(self):
        """Clean up resources and ensure all tasks/threads are terminated."""
        self.logger.info("Starting cleanup")
        self._shutting_down = True
        
        try:
            # Set exit flag first to stop all running loops
            self.exit_flag.set()
            
            # Cancel and await all running tasks
            for task in self.running_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self.logger.error(f"Error cancelling task {task}: {e}")
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

            # Shutdown thread pool
            async with self._thread_pool_lock:
                if hasattr(self, 'thread_pool') and not self.thread_pool._shutdown:
                    try:
                        self.thread_pool.shutdown(wait=False)
                        await asyncio.sleep(0.5)  # Brief wait for pending tasks
                    except Exception as e:
                        self.logger.error(f"Error in thread pool shutdown: {e}")
                    finally:
                        try:
                            self.thread_pool.shutdown(wait=True)  # Force shutdown
                        except Exception as e:
                            self.logger.error(f"Error in forced thread pool shutdown: {e}")

            # Clean up notification manager
            if hasattr(self, 'notification_manager'):
                await self.notification_manager.cleanup()

            # Clean up database connection
            if self.db_connection:
                try:
                    self.db_connection.close()
                except Exception as e:
                    self.logger.error(f"Error closing database: {e}")
                finally:
                    self.db_connection = None

            # Drain log queue
            try:
                while not self.log_queue.empty():
                    try:
                        self.log_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
            except Exception as e:
                self.logger.error(f"Error draining log queue: {e}")

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
                    # Add a small delay to ensure disconnect completes
                    time.sleep(0.5)
            except Exception as e:
                self.logger.error(f"Error in _disconnect_sensor: {e}")

    async def _handle_temperature_update(
        self, app: 'TemperatureAlarmApp', 
        current_temp: float, 
        current_time: datetime,
        target_temp: float,
        direction: Literal['increases', 'decreases'],
        last_announced_temp: Optional[float],
        target_reached_flag: bool,
        start_time: float
    ) -> tuple[bool, Optional[float]]:
        """
        Handle temperature updates including logging and notifications.
        
        Args:
            app: The TemperatureAlarmApp instance
            current_temp: Current temperature reading
            current_time: Current timestamp
            target_temp: Target temperature to monitor for
            direction: Direction of temperature change to monitor
            last_announced_temp: Last temperature that was announced
            target_reached_flag: Whether target has been reached
            start_time: Start time of monitoring
            
        Returns:
            tuple[bool, Optional[float]]: Updated target_reached_flag and last_announced_temp
        """
        try:
            # Update the UI with current temperature
            await app.update_temperature(current_temp, current_time)
            
            # Log temperature if enabled
            if self.logging_enabled and self.run_id is not None:
                await self.log_queue.put((self.run_id, current_temp))
            
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
                        await self.play_sound_async(f"Target temperature of {target_temp:.1f} degrees has been reached")
                    
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
                    
                # Continue monitoring - target_reached_flag prevents repeated notifications

            # Announce temperature changes
            current_time = time.time()
            if (self.config_manager.voice_config.enabled and
                (last_announced_temp is None or 
                (abs(current_temp - last_announced_temp) >= 1.0 and 
                 current_time - self.last_announcement_time >= ANNOUNCE_PERIOD_S))):
                if not self._shutting_down:
                    await self.play_sound_async(f"Current temperature is {current_temp:.1f} degrees")
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
    
    def play_sound(self, message: str) -> None:
        """
        Play a text-to-speech message directly from memory without saving to disk.
        
        Args:
            message: The text message to convert to speech and play
        
        Raises:
            RuntimeError: If pygame mixer initialization fails
            Exception: For other errors during TTS or playback
        """
        try:
            # Initialize pygame mixer first to catch initialization errors early
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                
            # Convert message to speech and write to BytesIO (in MP3 format)
            tts = gTTS(text=message, lang='en')
            fp = BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)

            # Load and play audio from BytesIO object
            pygame.mixer.music.load(fp, 'mp3')
            pygame.mixer.music.play()

            # Keep the program running while the audio plays
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)

        except Exception as e:
            print(f"Error playing sound: {e}")
        finally:
            # Clean up resources
            pygame.mixer.quit()

    async def play_sound_async(self, message: str) -> None:
        """
        Asynchronously play a text-to-speech message.
        
        Args:
            message: The text message to convert to speech and play
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self.thread_pool, self.play_sound, message)
        except Exception as e:
            self.logger.error(f"Error in play_sound_async: {e}")

    async def scan(self):
        """
        Scan for available PASCO BLE devices.
        
        Returns:
            List[BLEDevice]: List of found PASCO devices
        """
        try:
            # Create a new PASCOBLEDevice instance for scanning
            temp_sensor = PASCOBLEDevice()
            
            # Run the scan in a thread to avoid blocking
            loop = asyncio.get_running_loop()
            found_devices = await loop.run_in_executor(
                self.thread_pool, 
                temp_sensor.scan
            )
            
            self.logger.info(f"Found {len(found_devices)} device(s)")
            return found_devices
            
        except Exception as e:
            self.logger.error(f"Error scanning for devices: {e}")
            raise

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

async def log_temperature(temperature: float):
    """Add temperature to the logging queue."""
    global run_id
    if logging_enabled and run_id is not None:
        await log_queue.put((run_id, temperature))

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

async def database_logger():
    """Function to handle database logging in the main thread."""
    global db_connection, exit_flag
    while not exit_flag.is_set() or not log_queue.empty():
        try:
            run_id, temperature = await log_queue.get()
            cursor = db_connection.cursor()
            cursor.execute(
                "INSERT INTO temperature_logs (run_id, temperature) VALUES (?, ?)",
                (run_id, temperature)
            )
            db_connection.commit()
        except asyncio.QueueEmpty:
            continue
        except Exception as e:
            print(f"Error logging to database: {e}")
        await asyncio.sleep(0.1)  # Small delay to prevent CPU hogging

class ResourceManager:
    """Manage application resources and ensure proper cleanup"""
    
    def __init__(self):
        self.db_connection: Optional[sqlite3.Connection] = None
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
                    self.db_connection.close()
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
        loop.add_signal_handler(sig, handle_signal)

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
        self.monitoring = False
        if hasattr(self, 'monitor_button'):
            self.monitor_button.label = "Start Monitoring"
            self.monitor_button.variant = "success"

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
    asyncio.run(main())


import logging
import asyncio
import signal
from typing import List, Optional, Tuple
from datetime import datetime
import nest_asyncio
import plotext as plt
import textual.css.query  # Add this import at the top of the file

nest_asyncio.apply()

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Button, Input, Label, Select, Switch, Pretty
from textual.containers import Container, Horizontal, Vertical
from pasco.pasco_ble_device import PASCOBLEDevice
from textual.message import Message
from logging_config import setup_logging
from temperature_alarm import TemperatureMonitor, select_sensor, exit_flag
from temperature_types import TemperatureUI
from textual_plotext import PlotextPlot  # Add this import

logger = setup_logging(__name__)

class TemperatureDisplay(Static):
    """A widget to display the current temperature and last update time."""

    def __init__(self):
        super().__init__("Current Temperature: N/A\nLast Update: N/A")

    def update_temperature(self, temperature: float, update_time: datetime):
        self.update(f"Current Temperature: {temperature:.1f}°C\nLast Update: {update_time.strftime('%Y-%m-%d %H:%M:%S')}")

class TargetTemperature(Static):
    """A widget to display the target temperature."""

    def __init__(self):
        super().__init__("Target Temperature: Not set")

    def update_target(self, temperature: float):
        self.update(f"Target Temperature: {temperature:.1f}°C")

class DevicesFound(Message):
    """Message sent when devices are found."""
    def __init__(self, options: list) -> None:
        self.options = options
        super().__init__()

class TemperatureAlarmApp(App):
    """The main Textual app for the Temperature Alarm."""

    CSS = """
    TemperatureDisplay, TargetTemperature {
        height: 3;
        content-align: center middle;  # This is correct for Static widgets
        background: $boost;
        width: 100%;
    }

    PlotextPlot {
        height: 60%;  # Changed from fixed 20 lines to 60% of available space
        border: solid green;
        width: 100%;
        margin: 0 0;
        padding: 0 0;
    }

    #device_selection_container {
        height: 3;
        margin: 1 0;
    }

    #scan_button {
        width: 30%;
    }

    #device_select {
        width: 70%;
    }

    #target_input_container {
        height: 3;
        margin: 1 0;
    }

    #target_input {
        width: 100%;
    }

    #button_container {
        height: auto;
        margin: 1 0;
        align: center middle;
    }

    #toggle_monitoring, #exit_button {
        width: 45%;  /* Reduced from 100% to allow buttons to sit side by side */
        margin: 1 1;
    }

    .vertical-separator {
        width: 1;
        height: 100%;
        background: $primary-background-lighten-2;
        margin: 0 2;
    }

    NotificationPopup {
        align: center middle;
    }

    #popup_container {
        background: $boost;
        padding: 1 2;
        border: thick $primary;
        width: 40;
        height: auto;
        align: center middle;
    }

    #popup_container Label {
        content-align: center middle;
        width: 100%;
        margin: 1 0;
    }

    #popup_container Button {
        margin: 1 0;
        width: 100%;
    }

    #settings_row {
        height: 3;
        margin: 1 0;
        align: left middle;  # Align the entire row
    }

    #target_input_container {
        width: 50%;
        height: 3;
        margin: 0 1;
        content-align: left middle;  # For Static content alignment
    }

    #target_input {
        width: 50%;
    }

    #notification_settings {
        width: 50%;
        height: 3;
        margin: 0 1;
        content-align: left middle;  # For Static content alignment
    }

    #notification_settings Label {
        margin-right: 1;
        content-align: left middle;  # For Label content alignment
    }

    #ntfy_topic {
        margin-left: 2;
        color: $text;
        content-align: left middle;  # For Label content alignment
    }

    Switch {
        margin: 0 1;
        align: center middle;  # For widget alignment in container
    }

    #ntfy_topic_input {
        width: 30%;  # Adjust width as needed
        margin-left: 1;
    }

    #voice_switch {
        margin-left: 1;
        align: center middle;
    }
    """

    def __init__(self):
        super().__init__()
        self.monitor = None  # Will be set to a BaseTemperatureMonitor instance
        self.target_temp: Optional[float] = None
        self.monitoring: bool = False
        self.found_devices = []
        self.device_map = {}  # Initialize the device map dictionary
        self.logger = setup_logging(__name__)
        self.graph_update_task: Optional[asyncio.Task] = None
        
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Horizontal(
            Button("Scan for Devices", id="scan_button", variant="primary"),
            Select(
                options=[],
                prompt="Select a device",
                id="device_select"
            ),
            id="device_selection_container"
        )
        yield TemperatureDisplay()
        yield TargetTemperature()
        yield PlotextPlot(id="temperature_plot")
        # Combined target temperature and notifications row
        yield Horizontal(
            # Left side - Target Temperature
            Horizontal(
                Label("Enter target temperature: "),
                Input(placeholder="e.g., 25.5", id="target_input"),
                id="target_input_container"
            ),
            # Right side - Notifications
            Horizontal(
                Label("Notifications:"),
                Switch(value=False, id="ntfy_switch"),
                Label("Topic:"),
                Input(placeholder="ntfy topic", id="ntfy_topic_input"),
                Label("Voice:"),
                Switch(value=True, id="voice_switch"),
                id="notification_settings"
            ),
            id="settings_row"
        )
        yield Horizontal(
            Button("Start Monitoring", id="toggle_monitoring", variant="success"),
            Static(classes="vertical-separator"),
            Button("Exit", id="exit_button", variant="error"),
            id="button_container"
        )
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        try:
            if event.button.id == "scan_button":
                await self._scan_for_devices()  # Call the new method
            elif event.button.id == "toggle_monitoring":
                await self._toggle_monitoring()
            elif event.button.id == "exit_button":
                await self._exit_app()
        except Exception as e:
            self.logger.error(f"Error handling button press: {e}")
            self.notify(f"Error: {str(e)}", severity="error")


    async def _scan_for_devices(self):
        """Scan for available PASCO BLE devices."""
        if not self.monitor:
            self.notify("Monitor not initialized", severity="error")
            return

        temp_sensor = PASCOBLEDevice()  # Create temporary sensor for scanning
        found_devices = temp_sensor.scan()

        if not found_devices:
            self.notify("No devices found", severity="warning")
            return

        device_select = self.query_one("#device_select")
        self.found_devices = found_devices
        
        device_options = []
        self.device_map = {}
        for i, device in enumerate(found_devices):
            try:
                device_id = device.name.split()[1].split('>')[0]
                self.device_map[device_id] = i
                device_options.append((device_id, device_id))
            except (IndexError, AttributeError):
                self.device_map[device.name] = i
                device_options.append((device.name, device.name))
        
        device_select.set_options(device_options)
        
        # Remove automatic connection for single device
        # Instead, just set the dropdown value which will trigger the connection
        if len(found_devices) == 1:
            first_option = device_options[0][0]
            device_select.value = first_option
            # Remove the direct connection call here

    async def _connect_device(self, device_index: int):
        """
        Connect to the selected PASCO BLE device.
        
        Args:
            device_index: The index of the device in self.found_devices
        """
        try:
            # Create a new PASCOBLEDevice instance
            temp_sensor = PASCOBLEDevice()
            # Connect to the selected device using the BLEDevice object
            selected_device = self.found_devices[device_index]
            
            # Try to connect with a timeout
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: temp_sensor.connect(selected_device)
                    ),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                raise Exception("Connection timeout")
            
            if not temp_sensor.is_connected():
                raise Exception("Failed to establish connection")
            
            # Store the connected sensor in the monitor
            self.monitor.temp_sensor = temp_sensor
            
            self.notify(f"Connected to: {selected_device.name}", severity="success")
            
        except Exception as e:
            error_msg = f"Failed to connect: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.notify(error_msg, severity="error")
            
            # Clean up the failed connection attempt
            if 'temp_sensor' in locals():
                try:
                    temp_sensor.disconnect()
                except:
                    pass

    async def _toggle_monitoring(self):
        """Toggle between starting and stopping monitoring."""
        try:
            if not self.monitoring:
                await self.start_monitoring()
            else:
                await self.stop_monitoring()
        except Exception as e:
            self.logger.error(f"Error toggling monitoring: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def start_monitoring(self):
        """Start the temperature monitoring process."""
        if not self.target_temp:
            self.notify("Please set a target temperature first", severity="error")
            return
        
        if not self.monitor or not self.monitor.temp_sensor:
            self.notify("Please connect to a device first", severity="error")
            return

        try:
            self.monitoring = True
            button = self.query_one("#toggle_monitoring", Button)
            button.label = "Stop Monitoring"
            button.variant = "error"

            # Initialize the plot
            plot = self.query_one(PlotextPlot)
            plot.plt.clear_figure()
            plot.plt.theme('textual-design-dark')
            
            # Start the graph update task
            if self.graph_update_task:
                self.graph_update_task.cancel()
            self.graph_update_task = asyncio.create_task(self._update_graph_periodically())
            
            # Start the monitoring process
            await self.monitor.monitor_temperature(self, 'increases', self.target_temp)
        except Exception as e:
            self.logger.error(f"Error starting monitoring: {e}")
            self.notify(f"Error: {str(e)}", severity="error")
            await self.stop_monitoring()

    async def stop_monitoring(self):
        """Stop the temperature monitoring process."""
        try:
            self.monitoring = False
            button = self.query_one("#toggle_monitoring", Button)
            button.label = "Start Monitoring"
            button.variant = "success"
            
            # Set the exit flag
            exit_flag.set()
            
            # Cancel graph update task
            if self.graph_update_task:
                self.graph_update_task.cancel()
                try:
                    await self.graph_update_task
                except asyncio.CancelledError:
                    pass
                self.graph_update_task = None
            
            if self.monitor:
                await self.monitor.cleanup()
        except Exception as e:
            self.logger.error(f"Error stopping monitoring: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def _exit_app(self):
        """Clean up and exit the application."""
        self.notify("Shutting down...", severity="warning")
        
        # Stop monitoring if active
        if self.monitoring:
            await self.stop_monitoring()
        
        # Ensure monitor cleanup
        if self.monitor:
            await self.monitor.cleanup()
        
        # Exit the app
        self.exit()

    def on_mount(self):
        """Handle the app mount event."""
        from logging_config import TUIHandler  # Import at use to avoid circular imports
        
        self.title = "Temperature Alarm"
        # Register app with TUI handler
        TUIHandler.set_app(self)
        
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self._handle_signal()))
        
        # Initialize notification settings
        self._init_notification_settings()

    async def _handle_signal(self):
        """Handle interrupt signals."""
        self.notify("Received shutdown signal", severity="warning")
        await self._exit_app()

    async def update_temperature(self, temperature: float, timestamp: datetime):
        """Update the temperature display."""
        try:
            temp_display = self.query_one(TemperatureDisplay)
            temp_display.update_temperature(temperature, timestamp)
        except textual.css.query.NoMatches:
            # Silently ignore if we can't update during popup display
            self.logger.debug("Temperature display not accessible (popup might be shown)")

    async def update_graph(self, temperatures: List[float], timestamps: List[float]) -> None:
        """Update the temperature graph using PlotextPlot."""
        if not temperatures or not timestamps:
            self.logger.debug("No data to plot")
            return

        try:
            # Try to get the plot widget, return if not found (e.g., when popup is shown)
            try:
                plot = self.query_one(PlotextPlot)
            except textual.css.query.NoMatches:
                self.logger.debug("Plot widget not accessible (popup might be shown)")
                return
            
            plt = plot.plt  # Get the plotext instance from PlotextPlot

            self.logger.debug(f"Plotting data - Temps: {temperatures}, Times: {timestamps}")

            # Clear previous data
            plt.clear_figure()
            
            # Convert timestamps to relative time (seconds from start)
            start_time = timestamps[0]
            relative_times = [t - start_time for t in timestamps]

            # Calculate axis limits with padding
            y_min = min(min(temperatures), self.target_temp if self.target_temp is not None else float('inf'))
            y_max = max(max(temperatures), self.target_temp if self.target_temp is not None else float('-inf'))
            padding = max(0.1, (y_max - y_min) * 0.1)  # At least 0.1 padding
            y_min -= padding
            y_max += padding

            self.logger.debug(f"Plot ranges - X: [0, {max(relative_times)}], Y: [{y_min}, {y_max}]")

            # Set up the plot
            plt.theme('dark')  # Try different theme
            plt.plot_size(None, None)  # Let textual handle the size
            plt.ylim(y_min, y_max)
            plt.xlim(0, max(relative_times) + 1)  # Add 1 for padding
            
            # Plot the temperature data
            plt.plot(relative_times, temperatures, 
                    color="red", 
                    marker="dot", 
                    label="Temperature")
            
            # Plot target temperature line if set
            if self.target_temp is not None:
                # Add horizontal line for target temperature
                plt.hline(self.target_temp, "green")
            
            plt.title("Temperature vs Time")
            plt.xlabel("Time (s)")
            plt.ylabel("Temperature (°C)")
            plt.grid(True)  # Add grid for better readability
            #plt.show_legend()  # Show the legend to identify the lines
            
            # Force a refresh of the plot
            plot.refresh()
            self.logger.debug("Plot updated successfully")

        except Exception as e:
            self.logger.error(f"Error updating graph: {e}", exc_info=True)

    async def on_input_submitted(self, message: Input.Submitted) -> None:
        """Handle input submission events."""
        if message.input.id == "target_input":
            await self._set_target_temperature(message.value)
        elif message.input.id == "ntfy_topic_input":
            await self._update_ntfy_topic(message.value)

    async def _set_target_temperature(self, value: str) -> None:
        """
        Set the target temperature from input value.
        
        Args:
            value: The string value from the input field
        """
        try:
            temp = float(value)
            if -50 <= temp <= 150:  # reasonable temperature range
                self.target_temp = temp
                target_display = self.query_one(TargetTemperature)
                target_display.update_target(temp)
                self.notify(f"Target temperature set to {temp}°C", severity="success")
            else:
                self.notify("Temperature must be between -50°C and 150°C", severity="error")
        except ValueError:
            self.notify("Please enter a valid number", severity="error")

    async def on_input_changed(self, message: Input.Changed) -> None:
        """Handle input change events."""
        if message.input.id == "target_input":
            # Optionally validate input as user types
            if message.value and not message.value.replace(".", "").replace("-", "").isdigit():
                self.notify("Please enter a valid number", severity="error")

    async def on_select_changed(self, message: Select.Changed) -> None:
        """Handle device selection changes."""
        if message.select.id == "device_select" and message.value is not None:
            # Add a check to prevent connecting if already connected
            if (self.monitor and self.monitor.temp_sensor and 
                self.monitor.temp_sensor.is_connected()):
                self.logger.debug("Device already connected, skipping connection attempt")
                return
                
            device_index = self.device_map.get(message.value)
            if device_index is not None:
                await self._connect_device(device_index)

    async def cleanup(self) -> None:
        """Clean up resources without exiting."""
        logger.info("Starting application cleanup")
        
        try:
            from logging_config import TUIHandler
            # Remove app from TUI handler
            TUIHandler.remove_app(self)
            
            # Stop monitoring if active
            if self.monitoring:
                await self.stop_monitoring()
            
            # Ensure monitor cleanup with timeout
            if self.monitor:
                try:
                    await asyncio.wait_for(self.monitor.cleanup(), timeout=10.0)
                except asyncio.TimeoutError:
                    logger.error("Monitor cleanup timed out")
                except Exception as e:
                    logger.error(f"Error during monitor cleanup: {e}")
                
            # Clear any pending notifications
            self.notify("Shutting down...", severity="warning")
            
            # Wait briefly for final cleanup operations
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.exception(f"Error during app cleanup: {e}")

    async def cleanup_and_exit(self) -> None:
        """Clean up resources and exit the application."""
        await self.cleanup()
        self.exit()

    async def _update_graph_periodically(self):
        """Periodically update the temperature graph."""
        self.logger.info("Starting graph update loop")
        try:
            while self.monitoring:
                if self.monitor and hasattr(self.monitor, 'temperature_buffer'):
                    temps, times = await self.monitor.temperature_buffer.get_data()
                    self.logger.debug(f"Retrieved data - Temps: {len(temps)} points, Times: {len(times)} points")
                    if temps and times:  # Only update if we have data
                        try:
                            await self.update_graph(temps, times)
                        except Exception as e:
                            # Log the error but continue the loop
                            self.logger.debug(f"Graph update skipped: {e}")
                else:
                    self.logger.debug("No temperature buffer available")
                # Update graph at half the sample rate for smooth display
                await asyncio.sleep(self.monitor.sample_rate / 2 if self.monitor else 1.0)
        except asyncio.CancelledError:
            self.logger.info("Graph update loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in graph update loop: {e}", exc_info=True)

    # Example of showing popup from any method in TemperatureAlarmApp
    async def show_notification(self, message: str) -> bool:
        """Show a notification popup with the given message.
        
        Args:
            message: The message to show in the popup
            
        Returns:
            bool: True if OK was clicked, False if dismissed
        """
        popup = NotificationPopup(message)
        return await self.push_screen(popup)

    def _init_notification_settings(self) -> None:
        """Initialize notification settings from config."""
        if hasattr(self, 'monitor') and hasattr(self.monitor, 'config_manager'):
            config_manager = self.monitor.config_manager
            
            # Update ntfy switch state
            ntfy_switch = self.query_one("#ntfy_switch", Switch)
            ntfy_switch.value = config_manager.ntfy_config.enabled
            
            # Update voice switch state
            voice_switch = self.query_one("#voice_switch", Switch)
            voice_switch.value = config_manager.voice_config.enabled
            
            # Update topic input
            topic_input = self.query_one("#ntfy_topic_input", Input)
            topic_input.value = config_manager.ntfy_config.topic

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle notification switch changes."""
        if not hasattr(self, 'monitor') or not hasattr(self.monitor, 'config_manager'):
            return

        if event.switch.id == "ntfy_switch":
            self.monitor.config_manager.update_ntfy_config(enabled=event.value)
            status = "enabled" if event.value else "disabled"
            self.notify(f"Notifications {status}", severity="information")
            
        elif event.switch.id == "voice_switch":
            self.monitor.config_manager.update_voice_config(event.value)
            status = "enabled" if event.value else "disabled"
            self.notify(f"Voice notifications {status}", severity="information")

    async def _update_ntfy_topic(self, topic: str) -> None:
        """Update the ntfy topic in config and notification manager.
        
        Args:
            topic: The new topic value
        """
        if hasattr(self, 'monitor') and hasattr(self.monitor, 'notification_manager'):
            try:
                # Update the config through config manager
                self.monitor.config_manager.update_ntfy_config(topic=topic)
                
                # Update the notification manager's config to match
                self.monitor.notification_manager.config.topic = topic
                
                self.notify(f"Ntfy topic updated to: {topic}", severity="success")
            except Exception as e:
                self.logger.error(f"Failed to update ntfy topic: {e}")
                self.notify(f"Failed to update topic: {str(e)}", severity="error")

if __name__ == "__main__":
    app = TemperatureAlarmApp()
    app.run()

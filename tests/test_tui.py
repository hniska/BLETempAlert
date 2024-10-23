import pytest
import sys
import asyncio
import logging  # Add this import
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from textual.app import App
from textual.widgets import Button, Input, Select
from datetime import datetime

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from tui import (
    TemperatureAlarmApp,
    TemperatureDisplay,
    TargetTemperature,
    TemperatureGraph
)

@pytest.fixture
async def app():
    """Fixture to create a TemperatureAlarmApp instance"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        pilot.app = app  # Store the app instance in the pilot
        yield pilot
        await pilot.close()

@pytest.fixture
def temp_display():
    """Fixture to create a TemperatureDisplay instance"""
    return TemperatureDisplay()

@pytest.fixture
def target_temp():
    """Fixture to create a TargetTemperature instance"""
    return TargetTemperature()

@pytest.fixture
def temp_graph():
    """Fixture to create a TemperatureGraph instance"""
    return TemperatureGraph()

def test_temperature_display_update(temp_display):
    """Test TemperatureDisplay update"""
    temp = 25.5
    time = datetime.now()
    temp_display.update_temperature(temp, time)
    expected = f"Current Temperature: {temp:.1f}°C\nLast Update: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    assert temp_display.renderable.plain == expected

def test_target_temperature_update(target_temp):
    """Test TargetTemperature update"""
    temp = 26.0
    target_temp.update_target(temp)
    expected = f"Target Temperature: {temp:.1f}°C"
    assert target_temp.renderable.plain == expected

@pytest.mark.asyncio
async def test_temperature_graph_update(temp_graph):
    """Test TemperatureGraph update"""
    temperatures = [25.0, 26.0, 27.0]
    timestamps = [0.0, 1.0, 2.0]
    temp_graph.update_graph(temperatures, timestamps)
    assert temp_graph.plot_initialized

@pytest.mark.asyncio
async def test_app_scan_for_devices():
    """Test scanning for devices"""
    print("\nStarting test_app_scan_for_devices")
    app = TemperatureAlarmApp()
    try:
        print("Setting up app.run_test()")
        async with app.run_test() as pilot:
            print("Setting up mock monitor")
            # Setup mock monitor and device
            mock_monitor = AsyncMock()
            mock_device = Mock(name="Test Device")
            mock_monitor.scan = AsyncMock(return_value=[mock_device])
            pilot.app.monitor = mock_monitor
            
            # Mock PASCOBLEDevice
            mock_pasco = Mock()
            mock_pasco.connect = Mock()
            
            print("Setting up PASCOBLEDevice mock")
            with patch('tui.PASCOBLEDevice', return_value=mock_pasco):
                print("Simulating click on scan button")
                await pilot.click("#scan_button")
                await pilot.pause()
                
                print("Verifying interactions")
                # Verify scan was called
                mock_monitor.scan.assert_called_once()
                # Verify device connection
                mock_pasco.connect.assert_called_once_with(mock_device)
                # Verify sensor was stored
                assert pilot.app.monitor.temp_sensor == mock_pasco
                
    except Exception as e:
        print(f"Test failed with error: {e}")
        pytest.fail(f"Test failed with error: {e}")
    finally:
        print("Starting cleanup")
        try:
            if hasattr(app, 'monitor') and app.monitor:
                print("Cleaning up monitor")
                await asyncio.wait_for(app.monitor.cleanup(), timeout=1.0)
            print("Cleaning up app")
            await asyncio.wait_for(app.cleanup(), timeout=1.0)
        except asyncio.TimeoutError:
            print("Cleanup timed out")
        except Exception as e:
            print(f"Cleanup error: {e}")
    print("Test completed")

@pytest.mark.asyncio
async def test_app_set_target_temperature():
    """Test setting target temperature"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        input_widget = pilot.app.query_one("#target_input", Input)
        
        # Set value directly
        input_widget.value = "25.5"
        # Trigger input submission
        await input_widget.action_submit()
        await pilot.pause()
        
        assert pilot.app.target_temp == 25.5

@pytest.mark.asyncio
async def test_app_toggle_monitoring():
    """Test toggling monitoring"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        # Setup mock monitor
        mock_monitor = AsyncMock()
        pilot.app.monitor = mock_monitor
        pilot.app.target_temp = 25.5
        mock_monitor.temp_sensor = Mock()
        
        # Get the button widget and call its handler directly
        button = pilot.app.query_one("#toggle_monitoring", Button)
        await pilot.app._toggle_monitoring()
        await pilot.pause()
        
        # Verify button state
        assert pilot.app.monitoring is True
        assert str(button.label) == "Stop Monitoring"

@pytest.mark.asyncio
async def test_app_cleanup():
    """Test app cleanup"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        mock_monitor = AsyncMock()
        pilot.app.monitor = mock_monitor
        
        await pilot.app.cleanup()
        
        mock_monitor.cleanup.assert_called_once()

@pytest.mark.asyncio
async def test_app_update_temperature():
    """Test updating temperature display"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        temp = 25.5
        time = datetime.now()
        
        await pilot.app.update_temperature(temp, time)
        
        temp_display = pilot.app.query_one(TemperatureDisplay)
        expected = f"Current Temperature: {temp:.1f}°C\nLast Update: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        assert temp_display.renderable.plain == expected

@pytest.mark.asyncio
async def test_app_handle_device_selection():
    """Test handling device selection"""
    app = TemperatureAlarmApp()
    async with app.run_test() as pilot:
        # Setup mock monitor
        mock_monitor = AsyncMock()
        mock_monitor.temp_sensor = None  # Ensure no sensor is connected initially
        pilot.app.monitor = mock_monitor
        
        # Setup mock device
        mock_device = Mock(name="Device 1")
        pilot.app.found_devices = [mock_device]
        pilot.app.device_map = {"Device 1": 0}
        
        # Mock PASCOBLEDevice
        mock_pasco = Mock()
        mock_pasco.connect = Mock()
        mock_pasco.is_connected = Mock(return_value=True)
        
        # Patch PASCOBLEDevice constructor
        with patch('tui.PASCOBLEDevice', return_value=mock_pasco):
            # Get the select widget and simulate selection
            select = pilot.app.query_one("#device_select", Select)
            
            # Create and post a Select.Changed message
            message = Select.Changed(select, "Device 1")
            await pilot.app.on_select_changed(message)
            await pilot.pause()
            
            # Verify connection attempt was made
            mock_pasco.connect.assert_called_once_with(mock_device)
            # Verify the sensor was stored in the monitor
            assert pilot.app.monitor.temp_sensor == mock_pasco

@pytest.mark.asyncio
async def test_device_connection_flow():
    """Test the complete device connection flow from scan to connect"""
    app = TemperatureAlarmApp()
    try:
        async with app.run_test() as pilot:
            # Setup mock monitor
            mock_monitor = AsyncMock()
            mock_monitor.temp_sensor = None
            pilot.app.monitor = mock_monitor
            
            # Mock device data
            mock_device = Mock(name="PASCO Test Device")
            mock_monitor.scan = AsyncMock(return_value=[mock_device])
            
            # Mock PASCOBLEDevice
            mock_pasco = Mock()
            mock_pasco.connect = Mock()
            mock_pasco.is_connected = Mock(return_value=True)
            mock_pasco.read_data = Mock(return_value=25.5)
            
            print("\nStarting device connection test")
            
            # Step 1: Click scan button
            print("Clicking scan button")
            await pilot.click("#scan_button")
            await pilot.pause()
            
            # Verify scan was called
            print("Verifying scan was called")
            mock_monitor.scan.assert_called_once()
            
            # Verify device select was populated
            print("Checking device select options")
            device_select = pilot.app.query_one("#device_select", Select)
            assert len(device_select.options) > 0
            
            # Step 2: Select device
            print("Selecting device")
            with patch('tui.PASCOBLEDevice', return_value=mock_pasco):
                # Simulate device selection
                message = Select.Changed(device_select, device_select.options[0][0])
                await pilot.app.on_select_changed(message)
                await pilot.pause()
                
                # Verify connection attempt
                print("Verifying connection")
                mock_pasco.connect.assert_called_once_with(mock_device)
                assert pilot.app.monitor.temp_sensor == mock_pasco
                
                # Verify connection success notification
                print("Checking connection success")
                assert mock_pasco.is_connected() is True
                
                # Try reading temperature
                print("Testing temperature read")
                temp = await pilot.app.monitor.temp_sensor.read_data('Temperature')
                assert temp == 25.5
                
    except Exception as e:
        print(f"Test failed with error: {e}")
        pytest.fail(f"Test failed with error: {e}")
    finally:
        print("Starting cleanup")
        try:
            if hasattr(app, 'monitor') and app.monitor:
                print("Cleaning up monitor")
                await asyncio.wait_for(app.monitor.cleanup(), timeout=1.0)
            print("Cleaning up app")
            await asyncio.wait_for(app.cleanup(), timeout=1.0)
        except asyncio.TimeoutError:
            print("Cleanup timed out")
        except Exception as e:
            print(f"Cleanup error: {e}")
    print("Test completed")

@pytest.mark.asyncio
async def test_real_device_connection():
    """Test connecting to a real PASCO device"""
    app = TemperatureAlarmApp()
    try:
        async with app.run_test() as pilot:
            print("\nStarting real device connection test")
            
            # Initialize monitor
            from temperature_alarm import TemperatureMonitor, select_sensor
            monitor = TemperatureMonitor()
            pilot.app.monitor = monitor
            
            # Use select_sensor to find and connect to a device
            print("Scanning and selecting device...")
            temp_sensor = select_sensor()
            
            if temp_sensor is None:
                pytest.skip("No PASCO devices found - skipping test")
            
            print(f"Connected to device")
            monitor.temp_sensor = temp_sensor
            
            # Try reading temperature
            temp = temp_sensor.read_data('Temperature')
            print(f"Current temperature: {temp:.1f}°C")
            assert temp is not None, "Failed to read temperature"
                
    except Exception as e:
        print(f"Test failed with error: {e}")
        pytest.fail(f"Test failed with error: {e}")
    finally:
        print("Starting cleanup")
        try:
            if hasattr(app, 'monitor') and app.monitor and app.monitor.temp_sensor:
                print("Cleaning up monitor")
                await asyncio.wait_for(app.monitor.cleanup(), timeout=1.0)
            print("Cleaning up app")
            await asyncio.wait_for(app.cleanup(), timeout=1.0)
        except asyncio.TimeoutError:
            print("Cleanup timed out")
        except Exception as e:
            print(f"Cleanup error: {e}")
    print("Test completed")

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from temperature_alarm import (
    TemperatureMonitor,
    target_reached,
    select_sensor
)
from temperature_types import TemperatureBuffer
from pasco.pasco_ble_device import PASCOBLEDevice

@pytest.fixture
def temperature_monitor():
    """Fixture to create a TemperatureMonitor instance"""
    return TemperatureMonitor(sample_rate=2.0)

@pytest.mark.parametrize("direction,target_temp,current_temp,expected", [
    ('increases', 25.0, 26.0, True),
    ('increases', 25.0, 24.0, False),
    ('decreases', 25.0, 24.0, True),
    ('decreases', 25.0, 26.0, False),
    ('invalid', 25.0, 26.0, False),
])
def test_target_reached(direction, target_temp, current_temp, expected):
    """Test the target_reached function with various scenarios"""
    assert target_reached(direction, target_temp, current_temp) == expected

@pytest.mark.asyncio
async def test_temperature_monitor_initialization(temperature_monitor):
    """Test TemperatureMonitor initialization"""
    assert temperature_monitor.temp_sensor is None
    assert temperature_monitor.exit_flag.is_set() is False
    assert temperature_monitor.sample_rate == 2.0
    assert isinstance(temperature_monitor.temperature_buffer, TemperatureBuffer)

@pytest.mark.asyncio
async def test_safe_read_temperature_no_sensor(temperature_monitor):
    """Test safe_read_temperature when no sensor is connected"""
    temp = await temperature_monitor.safe_read_temperature()
    assert temp is None

@pytest.mark.asyncio
async def test_safe_read_temperature_with_mock_sensor(temperature_monitor):
    """Test safe_read_temperature with a mock sensor"""
    mock_sensor = Mock()
    mock_sensor.read_data.return_value = 25.5
    temperature_monitor.temp_sensor = mock_sensor
    
    temp = await temperature_monitor.safe_read_temperature()
    assert temp == 25.5
    mock_sensor.read_data.assert_called_once_with('Temperature')

@pytest.mark.asyncio
async def test_cleanup(temperature_monitor):
    """Test cleanup method"""
    # Setup mock sensor
    mock_sensor = Mock()
    mock_sensor.is_connected = Mock(return_value=True)
    temperature_monitor.temp_sensor = mock_sensor
    
    # Create a mock task that's not done
    mock_task = AsyncMock()
    mock_task.done.return_value = False
    mock_task.cancel = Mock()  # Use regular Mock instead of AsyncMock
    temperature_monitor.running_tasks.append(mock_task)
    
    # Mock the thread pool
    mock_thread_pool = Mock()
    mock_thread_pool._shutdown = False
    temperature_monitor.thread_pool = mock_thread_pool
    
    # Mock asyncio functions
    with patch('asyncio.shield', new_callable=AsyncMock) as mock_shield, \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            
            # Set up mock_shield to simulate task cancellation
            async def shield_effect(coro):
                if isinstance(coro, Mock):
                    # If it's a mock, just return None
                    return None
                # Otherwise, await the coroutine
                return await coro
            mock_shield.side_effect = shield_effect
            
            # Mock the task's cancel method
            mock_task.cancel = Mock()
            
            # Mock the task's done method to return True after cancel is called
            done_values = [False, True]  # First call returns False, second call returns True
            mock_task.done = Mock(side_effect=done_values)
            
            await temperature_monitor.cleanup()
            
            # Verify cleanup behavior
            assert temperature_monitor.exit_flag.is_set()
            assert not temperature_monitor.running_tasks
            assert temperature_monitor.temp_sensor is None
            mock_task.cancel.assert_called_once()
            mock_sensor.disconnect.assert_called_once()
            assert mock_thread_pool.shutdown.call_count == 2

@pytest.mark.asyncio
async def test_play_sound_async(temperature_monitor):
    """Test play_sound_async method"""
    test_message = "Test message"
    
    # Mock the synchronous play_sound method
    with patch.object(temperature_monitor, 'play_sound') as mock_play_sound:
        # Call the async method
        await temperature_monitor.play_sound_async(test_message)
        
        # Verify play_sound was called with correct message
        mock_play_sound.assert_called_once_with(test_message)

@pytest.mark.asyncio
async def test_monitor_temperature(temperature_monitor):
    """Test monitor_temperature method"""
    mock_app = AsyncMock()
    mock_sensor = Mock()
    mock_sensor.read_data.return_value = 25.5
    temperature_monitor.temp_sensor = mock_sensor
    
    try:
        # Start monitoring in background task
        monitor_task = asyncio.create_task(
            temperature_monitor.monitor_temperature(
                mock_app, 'increases', 26.0
            )
        )
        
        # Let it run for a brief moment
        await asyncio.sleep(0.1)
        
        # Stop monitoring
        temperature_monitor.exit_flag.set()
        
        # Wait for the task to complete with a timeout
        try:
            await asyncio.wait_for(monitor_task, timeout=1.0)
        except asyncio.TimeoutError:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
        # Verify app's update_temperature was called
        mock_app.update_temperature.assert_called()
        
    finally:
        # Ensure cleanup happens even if test fails
        if not temperature_monitor.exit_flag.is_set():
            temperature_monitor.exit_flag.set()
        await temperature_monitor.cleanup()

@pytest.fixture
def mock_pasco_device():
    """Fixture to create a mock PASCO device"""
    mock_device = Mock(spec=PASCOBLEDevice)
    mock_device.scan.return_value = [
        Mock(name="PASCO Device 1"),
        Mock(name="PASCO Device 2")
    ]
    return mock_device

def test_select_sensor_no_devices():
    """Test select_sensor when no devices are found"""
    with patch('temperature_alarm.PASCOBLEDevice') as mock_pasco:
        mock_pasco.return_value.scan.return_value = []
        result = select_sensor()
        assert result is None

def test_select_sensor_single_device(monkeypatch, mock_pasco_device):
    """Test select_sensor with a single device"""
    with patch('temperature_alarm.PASCOBLEDevice') as mock_pasco:
        mock_pasco.return_value = mock_pasco_device
        mock_pasco.return_value.scan.return_value = [Mock(name="PASCO Device 1")]
        
        result = select_sensor()
        assert result is not None
        mock_pasco.return_value.connect.assert_called_once()

def test_play_sound(temperature_monitor):
    """Test synchronous play_sound method"""
    test_message = "Test message"
    
    # Mock all the sound-related dependencies
    with patch('gtts.gTTS') as mock_tts, \
         patch('pydub.AudioSegment.from_mp3') as mock_audio, \
         patch('simpleaudio.WaveObject.from_wave_file') as mock_wave:
        
        # Setup mock chain
        mock_tts_instance = mock_tts.return_value
        mock_audio_instance = mock_audio.return_value
        mock_wave_instance = mock_wave.return_value
        mock_play_obj = Mock()
        mock_wave_instance.play.return_value = mock_play_obj
        
        # Call the method
        temperature_monitor.play_sound(test_message)
        
        # Verify the call chain
        mock_tts.assert_called_once_with(text=test_message, lang='en')
        mock_tts_instance.write_to_fp.assert_called_once()
        mock_audio.assert_called_once()
        mock_audio_instance.export.assert_called_once()
        mock_wave.assert_called_once()
        mock_wave_instance.play.assert_called_once()
        mock_play_obj.wait_done.assert_called_once()

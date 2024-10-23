import pytest
import os
import time
from sound_manager import AlarmSound
from unittest.mock import Mock, patch

@pytest.fixture
def test_mp3_file(tmp_path):
    """Create a temporary MP3 file for testing."""
    test_file = tmp_path / "test_alarm.mp3"
    # Create an empty MP3 file
    test_file.write_bytes(b"")
    return str(test_file)

@pytest.fixture
def mock_audio_segment():
    """Mock AudioSegment to avoid actual audio loading."""
    with patch('sound_manager.AudioSegment') as mock:
        yield mock

@pytest.fixture
def mock_play():
    """Mock play function to avoid actual audio playback."""
    with patch('sound_manager.play') as mock:
        yield mock

def test_init_file_not_found():
    """Test initialization with non-existent file."""
    with pytest.raises(FileNotFoundError):
        AlarmSound("nonexistent.mp3")

def test_init_success(test_mp3_file, mock_audio_segment):
    """Test successful initialization."""
    alarm = AlarmSound(test_mp3_file)
    assert alarm.sound_file == test_mp3_file
    assert not alarm._stop_flag.is_set()
    assert alarm._thread is None
    mock_audio_segment.from_mp3.assert_called_once_with(test_mp3_file)

def test_start_stop(test_mp3_file, mock_audio_segment, mock_play):
    """Test starting and stopping the alarm."""
    alarm = AlarmSound(test_mp3_file)
    
    # Test start
    alarm.start()
    assert alarm._thread is not None
    assert alarm._thread.is_alive()
    assert not alarm._stop_flag.is_set()
    
    # Give the thread a moment to start
    time.sleep(0.1)
    
    # Test stop
    alarm.stop()
    assert alarm._stop_flag.is_set()
    
    # Wait for thread to finish
    alarm._thread.join(timeout=1.0)
    assert not alarm._thread.is_alive()

def test_multiple_start_stop(test_mp3_file, mock_audio_segment, mock_play):
    """Test starting and stopping the alarm multiple times."""
    alarm = AlarmSound(test_mp3_file)
    
    # First cycle
    alarm.start()
    time.sleep(0.1)
    alarm.stop()
    time.sleep(0.1)
    
    # Second cycle
    alarm.start()
    time.sleep(0.1)
    alarm.stop()
    time.sleep(0.1)
    
    assert not alarm._thread.is_alive()

@pytest.mark.parametrize("exception_type", [
    Exception,
    RuntimeError,
    ValueError
])
def test_play_loop_error_handling(test_mp3_file, mock_audio_segment, mock_play, exception_type):
    """Test error handling in play loop with different exceptions."""
    mock_play.side_effect = exception_type("Test error")
    
    alarm = AlarmSound(test_mp3_file)
    alarm.start()
    time.sleep(0.1)  # Give time for the error to occur
    alarm.stop()
    
    # Verify the thread stops after error
    alarm._thread.join(timeout=1.0)
    assert not alarm._thread.is_alive()

def test_cleanup_on_init_error(test_mp3_file, mock_audio_segment):
    """Test proper cleanup when initialization fails."""
    mock_audio_segment.from_mp3.side_effect = Exception("Load failed")
    
    with pytest.raises(Exception):
        AlarmSound(test_mp3_file)

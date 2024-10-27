import pytest
import asyncio
import os
import time
from unittest.mock import patch, Mock, MagicMock
from sound_manager import AsyncSoundPlayer
from io import BytesIO

# Define test file path
SOUND_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'sounds', 'alarm.mp3')

class MockChannel:
    def __init__(self, busy_count=1):
        self.busy_count = busy_count
        self.current_count = 0
        
    def get_busy(self):
        self.current_count += 1
        return self.current_count < self.busy_count

class MockSound:
    def __init__(self):
        self.play = MagicMock(return_value=MockChannel())
        self.stop = MagicMock()

@pytest.fixture
def mock_pygame():
    """Mock pygame and its mixer module."""
    with patch('sound_manager.pygame') as mock_pg:
        # Create mock mixer
        mock_mixer = MagicMock()
        mock_mixer.init = MagicMock()
        mock_mixer.quit = MagicMock()
        mock_sound = MockSound()
        mock_mixer.Sound = MagicMock(return_value=mock_sound)
        mock_mixer.set_num_channels = MagicMock()
        
        # Attach mixer to pygame mock
        mock_pg.mixer = mock_mixer
        mock_pg.time.wait = MagicMock()
        
        yield mock_pg

@pytest.fixture
async def player():
    """Create and cleanup a player instance."""
    _player = AsyncSoundPlayer(SOUND_FILE_PATH)
    yield _player
    await _player.cleanup()

@pytest.mark.asyncio
async def test_initialization(mock_pygame):
    """Test player initialization."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    assert not player._initialized
    await player._initialize_pygame()
    
    assert player._initialized
    mock_pygame.mixer.init.assert_called_once()
    mock_pygame.mixer.Sound.assert_called_once_with(SOUND_FILE_PATH)
    await player.cleanup()

@pytest.mark.asyncio
async def test_start_stop(mock_pygame):
    """Test starting and stopping playback."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    
    try:
        # Start playback
        await player.start()
        assert player._task is not None
        assert not player._stop_event.is_set()
        
        # Allow task to start
        await asyncio.sleep(0.1)
        
        # Stop playback
        await player.stop()
        assert player._task is None
        assert player._stop_event.is_set()
        
        # Verify sound methods were called
        sound = mock_pygame.mixer.Sound.return_value
        sound.play.assert_called()
        sound.stop.assert_called()
    finally:
        await player.cleanup()

@pytest.mark.asyncio
async def test_continuous_playback(mock_pygame):
    """Test continuous playback mode."""
    # Create player in continuous mode
    player = AsyncSoundPlayer(SOUND_FILE_PATH, continuous=True)
    
    # Mock channel to report busy for multiple checks
    mock_channel = MockChannel(busy_count=3)
    mock_pygame.mixer.Sound.return_value.play.return_value = mock_channel
    
    try:
        # Start playback
        await player.start()
        await asyncio.sleep(0.3)  # Allow multiple play cycles
        
        # Verify multiple play calls
        assert mock_pygame.mixer.Sound.return_value.play.call_count > 1
        
    finally:
        await player.cleanup()

@pytest.mark.asyncio
async def test_bytesio_source(mock_pygame):
    """Test playing from BytesIO source."""
    sound_data = BytesIO(b"mock sound data")
    player = AsyncSoundPlayer(sound_data)
    
    try:
        await player._initialize_pygame()
        mock_pygame.mixer.Sound.assert_called_once_with(sound_data)
    finally:
        await player.cleanup()

@pytest.mark.asyncio
async def test_cleanup(mock_pygame):
    """Test resource cleanup."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    await player._initialize_pygame()
    await player.start()
    await player.cleanup()
    
    assert not player._initialized
    assert player._task is None
    mock_pygame.mixer.quit.assert_called_once()

@pytest.mark.asyncio
async def test_error_handling_init(mock_pygame):
    """Test error handling during initialization."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    mock_pygame.mixer.init.side_effect = Exception("Init failed")
    
    with pytest.raises(Exception, match="Init failed"):
        await player._initialize_pygame()
    
    assert not player._initialized
    await player.cleanup()

@pytest.mark.asyncio
async def test_error_handling_play(mock_pygame):
    """Test error handling during playback."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    mock_pygame.mixer.Sound.return_value.play.side_effect = Exception("Play failed")
    
    try:
        await player.start()
        await asyncio.sleep(0.1)  # Allow error to occur
        
        # Task should have ended due to error
        assert player._task is None or player._task.done()
    finally:
        await player.cleanup()

@pytest.mark.asyncio
async def test_multiple_starts(mock_pygame):
    """Test starting playback multiple times."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    try:
        await player.start()
        first_task = player._task
        
        # Try to start again
        await player.start()
        assert player._task == first_task  # Should be the same task
    finally:
        await player.stop()
        await player.cleanup()

@pytest.mark.asyncio
async def test_stop_before_start(mock_pygame):
    """Test stopping before starting."""
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    try:
        await player.stop()  # Should not raise any errors
        assert player._task is None
    finally:
        await player.cleanup()
        
@pytest.mark.asyncio
async def test_stop_timeout(mock_pygame):
    """Test handling of stop timeout.
    
    Verifies that the stop() method completes within a reasonable timeout period
    even when the sound channel appears to be perpetually busy.
    """
    print("Starting test_stop_timeout")
    player = AsyncSoundPlayer(SOUND_FILE_PATH)
    print(f"Created AsyncSoundPlayer with sound file: {SOUND_FILE_PATH}")
    
    # Mock channel to never report as not busy
    mock_channel = MockChannel(busy_count=float('inf'))
    mock_pygame.mixer.Sound.return_value.play.return_value = mock_channel
    print("Mocked pygame channel to be perpetually busy")
    
    try:
        # Start playback
        print("Starting playback")
        await player.start()
        print("Waiting for 2 seconds to allow playback to begin")
        await asyncio.sleep(2)  # Allow playback to begin
        
        # Time the stop operation
        print("Initiating stop operation")
        start_time = time.time()
        await player.stop()
        stop_duration = time.time() - start_time
        print(f"Stop operation completed in {stop_duration:.2f} seconds")
        
        # Verify stop completed in a reasonable time
        print("Verifying stop operation results")
        assert stop_duration < 4.0, f"Stop operation took {stop_duration:.2f} seconds, which is longer than expected"
        print("Stop duration within acceptable range")
        assert player._task is None, "Player task was not cleaned up"
        print("Player task cleaned up successfully")
        assert player._stop_event.is_set(), "Stop event was not set"
        print("Stop event set successfully")
        
        # Verify sound methods were called
        sound = mock_pygame.mixer.Sound.return_value
        sound.stop.assert_called_once()  # Should call stop() on the sound
        print("Verified that stop() was called on the sound object")
        
    finally:
        print("Cleaning up player")
        await player.cleanup()
    print("test_stop_timeout completed")

@pytest.mark.asyncio
@pytest.mark.integration  # Mark as integration test since it plays actual sound
async def test_real_sound_playback():
    """
    Integration test that plays actual sound.
    WARNING: This test will play audio through your speakers/headphones!
    """
    # Create player without mocks, in continuous mode
    player = AsyncSoundPlayer(SOUND_FILE_PATH, continuous=True)
    
    try:
        # Start playback
        await player.start()
        print("\nPlaying sound for 3 seconds...")
        
        # Let it play for 3 seconds
        await asyncio.sleep(3)
        
        # Stop playback
        await player.stop()
        
        # Verify the task is cleaned up
        assert player._task is None
        
    finally:
        await player.cleanup()

# Add configuration for pytest-asyncio
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )

# Helper to run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])

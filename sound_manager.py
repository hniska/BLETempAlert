from pydub import AudioSegment
from pydub.playback import play
import threading
from typing import Optional
import logging
from logging_config import setup_logging
import os

logger = setup_logging(__name__)

class AlarmSound:
    """Manages alarm sound playback from MP3."""
    
    def __init__(self, sound_file: str = "sounds/alarm.mp3"):
        """Initialize the alarm sound player.
        
        Args:
            sound_file: Path to the MP3 file to play. Defaults to 'sounds/alarm.mp3'
        """
        self.sound_file = sound_file
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # Verify sound file exists
        if not os.path.exists(sound_file):
            logger.error(f"Sound file not found: {sound_file}")
            raise FileNotFoundError(f"Sound file not found: {sound_file}")
        
        # Load the audio file once at initialization
        try:
            self.sound = AudioSegment.from_mp3(sound_file)
        except Exception as e:
            logger.error(f"Failed to load sound file: {e}")
            raise
        
    def _play_loop(self):
        """Loop that plays the alarm sound repeatedly."""
        while not self._stop_flag.is_set():
            try:
                play(self.sound)
            except Exception as e:
                logger.error(f"Error playing sound: {e}")
                break

    def start(self) -> None:
        """Start playing the alarm sound."""
        try:
            self._stop_flag.clear()
            self._thread = threading.Thread(target=self._play_loop, daemon=True)
            self._thread.start()
            logger.debug("Alarm sound started")
        except Exception as e:
            logger.error(f"Failed to start alarm sound: {e}")

    def stop(self) -> None:
        """Stop playing the alarm sound immediately."""
        try:
            self._stop_flag.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            logger.debug("Alarm sound stopped")
        except Exception as e:
            logger.error(f"Error stopping alarm sound: {e}")

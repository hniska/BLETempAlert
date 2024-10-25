from pydub import AudioSegment
from pydub.playback import play
import threading
from typing import Union, Optional, BinaryIO
import logging
from logging_config import setup_logging
import os
import asyncio
from io import BytesIO
import pygame
from concurrent.futures import ThreadPoolExecutor
import time


logger = setup_logging(__name__)

class AsyncSoundPlayer:
    """Asynchronous sound player using pygame mixer."""
    
    def __init__(self, sound_source: Union[str, BytesIO, None], continuous: bool = False):
        """
        Initialize the async sound player.
        
        Args:
            sound_source: Path to sound file, BytesIO object, or None if source will be set later
            continuous: Whether to play the sound continuously
        """
        self.sound_source = sound_source
        self.continuous = continuous
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._initialized = False
        self._sound = None
        self._mixer_initialized = False
        
        logger.debug(f"AsyncSoundPlayer initialized with sound_source type: {type(sound_source)}, continuous: {continuous}")

    def _convert_to_wav(self, audio_data: BytesIO, input_format: str = "mp3") -> BytesIO:
        """
        Convert audio data to WAV format.
        
        Args:
            audio_data: BytesIO containing audio data
            input_format: Format of input audio (default: "mp3")
            
        Returns:
            BytesIO: WAV format audio data
        """
        try:
            # Load audio data
            audio = AudioSegment.from_file(audio_data, format=input_format)
            
            # Convert to WAV
            wav_data = BytesIO()
            audio.export(wav_data, format='wav')
            wav_data.seek(0)
            
            return wav_data
        except Exception as e:
            logger.error(f"Error converting audio to WAV: {e}")
            raise

    async def _initialize_pygame(self) -> None:
        """Initialize pygame mixer asynchronously."""
        if not self._mixer_initialized:
            try:
                logger.debug("Initializing pygame mixer")
                await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda: pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                )
                self._mixer_initialized = True
                logger.debug("Pygame mixer initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize pygame mixer: {e}")
                raise

        try:
            # Load the sound - this needs to happen each time for BytesIO
            if isinstance(self.sound_source, (str, BytesIO)):
                logger.debug(f"Loading sound from {'file' if isinstance(self.sound_source, str) else 'BytesIO'}")
                
                # Convert to WAV if it's a BytesIO source (assuming MP3)
                if isinstance(self.sound_source, BytesIO):
                    wav_data = await asyncio.get_event_loop().run_in_executor(
                        self._executor,
                        self._convert_to_wav,
                        self.sound_source
                    )
                    sound_source = wav_data
                else:
                    sound_source = self.sound_source
                
                self._sound = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    pygame.mixer.Sound,
                    sound_source
                )
                self._initialized = True
                logger.debug("Sound loaded successfully")
            else:
                logger.error(f"Invalid sound source type: {type(self.sound_source)}")
                raise ValueError("Invalid sound source type")

        except Exception as e:
            logger.error(f"Failed to load sound: {e}")
            raise

    def _play_sound(self) -> None:
        """Play the sound synchronously (called in executor)."""
        try:
            if self._sound is None:
                logger.error("No sound loaded")
                return
                
            logger.debug("Playing sound")
            channel = self._sound.play()
            # Wait for the sound to finish playing
            while channel.get_busy():
                pygame.time.wait(100)  # Wait in small increments
            logger.debug("Sound finished playing")
        except Exception as e:
            logger.error(f"Error playing sound: {e}")
            raise

    async def _play_loop(self) -> None:
        """Internal loop for playing sound."""
        try:
            await self._initialize_pygame()
            
            while not self._stop_event.is_set():
                try:
                    logger.debug("Starting sound playback in executor")
                    # Play sound in executor to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(
                        self._executor,
                        self._play_sound
                    )
                    
                    if not self.continuous or self._stop_event.is_set():
                        logger.debug("Breaking play loop: continuous={}, stop_event={}".format(
                            self.continuous, self._stop_event.is_set()))
                        break
                    
                    # Small delay between loops if continuous
                    logger.debug("Waiting before next loop iteration")
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error in play loop: {e}")
                    break
                    
        except asyncio.CancelledError:
            logger.debug("Sound playback cancelled")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in play loop: {e}")
            raise
        finally:
            # Ensure sound is stopped
            if self._sound:
                logger.debug("Stopping sound in finally block")
                await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    self._sound.stop
                )
            # Clear the task reference
            self._task = None
            logger.debug("Task reference cleared")

    async def start(self) -> None:
        """Start playing the sound asynchronously."""
        try:
            if self._task is not None and not self._task.done():
                logger.debug("Sound playback task already exists and is still running")
                return
                
            self._stop_event.clear()
            logger.debug("Creating sound playback task")
            self._task = asyncio.create_task(self._play_loop())
            logger.debug("Sound playback task created")
            
        except Exception as e:
            logger.error(f"Failed to start sound playback: {e}")
            raise

    async def stop(self) -> None:
        """Stop the sound."""
        try:
            logger.debug("Stopping sound playback")
            if self._task is None:
                logger.debug("No sound playback task to stop")
                return
                
            logger.debug("Setting stop event")
            self._stop_event.set()
            
            # Only wait for task if executor is still alive
            if not self._executor._shutdown:
                try:
                    logger.debug("Waiting for task to finish")
                    await asyncio.wait_for(self._task, timeout=1.0)
                    logger.debug("Task finished")
                except asyncio.TimeoutError:
                    logger.warning("Sound stop timeout - forcing stop")
                    if self._sound:
                        # Only try to stop sound if executor is still alive
                        if not self._executor._shutdown:
                            logger.debug("Stopping sound forcefully")
                            await asyncio.get_event_loop().run_in_executor(
                                self._executor,
                                self._sound.stop
                            )
                            logger.debug("Sound stopped forcefully")
                    # Cancel the task if it's still running
                    if not self._task.done():
                        logger.debug("Cancelling task")
                        self._task.cancel()
                        try:
                            await self._task
                        except asyncio.CancelledError:
                            logger.debug("Task cancelled successfully")
                        except Exception as e:
                            logger.error(f"Error cancelling task: {e}")
            
            self._task = None
            logger.debug("Sound playback stopped completely")
            
        except Exception as e:
            logger.error(f"Error stopping sound playback: {e}")
            # Don't re-raise the exception during cleanup

    async def cleanup(self) -> None:
        """Clean up resources."""
        try:
            logger.debug("Starting cleanup")
            
            # First set the stop event
            self._stop_event.set()
            
            # Cancel any running task
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception) as e:
                    logger.debug(f"Task cancellation result: {e}")
            
            # Quit pygame mixer if initialized
            if self._initialized and not self._executor._shutdown:
                try:
                    logger.debug("Quitting pygame mixer")
                    await asyncio.get_event_loop().run_in_executor(
                        self._executor,
                        pygame.mixer.quit
                    )
                except Exception as e:
                    logger.debug(f"Error quitting pygame mixer: {e}")
                finally:
                    self._initialized = False
            
            # Finally shutdown the executor
            if not self._executor._shutdown:
                logger.debug("Shutting down executor")
                self._executor.shutdown(wait=False)
                logger.debug("Executor shut down")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            # Don't re-raise the exception during cleanup

from dataclasses import dataclass
from typing import List, Optional, Literal, Tuple, Protocol
from datetime import datetime
import asyncio

@dataclass
class TemperatureData:
    temperature: float
    timestamp: datetime

class TemperatureBuffer:
    def __init__(self, min_window: float = 100.0, max_window: float = 7200.0):
        """Initialize the temperature buffer.
        
        Args:
            min_window: Minimum time window to display (in seconds)
            max_window: Maximum time window to display (in seconds)
        """
        self.temperatures: List[float] = []
        self.timestamps: List[float] = []
        self.min_window = min_window
        self.max_window = max_window
        self._lock = asyncio.Lock()

    async def add(self, temperature: float, timestamp: float) -> None:
        """Add a temperature reading with its timestamp."""
        async with self._lock:
            # Add new data
            self.temperatures.append(temperature)
            self.timestamps.append(timestamp)
            
            # Only trim if we have more than max_window of data
            if self.timestamps:
                current_time = timestamp
                data_span = current_time - self.timestamps[0]
                
                if data_span > self.max_window:
                    cutoff_time = current_time - self.max_window
                    # Find index of first reading within time window
                    valid_index = 0
                    for i, t in enumerate(self.timestamps):
                        if t >= cutoff_time:
                            valid_index = i
                            break
                    
                    # Trim data to max window
                    if valid_index > 0:
                        self.temperatures = self.temperatures[valid_index:]
                        self.timestamps = self.timestamps[valid_index:]

    async def get_data(self) -> Tuple[List[float], List[float]]:
        """Get the current temperature and timestamp data."""
        async with self._lock:
            if not self.timestamps:
                return [], []
                
            current_time = self.timestamps[-1]
            data_span = current_time - self.timestamps[0]
            
            # If we have less than min_window of data, return everything
            if data_span <= self.min_window:
                return self.temperatures.copy(), self.timestamps.copy()
            
            # Otherwise, return data within the max_window
            cutoff_time = current_time - self.max_window
            valid_data = [(t, temp) for t, temp in zip(self.timestamps, self.temperatures) 
                         if t >= cutoff_time]
            
            if valid_data:
                timestamps, temperatures = zip(*valid_data)
                return list(temperatures), list(timestamps)
            return [], []

    async def clear(self) -> None:
        """Clear the buffer."""
        async with self._lock:
            self.temperatures.clear()
            self.timestamps.clear()

class TemperatureUI(Protocol):
    """Protocol defining the interface for temperature UI."""
    async def update_temperature(self, temperature: float, timestamp: datetime) -> None: ...
    async def stop_monitoring(self) -> None: ...

class BaseTemperatureMonitor:
    """Base class for temperature monitoring functionality."""
    def __init__(self, sample_rate: float = 2.0):
        self.temp_sensor = None
        self.exit_flag = asyncio.Event()
        self.db_connection = None
        self.logging_enabled = False
        self.run_id = None
        self.log_queue = asyncio.Queue()
        self.temperature_buffer = TemperatureBuffer()
        self.graph_lock = asyncio.Lock()
        self.sample_rate = sample_rate
        self.running_tasks = []
        self.thread_pool = None
        self._thread_pool_lock = asyncio.Lock()
        self._shutting_down = False

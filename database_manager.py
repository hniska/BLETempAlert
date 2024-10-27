"""Database management module for temperature monitoring."""

import logging
from pathlib import Path
import aiosqlite
from aiosqlite import Connection as AioConnection
from typing import Optional, List, Tuple
from datetime import datetime
from config_manager import DataRecordingConfig

# Create module-level logger
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database operations for temperature monitoring."""
    
    def __init__(self, config: DataRecordingConfig):
        """Initialize database manager.
        
        Args:
            config: Data recording configuration object
        """
        self.config = config
        self.db_path = Path(config.path)
        self.connection: Optional[AioConnection] = None
        self.enabled = config.enabled
        self.logger = logger  # Assign the module logger to instance
        
    async def initialize(self) -> None:
        """Initialize database connection and schema."""
        try:
            self.logger.debug(f"Creating data directory: {self.db_path.parent}")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.logger.debug(f"Connecting to database at: {self.db_path}")
            self.connection = await aiosqlite.connect(self.db_path)
            self.logger.info(f"Successfully connected to database: {self.db_path}")
            
            await self._create_schema()
            
            # Verify database is writable
            await self.connection.execute("PRAGMA journal_mode=WAL")
            await self.connection.commit()
            self.logger.debug("Database initialized and writable")
            
        except Exception as e:
            self.logger.exception(f"Failed to initialize database: {e}")
            raise

    async def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        schema = """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            target_temperature REAL,
            direction TEXT
        );

        CREATE TABLE IF NOT EXISTS temperature_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            FOREIGN KEY (run_id) REFERENCES runs (id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_temperature_logs_run_id 
        ON temperature_logs(run_id);
        """
        
        try:
            await self.connection.executescript(schema)
            await self.connection.commit()
            logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database schema: {e}")
            raise

    async def create_run(self, target_temp: float, direction: str) -> int:
        """Create a new monitoring run."""
        try:
            run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.debug(f"Creating new run - Name: {run_name}, Target: {target_temp}°C, Direction: {direction}")
            
            async with self.connection.execute(
                """INSERT INTO runs (name, target_temperature, direction) 
                   VALUES (?, ?, ?)""",
                (run_name, target_temp, direction)
            ) as cursor:
                await self.connection.commit()
                run_id = cursor.lastrowid
                logger.info(f"Created new run with ID: {run_id}")
                return run_id
        except Exception as e:
            logger.exception(f"Failed to create run: {e}")
            raise

    async def record_temperature(self, run_id: int, temperature: float) -> None:
        """Record a temperature reading."""
        try:
            logger.debug(f"Recording temperature for run {run_id}: {temperature}°C")
            async with self.connection.execute(
                "INSERT INTO temperature_logs (run_id, temperature) VALUES (?, ?)",
                (run_id, temperature)
            ):
                await self.connection.commit()
                logger.debug(f"Successfully recorded temperature {temperature}°C for run {run_id}")
        except Exception as e:
            logger.exception(f"Failed to record temperature {temperature}°C for run {run_id}: {e}")
            raise

    async def get_run_data(self, run_id: int) -> List[Tuple[float, datetime]]:
        """Get all temperature readings for a specific run.
        
        Args:
            run_id: ID of the run to query
            
        Returns:
            List of (temperature, timestamp) tuples
        """
        async with self.connection.execute(
            """SELECT temperature, timestamp 
               FROM temperature_logs 
               WHERE run_id = ? 
               ORDER BY timestamp""",
            (run_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def get_run_summary(self, run_id: int) -> dict:
        """Get summary statistics for a specific run.
        
        Args:
            run_id: ID of the run to summarize
            
        Returns:
            Dictionary containing run summary statistics
        """
        async with self.connection.execute(
            """SELECT r.*, 
                      MIN(t.temperature) as min_temp,
                      MAX(t.temperature) as max_temp,
                      AVG(t.temperature) as avg_temp,
                      COUNT(t.id) as reading_count
               FROM runs r 
               LEFT JOIN temperature_logs t ON t.run_id = r.id
               WHERE r.id = ?
               GROUP BY r.id""",
            (run_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def close(self) -> None:
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None

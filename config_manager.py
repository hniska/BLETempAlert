from dataclasses import dataclass
from typing import List, Optional
import sys
from pathlib import Path

# Handle TOML import based on Python version
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

@dataclass
class VoiceConfig:
    """Configuration for voice notifications"""
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> 'VoiceConfig':
        """Create VoiceConfig from dictionary
        
        Args:
            data: Dictionary containing voice configuration
            
        Returns:
            VoiceConfig: Initialized configuration object
        """
        return cls(
            enabled=data.get('enabled', True)
        )

@dataclass
class NtfyConfig:
    """Configuration for ntfy notifications"""
    enabled: bool
    server: str
    topic: str
    username: Optional[str] = None
    password: Optional[str] = None
    priority: str = "default"
    tags: List[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'NtfyConfig':
        """Create NtfyConfig from dictionary"""
        return cls(
            enabled=data.get('enabled', False),
            server=data.get('server', 'https://ntfy.sh'),
            topic=data.get('topic', ''),
            username=data.get('username'),
            password=data.get('password'),
            priority=data.get('priority', 'default'),
            tags=data.get('tags', [])
        )

@dataclass
class DataRecordingConfig:  # Changed from DatabaseConfig
    """Configuration for temperature data recording"""
    enabled: bool
    path: str = "data/temperature_logs.db"

    @classmethod
    def from_dict(cls, data: dict) -> 'DataRecordingConfig':
        """Create DataRecordingConfig from dictionary"""
        return cls(
            enabled=data.get('enabled', True),
            path=data.get('path', 'data/temperature_logs.db')
        )

class ConfigManager:
    """Manages application configuration using TOML format"""
    
    def __init__(self, config_path: str = "config/config.toml"):
        """Initialize configuration manager
        
        Args:
            config_path: Path to TOML configuration file
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist
        """
        self.config_path = Path(config_path)
        self.ntfy_config: Optional[NtfyConfig] = None
        self.voice_config: Optional[VoiceConfig] = None
        self.data_recording_config: Optional[DataRecordingConfig] = None  # Changed from database_config
        self._raw_config: dict = {}  # Store the raw config
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from TOML file
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            tomllib.TOMLDecodeError: If TOML file is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
        with open(self.config_path, "rb") as f:
            self._raw_config = tomllib.load(f)
            
        self.ntfy_config = NtfyConfig.from_dict(self._raw_config.get('ntfy', {}))
        self.voice_config = VoiceConfig.from_dict(self._raw_config.get('voice', {}))
        self.data_recording_config = DataRecordingConfig.from_dict(
            self._raw_config.get('data_recording', {})  # Changed from database
        )

    def update_ntfy_config(self, **kwargs) -> None:
        """Update ntfy configuration with provided values
        
        Args:
            **kwargs: Key-value pairs to update in ntfy config
            
        Example:
            update_ntfy_config(enabled=True, topic="new_topic")
        """
        # Update the NtfyConfig object
        for key, value in kwargs.items():
            if hasattr(self.ntfy_config, key):
                setattr(self.ntfy_config, key, value)
        
        # Update the raw config
        if 'ntfy' not in self._raw_config:
            self._raw_config['ntfy'] = {}
        self._raw_config['ntfy'].update(kwargs)
        
        # Save to file
        import tomli_w
        with open(self.config_path, "wb") as f:
            tomli_w.dump(self._raw_config, f)

    def update_voice_config(self, enabled: bool) -> None:
        """Update voice configuration
        
        Args:
            enabled: Whether voice notifications should be enabled
        """
        self.voice_config.enabled = enabled
        
        # Update the raw config
        if 'voice' not in self._raw_config:
            self._raw_config['voice'] = {}
        self._raw_config['voice']['enabled'] = enabled
        
        # Save to file
        import tomli_w
        with open(self.config_path, "wb") as f:
            tomli_w.dump(self._raw_config, f)

    def update_data_recording_config(self, enabled: bool) -> None:  # Changed from update_database_config
        """Update temperature data recording configuration
        
        Args:
            enabled: Whether temperature recording should be enabled
        """
        self.data_recording_config.enabled = enabled
        
        if 'data_recording' not in self._raw_config:  # Changed from database
            self._raw_config['data_recording'] = {}
        self._raw_config['data_recording']['enabled'] = enabled
        
        import tomli_w
        with open(self.config_path, "wb") as f:
            tomli_w.dump(self._raw_config, f)

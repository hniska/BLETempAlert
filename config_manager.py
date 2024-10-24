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
        """Create NtfyConfig from dictionary
        
        Args:
            data: Dictionary containing ntfy configuration
            
        Returns:
            NtfyConfig: Initialized configuration object
        """
        return cls(
            enabled=data.get('enabled', False),
            server=data.get('server', 'https://ntfy.sh'),
            topic=data.get('topic', ''),
            username=data.get('username'),
            password=data.get('password'),
            priority=data.get('priority', 'default'),
            tags=data.get('tags', [])
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
            config = tomllib.load(f)
            
        self.ntfy_config = NtfyConfig.from_dict(config.get('ntfy', {}))

    def update_ntfy_config(self, enabled: bool) -> None:
        """Update ntfy configuration
    
        Args:
            enabled: Whether notifications should be enabled
        """
        self.ntfy_config.enabled = enabled
        
        # Optionally persist the change to config file
        config = self.load_config()
        config['ntfy']['enabled'] = enabled
        self.save_config(config)

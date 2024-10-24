import pytest
from pathlib import Path
from config_manager import ConfigManager, NtfyConfig

def test_config_loading(tmp_path: Path):
    """Test loading configuration from TOML file"""
    # Create a test config file
    config_content = """
    [ntfy]
    enabled = true
    server = "https://test.ntfy.sh"
    topic = "test-topic"
    tags = ["test", "thermometer"]
    """
    
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    
    # Load and verify config
    config_manager = ConfigManager(str(config_file))
    assert isinstance(config_manager.ntfy_config, NtfyConfig)
    assert config_manager.ntfy_config.enabled is True
    assert config_manager.ntfy_config.server == "https://test.ntfy.sh"
    assert config_manager.ntfy_config.topic == "test-topic"
    assert config_manager.ntfy_config.tags == ["test", "thermometer"]

def test_missing_config():
    """Test handling of missing configuration file"""
    with pytest.raises(FileNotFoundError):
        ConfigManager("nonexistent.toml")
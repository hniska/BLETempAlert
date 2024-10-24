import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, patch
from datetime import datetime
from typing import AsyncGenerator

from config_manager import NtfyConfig
from notification_manager import NotificationManager

@pytest.fixture
def ntfy_config() -> NtfyConfig:
    """Create a test configuration"""
    return NtfyConfig(
        enabled=True,
        server="https://ntfy.sh",
        topic="test-topic",
        username="test-user",
        password="test-pass",
        priority="high",
        tags=["test", "thermometer"]
    )

@pytest_asyncio.fixture
async def notification_manager(ntfy_config: NtfyConfig) -> AsyncGenerator[NotificationManager, None]:
    """Create a notification manager with test configuration"""
    manager = NotificationManager(ntfy_config)
    yield manager
    await manager.cleanup()

@pytest.mark.asyncio
async def test_send_notification_success(notification_manager: NotificationManager):
    """Test successful notification sending"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            raise_for_status=AsyncMock()
        )

        result = await notification_manager.send_notification(
            message="Test message",
            title="Test Title"
        )

        assert result is True
        mock_post.assert_called_once()
        
        # Verify the call parameters
        call_args = mock_post.call_args
        assert "Test message" in call_args.kwargs['content']
        assert call_args.kwargs['headers']['Title'] == "Test Title"
        assert call_args.kwargs['headers']['Priority'] == "high"
        assert "test,thermometer" in call_args.kwargs['headers']['Tags']

@pytest.mark.asyncio
async def test_send_notification_network_error(notification_manager: NotificationManager):
    """Test notification sending with network error"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.side_effect = httpx.NetworkError("Test network error")

        result = await notification_manager.send_notification(
            message="Test message",
            title="Test Title"
        )

        assert result is False

@pytest.mark.asyncio
async def test_send_notification_timeout(notification_manager: NotificationManager):
    """Test notification sending with timeout"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Test timeout")

        result = await notification_manager.send_notification(
            message="Test message",
            title="Test Title"
        )

        assert result is False

@pytest.mark.asyncio
async def test_notification_authentication(notification_manager: NotificationManager):
    """Test notification sending with authentication"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            raise_for_status=AsyncMock()
        )

        result = await notification_manager.send_notification(
            message="Test message",
            title="Test Title"
        )

        assert result is True
        # Verify auth was passed
        assert 'auth' in mock_post.call_args.kwargs
        assert isinstance(mock_post.call_args.kwargs['auth'], httpx.BasicAuth)

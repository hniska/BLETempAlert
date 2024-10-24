from typing import Optional, List
import httpx
import asyncio
import logging
from config_manager import NtfyConfig
from logging_config import setup_logging

logger = setup_logging(__name__)

class NotificationManager:
    """Manages sending notifications via ntfy"""
    
    def __init__(self, config: NtfyConfig):
        """Initialize notification manager
        
        Args:
            config: NtfyConfig instance with notification settings
        """
        self.config = config
        self._client = httpx.AsyncClient()
        
    async def send_notification(
        self,
        message: str,
        title: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Send notification via ntfy
        
        Args:
            message: Notification message
            title: Optional notification title
            priority: Optional priority override
            tags: Optional tags override
            
        Returns:
            bool: True if notification was sent successfully
        """
        if not self.config.enabled:
            logger.debug("Notifications are disabled")
            return False
            
        try:
            url = f"{self.config.server}/{self.config.topic}"
            headers = {
                "Title": title if title else "Temperature Alert",
                "Priority": priority if priority else self.config.priority,
                "Tags": ",".join(tags if tags else self.config.tags)
            }
            
            # Add authentication if configured
            if self.config.username and self.config.password:
                auth = httpx.BasicAuth(self.config.username, self.config.password)
            else:
                auth = None
            
            async with self._client as client:
                response = await client.post(
                    url,
                    content=message,
                    headers=headers,
                    auth=auth,
                    timeout=10.0
                )
                response.raise_for_status()
                
            logger.debug(f"Notification sent successfully: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
            
    async def cleanup(self) -> None:
        """Cleanup resources"""
        if self._client:
            await self._client.aclose()

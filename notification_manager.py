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
            tags: Optional tags to add to configured tags
            
        Returns:
            bool: True if notification was sent successfully
        """
        logger.info(f"Sending notification: {message}")
        if not self.config.enabled:
            logger.debug("Notifications are disabled")
            return False
            
        try:
            url = f"{self.config.server}/{self.config.topic}"
            
            # Merge configured tags with passed-in tags
            all_tags = list(self.config.tags or [])  # Convert to list and handle None
            if tags:
                all_tags.extend(tags)
            # Remove duplicates while preserving order
            all_tags = list(dict.fromkeys(all_tags))
            
            headers = {
                "Title": title if title else "Temperature Alert",
                "Priority": priority if priority else self.config.priority,
                "Tags": ",".join(all_tags)
            }
            
            # Add authentication if configured
            if self.config.username and self.config.password:
                auth = httpx.BasicAuth(self.config.username, self.config.password)
            else:
                auth = None
            
            async with httpx.AsyncClient() as client:
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
        # Remove cleanup method since we no longer maintain a persistent client
        pass

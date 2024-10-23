from textual.screen import ModalScreen
from textual.containers import Container
from textual.widgets import Button, Label
from textual.events import Key

class NotificationPopup(ModalScreen[bool]):
    """A popup notification with a button."""
    
    def __init__(self, message: str) -> None:
        """Initialize the popup with a message.
        
        Args:
            message: The message to display in the popup
        """
        super().__init__()
        self.message = message

    BINDINGS = [("escape", "dismiss", "Dismiss")]

    def compose(self) -> Container:
        """Create child widgets for the popup."""
        yield Container(
            Label(self.message),
            Button("OK", variant="primary", id="ok_button"),
            id="popup_container",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press event."""
        if event.button.id == "ok_button":
            self.dismiss(True)

    def on_key(self, event: Key) -> None:
        """Handle key press event."""
        if event.key == "escape":
            self.dismiss(False)

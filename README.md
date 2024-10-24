# Temperature Alarm

This application monitors the temperature from a PASCO BLE sensor and triggers an alarm when the temperature reaches a user-defined target. It features a Textual-based user interface (TUI) for easy interaction and a graphical display of the temperature data.

## Installation

1. **Install Python:** Ensure you have Python 3.11 or later installed.

2. **Install Required Packages:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Notifications:**
   Create a `config/config.toml` file with your ntfy settings:
   ```toml
   [ntfy]
   enabled = true
   server = "https://ntfy.sh"
   topic = "your-topic-name"
   # Optional authentication
   username = ""
   password = ""
   # Notification settings
   priority = "high"
   tags = ["thermometer", "alert"]
   ```

## Running the Application

1. **Connect the PASCO BLE Sensor:** Make sure your PASCO BLE sensor is powered on and within range of your computer.

2. **Run the Application:**
   ```bash
   python main.py
   ```

## Usage

1. **Scan for Devices:** Click the "Scan for Devices" button to discover available PASCO BLE sensors.

2. **Select a Device:** Choose the desired sensor from the dropdown list.

3. **Set Target Temperature:** Enter the target temperature in the input field.

4. **Start Monitoring:** Click the "Start Monitoring" button to begin monitoring the temperature.

5. **Stop Monitoring:** Click the "Stop Monitoring" button to pause monitoring.

6. **Exit:** Click the "Exit" button to shut down the application.

## Features

- **Textual User Interface (TUI):** Provides a user-friendly interface for interacting with the application.
- **Temperature Monitoring:** Continuously monitors the temperature from the selected PASCO BLE sensor.
- **Target Temperature Alarm:** Triggers an alarm when the temperature reaches the set target.
- **Graphical Display:** Shows a real-time graph of the temperature data.
- **Logging:** Logs temperature readings to a database for later analysis.
- **Audio Notifications:** Plays text-to-speech announcements of temperature changes and alarm events.
- **Push Notifications:** Sends notifications via ntfy when temperature targets are reached.

## Notifications

The application uses ntfy for push notifications. When the target temperature is reached, you'll receive:
- Mobile/desktop notifications through the ntfy service
- Customizable notification priority and tags
- Optional authentication for private ntfy topics
- Real-time temperature updates with configurable settings

## Notes

- The application requires a PASCO BLE sensor to function.
- The `requirements.txt` file lists all necessary Python packages.
- The `config/config.toml` file contains notification settings.
- The `logging_config.py` file configures logging for the application.
- The `temperature_alarm.py` file contains the core temperature monitoring logic.
- The `tui.py` file implements the Textual user interface.
- The `main.py` file runs the application.

#### Configuration Details:

- **enabled**: Set to `true` to enable notifications, `false` to disable
- **server**: 
  - Default is "https://ntfy.sh"
  - Can be set to your self-hosted ntfy server
  - Must include the protocol (http:// or https://)

- **topic**: 
  - Your unique notification topic
  - Keep this private to prevent unauthorized notifications
  - Used in the URL: `{server}/{topic}`

- **username/password**:
  - Optional authentication for private topics
  - Leave empty for public topics
  - Both must be set if authentication is needed

- **priority**: Controls notification importance
  - `"default"`: Normal priority
  - `"low"`: Low priority, may be delayed
  - `"high"`: High priority, immediate delivery
  - `"urgent"`: Maximum priority, bypass do-not-disturb

- **tags**: List of emoji tags shown in notifications
  - Displayed as icons in mobile notifications
  - Helps identify notification source and type
  - Common tags: 🌡️ (thermometer), ⚠️ (alert), 📊 (chart)

## Mobile Device Setup

### Subscribe to Notifications

1. **Install the Official App:**
   - **Android:** 
     - [Google Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
     - [F-Droid](https://f-droid.org/en/packages/io.heckel.ntfy/) (Firebase-free version)
   - **iOS:** 
     - [App Store](https://apps.apple.com/us/app/ntfy/id1625396347)

2. **Subscribe to Your Topic:**
   - Open the ntfy app or PWA
   - Add a new subscription
   - Enter your topic URL: `https://ntfy.sh/your-topic-name` or just `your-topic-name` if using ntfy.sh
   - If using authentication, enter your username and password

### Testing the Connection

1. Send a test notification:
   ```bash
   curl -d "Test notification" ntfy.sh/your-topic-name
   ```

2. You should receive the notification on your mobile device immediately.

### Security Considerations

- Keep your topic name private to prevent unauthorized notifications
- Use authentication for sensitive topics
- Consider using a self-hosted ntfy server for additional security
- Topic names are case-sensitive and should be unique

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## Contributors

- [@Håkan Niska](https://github.com/hniska)

## License

This project is licensed under the MIT License.

## Acknowledgments

- [ntfy](https://ntfy.sh) - A simple pub-sub notification service that powers our push notifications. Thank you to [@binwiederhier](https://github.com/binwiederhier) for creating this excellent open-source tool.
  - [Documentation](https://docs.ntfy.sh/)
  - [GitHub Repository](https://github.com/binwiederhier/ntfy)
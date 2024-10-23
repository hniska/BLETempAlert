# Temperature Alarm

This application monitors the temperature from a PASCO BLE sensor and triggers an alarm when the temperature reaches a user-defined target. It features a Textual-based user interface (TUI) for easy interaction and a graphical display of the temperature data.

## Installation

1. **Install Python:** Ensure you have Python 3.7 or later installed.

2. **Install Required Packages:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install PASCO BLE Library:**
   ```bash
   pip install pasco
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

## Notes

- The application requires a PASCO BLE sensor to function.
- The `requirements.txt` file lists all necessary Python packages.
- The `logging_config.py` file configures logging for the application.
- The `temperature_alarm.py` file contains the core temperature monitoring logic.
- The `tui.py` file implements the Textual user interface.
- The `main.py` file runs the application.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

This project is licensed under the MIT License.
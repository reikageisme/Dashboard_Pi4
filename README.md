# Pi Dashboard

A comprehensive dashboard for Raspberry Pi managed via Docker.

## Features
- **Backend**: Flask
- **Frontend**: Bootstrap 5 + Chart.js
- **Monitoring**: Real-time CPU, RAM, Disk, Temperature stats.
- **Docker Management**: List, Start, Stop, Restart containers.
- **Fan Control**: PWM control via GPIO (Default Pin 18).
- **Network**: Integrated Speedtest.

## Installation (Direct on Raspberry Pi 4B)

1. Ensure you have Python 3 and pip installed.
2. Install system dependencies for GPIO (optional but recommended for fan control):
   ```bash
   sudo apt update
   sudo apt install python3-lgpio
   ```
3. Install Python dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python3 app.py
   ```
   *Note: For full functionality (hardware access, system logs, reboot), you may need to run with `sudo` or ensure your user has appropriate permissions (groups `gpio`, `docker`, `adm`).*

5. Open your browser and go to `http://<your-pi-ip>:5000`.

## Installation (Docker)

1. Ensure you are in the `dashboard` directory.
2. Build and run the container:

```bash
docker compose up --build -d
```

3. Open your browser and go to `http://<your-pi-ip>:5000`.

## Configuration

- **GPIO Pin**: Edited in `app.py` (Default: 18).
- **Timezone**: Set in system timezone (e.g. `sudo timedatectl set-timezone Asia/Ho_Chi_Minh`).

## Notes
- To access hardware sensors and GPIO without root, ensure your user is in the `gpio` group: `sudo usermod -aG gpio $USER`.
- To manage Docker containers without root, ensure your user is in the `docker` group: `sudo usermod -aG docker $USER`.
- If you lack `lgpio`, the fan control will run in generic "simulation mode" (no error, but no hardware action).

# Pi Dashboard

A comprehensive dashboard for Raspberry Pi managed via Docker.

## Features
- **Backend**: Flask
- **Frontend**: Bootstrap 5 + Chart.js
- **Monitoring**: Real-time CPU, RAM, Disk, Temperature stats.
- **Docker Management**: List, Start, Stop, Restart containers.
- **Fan Control**: PWM control via GPIO (Default Pin 18).
- **Network**: Integrated Speedtest.

## Installation

1. ensure you are in the `dashboard` directory.
2. Build and run the container:

```bash
docker compose up --build -d
```

3. Open your browser and go to `http://<your-pi-ip>:5000`.

## Configuration

- **GPIO Pin**: Edited in `app.py` (Default: 18).
- **Timezone**: Set in `docker-compose.yml`.

## Notes
- The container runs in `privileged` mode to access hardware sensors and GPIO.
- If you are not on a Raspberry Pi or lack `lgpio`, the fan control will run in generic "simulation mode" (no error, but no hardware action).

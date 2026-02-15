# 🍓 Pi Dashboard - The Ultimate HomeLab Controller

![Version](https://img.shields.io/badge/version-2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![AI](https://img.shields.io/badge/AI-Gemini_2.5_Flash-orange.svg)
![Docker](https://img.shields.io/badge/docker-supported-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A sleek, modern, and comprehensive web dashboard designed specifically for Raspberry Pi and HomeLab environments. Powered by Python (Flask + Waitress) and enhanced with **Google Gemini AI** for intelligent system diagnostics.

<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/11cecc8b-905a-4121-ba93-edb3f14bb420" />


---

## ✨ Key Features

### 🤖 AI-Powered Diagnostics
- **System Doctor:** One-click diagnostics using **Gemini 2.5 Flash AI**. It reads real-time OS logs (`journalctl`), detects hidden errors, identifies security threats, and provides actionable summaries in plain text.

### 📊 Comprehensive Monitoring
- **Real-time Stats:** Live monitoring for CPU usage, RAM allocation, Core Temperature, and Disk I/O.
- **Process Manager:** View the top 10 resource-hungry processes live.
- **Storage Manager:** Visualize disk usage across all mounted partitions (`/`, `/boot`, external drives).

### 🐳 Docker & App Management
- **Container Control:** Start, Stop, Restart, and Remove Docker containers directly from the UI.
- **Image Puller:** Fetch new images from Docker Hub seamlessly.
- **App Store:** One-click deployment for popular self-hosted applications.

### 🌐 Network & Security
- **Pi-hole Integration:** View DNS query stats and temporarily disable ad-blocking without leaving the dashboard.
- **Tunnel Manager:** Manage Cloudflare Tunnels (Start/Stop) and monitor active network states.
- **Port Scanner:** View all open TCP/UDP ports on your local network.
- **Speedtest:** Integrated 1-click internet bandwidth tester.

### 🌪️ Hardware Control
- **Smart Fan Control:** PWM fan control via GPIO (Default Pin 18) with intelligent Auto, Manual, Max, and Off modes.

---

## 🛠️ Tech Stack
- **Backend:** Python 3, Flask, Waitress (Production WSGI Server), Google GenAI SDK.
- **Frontend:** HTML5, Bootstrap 5, Chart.js, Vanilla JavaScript.
- **System Integration:** Systemd, Docker Engine API, `psutil`, `lgpio`.

---

## 🚀 Installation (Method 1: Direct on OS - Recommended)

*Running directly on the OS (Bare-metal) is highly recommended. It ensures full hardware access (GPIO for Fan Control), direct access to `journalctl` for the AI Doctor, and accurate network stats.*

### 1. Install System Dependencies
```bash
sudo apt update
sudo apt install -y git python3-pip python3-psutil python3-docker python3-rpi-lgpio speedtest-cli

```

### 2. Clone the Repository & Install Python Packages

```bash
git clone [https://github.com/reikageisme/Dashboard_Pi4.git](https://github.com/reikageisme/Dashboard_Pi4.git)
cd Dashboard_Pi4
sudo pip3 install -r requirements.txt --break-system-packages

```

### 3. Configure AI (Optional but highly recommended)

Get a free API Key from [Google AI Studio](https://aistudio.google.com/).
Open `app.py` and replace the placeholder with your key:

```python
GEMINI_API_KEY = "YOUR_API_KEY_HERE"

```

### 4. Run the Dashboard

```bash
sudo python3 app.py

```

*Your dashboard is now live at `http://<your-pi-ip>:5000*`

---

## 💡 Auto-Start Service (Systemd)

To keep the dashboard running permanently and automatically after a reboot, deploy it as a system service.

**1. Create the service file:**

```bash
sudo nano /etc/systemd/system/pi_dashboard.service

```

**2. Paste the following configuration** *(Make sure to replace `/home/your_user/` with your actual path)*:

```ini
[Unit]
Description=Pi Web Dashboard & AI Doctor
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/your_user/Dashboard_Pi4
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /home/your_user/Dashboard_Pi4/app.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

# Optional: Set Web Login Credentials here
Environment=ADMIN_USER=admin
Environment=ADMIN_PASS=admin

[Install]
WantedBy=multi-user.target

```

**3. Enable and Start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pi_dashboard.service

```

---

## 🐳 Installation (Method 2: Docker)

*Suitable if you prefer containerized isolation. Note: Hardware Fan Control and full Host OS AI Log reading will be limited.*

```bash
git clone [https://github.com/reikageisme/Dashboard_Pi4.git](https://github.com/reikageisme/Dashboard_Pi4.git)
cd Dashboard_Pi4
docker compose up --build -d

```

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `ADMIN_USER` | `admin` | Username for web interface login. |
| `ADMIN_PASS` | `admin` | Password for web interface login. |
| `SECRET_KEY` | *(Random)* | Secret key for Flask session security. |
| `GEMINI_API_KEY` | `None` | Key for Google Gemini API (System Doctor). |

* **Timezone Setting:** Ensure your Raspberry Pi's timezone is correct so the charts and log times display accurately:
```bash
sudo timedatectl set-timezone Asia/Ho_Chi_Minh

```


* **Hardware Simulation:** If you run this on a non-Raspberry Pi system (lacking `python3-rpi-lgpio`), the Fan Control module will automatically fallback to "Simulation Mode" to prevent application crashes.

---

## 👨‍💻 Author

**ReiKage** - GitHub: [@reikageisme](https://www.google.com/search?q=https://github.com/reikageisme)

* *A passionate CyberSecurity engineer and HomeLab enthusiast dedicated to building efficient, open-source infrastructure tools.*

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://www.google.com/search?q=https://github.com/reikageisme/Dashboard_Pi4/issues). If you like this project, please give it a ⭐️!

## 📝 License

This project is licensed under the **MIT License** - see the [LICENSE](https://github.com/reikageisme/Dashboard_Pi4/blob/main/LICENSE) file for details.

# 🍓 Pi Dashboard
![Version](https://img.shields.io/badge/version-2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.x-blue.svg)
![AI](https://img.shields.io/badge/AI-Gemini_2.0-orange.svg)
![Docker](https://img.shields.io/badge/docker-supported-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A sleek, modern web dashboard for monitoring your Raspberry Pi/HomeLab. Powered by Python (Flask + Waitress) and Google Gemini AI.

## ✨ Features
- 📊 **Real-time Monitoring:** Live CPU, RAM, Disk, Temp stats.
- 🐳 **Docker Management:** Start/Stop/Restart containers & Pull images from Docker Hub.
- 📉 **Top Processes:** View top 10 resource-hungry processes in real-time.
- 🌪️ **Fan Control:** Smart PWM control (Auto/Manual/Max) via GPIO.
- ⚡ **Speedtest:** Integrated network bandwidth test.
- 🛡️ **Pi-hole:** View query stats & disable blocking temporarily.
- 🌐 **Network Tunnel:** Manage Cloudflare Tunnels & View Open Ports.
- 💾 **Storage Manager:** Visualize disk usage across partitions.
- 🖥️ **Terminal:** View system logs (journalctl) in real-time.
- 🤖 **AI System Doctor:** One-click diagnostics using **Gemini 2.0 Flash AI** to analyze logs and detect errors.

---

## 🚀 Installation (Recommended: Direct on OS)

**1. Install Dependencies:**
```bash
sudo apt update && sudo apt install -y git python3-pip
git clone https://github.com/reikageisme/Dashboard_Pi4.git
cd Dashboard_Pi4
sudo pip3 install -r requirements.txt --break-system-packages
```

**2. Configure AI (Optional):**
Get a free API Key from [Google AI Studio](https://aistudio.google.com/).
Open `app.py` and paste your key into `GEMINI_API_KEY`.

**3. Run:**
```bash
sudo python3 app.py
```
*Access at: http://<your-pi-ip>:5000*

### 💡 Run as Service (Auto-Start)
create `/etc/systemd/system/pi_dashboard.service`:
```ini
[Unit]
Description=Pi Dashboard
After=network.target docker.service

[Service]
type=simple
User=root
WorkingDirectory=/home/your_user/Dashboard_Pi4
ExecStart=/usr/bin/python3 /home/your_user/Dashboard_Pi4/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Then enable:
```bash
sudo systemctl enable --now pi_dashboard.service
```

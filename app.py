import eventlet
eventlet.monkey_patch()
import os
import time
import threading
import psutil
import docker
import speedtest
import subprocess
import requests
import random
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from datetime import datetime
from datetime import timedelta
from functools import wraps
from dotenv import load_dotenv
from flask_socketio import SocketIO, emit, disconnect
import pty
import select
import termios
import struct
import fcntl
import shlex

# Load environment variables from .env file
load_dotenv()

# Thay thế thư viện cũ google.generativeai bằng google-genai mới
from google import genai
from google.genai import types
from waitress import serve


# Setup Gemini AI (New SDK)
try:
    # List of API keys for rotation/fallback
    GEMINI_API_KEYS = [
        os.getenv("GEMINI_API_KEY_0"),
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3")
    ]
    # Filter out None values in case some keys are missing
    GEMINI_API_KEYS = [key for key in GEMINI_API_KEYS if key]
    
    if not GEMINI_API_KEYS:
        print("Error: No Gemini API keys found in .env. Please add GEMINI_API_KEY_0 through GEMINI_API_KEY_3.")
        gemini_client = None
    else:
        # Select a random key to distribute load
        GEMINI_API_KEY = random.choice(GEMINI_API_KEYS)
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini Init Error: {e}")
    gemini_client = None

# Disable GPIO for now to debug crash
GPIO_AVAILABLE = False
# try:
#     import lgpio
#     GPIO_AVAILABLE = True
# except ImportError:
#     GPIO_AVAILABLE = False
#     print("lgpio not found, running in simulation mode for Fan Control")


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_change_me')
app.permanent_session_lifetime = timedelta(days=7)

# Initialize SocketIO (threading mode for stability)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# Auth Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return render_template('login.html') # Serve login page instead of redirect loop for SPA feel
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return redirect('/')
        
    data = request.json
    ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
    ADMIN_PASS = os.environ.get('ADMIN_PASS', 'admin')
    
    if data.get('username') == ADMIN_USER and data.get('password') == ADMIN_PASS:
        session.permanent = True
        session['logged_in'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid credentials"})

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# Try to connect to docker, if it fails, we handle it gracefully later
try:
    client = docker.from_env()
except Exception as e:
    client = None
    print(f"Warning: Could not connect to Docker: {e}")

# Global State
FAN_PIN = 18
FAN_SPEED = 0
FAN_MODE = 'manual'
SPEEDTEST_RESULT = {"ping": 0, "download": 0, "upload": 0, "timestamp": None}
SPEEDTEST_RUNNING = False
LAST_NET_IO = {"bytes_sent": 0, "bytes_recv": 0, "time": 0}
LAST_DISK_IO = {"read_bytes": 0, "write_bytes": 0, "time": 0}

# --- Uptime Monitor Globals ---
UPTIME_SITES = [
    {"name": "Google", "url": "https://google.com"},
    # Add more default sites here or load from a file
]
UPTIME_STATUS = {} # {url: {status: 200, latency: 50, last_check: ...}}

# --- Terminal Globals ---
TERMINAL_SESSIONS = {}
TERMINAL_FD_MAP = {}

# --- Hardware / GPIO Helper ---
class FanController:
    def __init__(self, pin):
        self.pin = pin
        self.handle = None
        if GPIO_AVAILABLE:
            try:
                self.handle = lgpio.gpiochip_open(0)
                # Try to claim, check if successful
                lgpio.gpio_claim_output(self.handle, self.pin)
            except Exception as e:
                print(f"Failed to init GPIO: {e}")
                self.handle = None

    def set_speed(self, speed_percent):
        """ speed_percent: 0 to 100 """
        global FAN_SPEED
        FAN_SPEED = speed_percent
        if self.handle:
            try:
                # Frequency 100Hz is generic for fans
                lgpio.tx_pwm(self.handle, self.pin, 100, float(speed_percent)) 
            except Exception as e:
                print(f"GPIO Error: {e}")

    def cleanup(self):
        if self.handle:
            lgpio.gpiochip_close(self.handle)

fan_ctrl = FanController(FAN_PIN)

def get_temp():
    temp = 0
    try:
        temps = psutil.sensors_temperatures()
        if 'cpu_thermal' in temps:
            temp = temps['cpu_thermal'][0].current
        elif 'coretemp' in temps: 
            temp = temps['coretemp'][0].current
        elif 'thermal_zone0' in temps:
             temp = temps['thermal_zone0'][0].current
    except:
        pass
    return temp

def auto_fan_loop():
    while True:
        if FAN_MODE == 'auto':
            temp = get_temp()
            # Simple Hysteresis / Curve
            if temp < 40:
                new_speed = 0
            elif temp < 50:
                new_speed = 40
            elif temp < 60:
                new_speed = 60
            elif temp < 70:
                new_speed = 80
            else:
                new_speed = 100
            
            if new_speed != FAN_SPEED:
                fan_ctrl.set_speed(new_speed)
        time.sleep(5)

# Start Auto Fan Thread
fan_thread = threading.Thread(target=auto_fan_loop, daemon=True)
fan_thread.start()

# --- Uptime Monitor Background Thread ---
def uptime_monitor_loop():
    while True:
        for site in UPTIME_SITES:
            url = site['url']
            try:
                start_time = time.time()
                resp = requests.get(url, timeout=5)
                latency = int((time.time() - start_time) * 1000)
                status_code = resp.status_code
                UPTIME_STATUS[url] = {
                    "status": "online" if 200 <= status_code < 400 else "offline",
                    "code": status_code,
                    "latency": latency,
                    "last_check": datetime.now().strftime("%H:%M:%S")
                }
            except Exception as e:
                UPTIME_STATUS[url] = {
                    "status": "offline",
                    "code": "ERR",
                    "latency": 0,
                    "last_check": datetime.now().strftime("%H:%M:%S"),
                    "error": str(e)
                }
        socketio.sleep(30) # Use socketio.sleep for greenlet compatibility if using eventlet

# Start Monitor Thread
monitor_thread = threading.Thread(target=uptime_monitor_loop, daemon=True) # Or socketio.start_background_task
# Ideally use socketio.start_background_task if fully committed to eventlet, but thread works for now with monkey patching
# monitor_thread.start() 

# --- Routes ---
@app.route('/api/stats')
@login_required
def get_stats():
    global LAST_NET_IO
    global LAST_DISK_IO
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=None)
    
    # RAM
    ram = psutil.virtual_memory()
    
    # Disk
    disk = psutil.disk_usage('/')
    
    # Temp
    temp = get_temp()

    # Time
    now_time = datetime.now()
    now_str = now_time.strftime("%H:%M:%S")

    # Network I/O Speed (Live)
    net_io = psutil.net_io_counters()
    cur_time = time.time()
    
    # Calculate bytes per second
    time_delta = cur_time - LAST_NET_IO["time"]
    tx_speed = 0
    rx_speed = 0
    
    if time_delta > 0 and LAST_NET_IO["time"] != 0:
        tx_speed = (net_io.bytes_sent - LAST_NET_IO["bytes_sent"]) / time_delta
        rx_speed = (net_io.bytes_recv - LAST_NET_IO["bytes_recv"]) / time_delta
    
    # Update global state
    LAST_NET_IO = {
        "bytes_sent": net_io.bytes_sent,
        "bytes_recv": net_io.bytes_recv,
        "time": cur_time
    }

    # Disk I/O (Read/Write Speed)
    try:
        disk_io = psutil.disk_io_counters()
        read_speed = 0
        write_speed = 0
        
        if time_delta > 0 and LAST_DISK_IO["time"] != 0:
            read_speed = (disk_io.read_bytes - LAST_DISK_IO["read_bytes"]) / time_delta
            write_speed = (disk_io.write_bytes - LAST_DISK_IO["write_bytes"]) / time_delta
        
        LAST_DISK_IO = {
            "read_bytes": disk_io.read_bytes,
            "write_bytes": disk_io.write_bytes,
            "time": cur_time
        }
    except Exception as e:
        read_speed = 0
        write_speed = 0
        print(f"Disk I/O Error: {e}")

    # Top Processes (by CPU)
    # Get top 5 sorted by cpu_percent
    top_procs = []
    try:
        # iterate over all processes
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                # cpu_percent needs a call to initialize, but since we can't wait for all, 
                # we rely on the background interval of psutil or just one-shot.
                # Actually psutil.process_iter cpu_percent(interval=None) returns 0.0 often on first call.
                # Cleaner way:
                pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # Alternative: Sorted once
        procs = sorted(
            [p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info'])],
            key=lambda p: p['cpu_percent'],
            reverse=True
        )[:5]
        
        top_procs = [{
            "pid": p['pid'],
            "name": p['name'],
            "cpu": p['cpu_percent'],
            "mem": round(p['memory_info'].rss / 1024 / 1024, 1) # MB
        } for p in procs]

    except Exception as e:
        print(f"Proc error: {e}")

    # Calculate Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    m, s = divmod(uptime_seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    uptime_str = f"{int(d)}d {int(h)}h {int(m)}m"

    return jsonify({
        "cpu": cpu_percent,
        "ram_percent": ram.percent,
        "ram_used": round(ram.used / 1024**3, 2),
        "ram_total": round(ram.total / 1024**3, 2),
        "disk_percent": disk.percent,
        "temp": temp,
        "time": now_str,
        "uptime": uptime_str,
        "fan_speed": FAN_SPEED,
        "fan_mode": FAN_MODE,
        "net_tx": tx_speed, # Bytes/s
        "net_rx": rx_speed, # Bytes/s
        "disk_read": read_speed,
        "disk_write": write_speed,
        "top_procs": top_procs
    })

@app.route('/api/system/power', methods=['POST'])
def system_power():
    action = request.json.get('action')
    try:
        # Check if we are running directly on host (simple heuristic or just try direct command first)
        # If running as root or sudo, direct commands work.
        # If running as user, sudo might be needed.
        
        cmd_prefix = []
        if os.geteuid() != 0:
            cmd_prefix = ['sudo']

        if action == 'reboot':
            subprocess.Popen(cmd_prefix + ["reboot"])
            return jsonify({"success": True, "message": "Rebooting..."})
        elif action == 'shutdown':
            subprocess.Popen(cmd_prefix + ["shutdown", "-h", "now"])
            return jsonify({"success": True, "message": "Shutting down..."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": False, "error": "Invalid action"})

@app.route('/ssh')
@login_required
def ssh_page():
    return render_template('ssh.html')

@app.route('/api/system_log')
@login_required
def system_log():
    try:
        # Lấy LOG THÔ (nhiều hơn để có bối cảnh cho AI)
        log_out = subprocess.check_output(['journalctl', '-n', '500', '--no-pager'], text=True, stderr=subprocess.STDOUT)
        
        # 1. TRẢ VỀ CHO GIAO DIỆN (Lọc bớt rác API)
        filtered_lines = [line for line in log_out.split('\n') if "GET /api/" not in line]
        final_log = "\n".join(filtered_lines[-100:])
        
        return jsonify({'log': final_log})
    except Exception as e:
        return jsonify({'log': f"Lỗi đọc log: {str(e)}"})

# --- Uptime Monitor Routes ---
@app.route('/api/uptime/list', methods=['GET'])
@login_required
def uptime_list():
    data = []
    for site in UPTIME_SITES:
        url = site['url']
        status = UPTIME_STATUS.get(url, {"status": "pending", "code": 0, "latency": 0})
        data.append({
            "name": site.get('name', url),
            "url": url,
            "status": status.get("status"),
            "code": status.get("code"),
            "latency": status.get("latency"),
            "last_check": status.get("last_check")
        })
    return jsonify(data)

@app.route('/api/uptime/add', methods=['POST'])
@login_required
def uptime_add():
    data = request.json
    name = data.get('name')
    url = data.get('url')
    if name and url:
        UPTIME_SITES.append({'name': name, 'url': url})
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Missing name or url"})

@app.route('/api/uptime/remove', methods=['POST'])
@login_required
def uptime_remove():
    url = request.json.get('url')
    global UPTIME_SITES
    UPTIME_SITES = [s for s in UPTIME_SITES if s['url'] != url]
    return jsonify({"success": True})

# --- File Manager Routes ---
BASE_DIR = os.path.expanduser('~')

@app.route('/api/files/list')
@login_required
def file_list():
    req_path = request.args.get('path', '')
    abs_path = os.path.join(BASE_DIR, req_path.lstrip('/'))
    
    # Security check: Ensure within BASE_DIR
    if not os.path.commonprefix([abs_path, BASE_DIR]) == BASE_DIR:
        return jsonify({"error": "Access denied"}), 403
        
    if not os.path.exists(abs_path):
        return jsonify({"error": "Path not found"}), 404
        
    files = []
    try:
        with os.scandir(abs_path) as entries:
            for entry in entries:
                files.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size,
                    "mod_time": datetime.fromtimestamp(entry.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    # Sort: folders first, then files
    files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    return jsonify({"path": req_path, "files": files})

@app.route('/api/files/read')
@login_required
def file_read():
    req_path = request.args.get('path', '')
    abs_path = os.path.join(BASE_DIR, req_path.lstrip('/'))
    
    if not os.path.commonprefix([abs_path, BASE_DIR]) == BASE_DIR:
        return jsonify({"error": "Access denied"}), 403
        
    if not os.path.isfile(abs_path):
        return jsonify({"error": "File not found"}), 404
        
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": f"Error reading file: {str(e)}"}), 500

@app.route('/api/files/save', methods=['POST'])
@login_required
def file_save():
    data = request.json
    req_path = data.get('path', '')
    content = data.get('content', '')
    abs_path = os.path.join(BASE_DIR, req_path.lstrip('/'))
    
    if not os.path.commonprefix([abs_path, BASE_DIR]) == BASE_DIR:
        return jsonify({"error": "Access denied"}), 403

    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/files/upload', methods=['POST'])
@login_required
def file_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    req_path = request.form.get('path', '')
    abs_path = os.path.join(BASE_DIR, req_path.lstrip('/'))
    
    if not os.path.isdir(abs_path):
        return jsonify({"error": "Target is not a directory"}), 400

    if not os.path.commonprefix([abs_path, BASE_DIR]) == BASE_DIR:
        return jsonify({"error": "Access denied"}), 403

    try:
        filename = file.filename
        save_path = os.path.join(abs_path, filename)
        file.save(save_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze_log', methods=['GET', 'POST'])
@login_required
def analyze_log():
    try:
        # 1. Get Log (Last 100 lines)
        log_out = subprocess.check_output(['journalctl', '-n', '100', '--no-pager'], text=True, stderr=subprocess.STDOUT)
        
        # Filter out "GET /api/" noise
        filtered_lines = [line for line in log_out.split('\n') if "GET /api/" not in line]
        final_log = "\n".join(filtered_lines[-50:])
        
        if not final_log.strip():
             return jsonify({'status': 'success', 'analysis': 'No significant logs found recently.'})

        # 2. Call Gemini
        # Model: gemini-2.0-flash-exp (Latest & Fastest)
        
        prompt = f"""
        You are an expert DevOps Engineer. Analyze the following Linux system logs from a Raspberry Pi:
        1. Identify any ERRORS, WARNINGS, or Security Threats (e.g., SSH failures).
        2. Summarize the system status in 3 short, clear bullet points.
        3. Provide a recommendation if any issues are found.
        
        Logs:
        {final_log}
        
        Response Format: Markdown, English, Use Emojis (No preamble).
        """
        
        # Use gemini_client to avoid conflict with docker client
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash', # Model
            contents=prompt
        )
        
        return jsonify({'status': 'success', 'analysis': response.text})

    except Exception as e:
        print(f"AI Error: {e}") # Print to service logs for debugging
        return jsonify({'status': 'error', 'analysis': f"AI Error: {str(e)}"})


def get_real_docker_stats():
    stats_dict = {}
    try:
        # Get stats from docker CLI directly
        raw_output = subprocess.check_output(
            ['docker', 'stats', '--no-stream', '--format', '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'], 
            text=True
        )
        
        for line in raw_output.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) == 3:
                    name, cpu, mem_full = parts
                    # mem_full format: "15.4MiB / 7.64GiB", take "15.4MiB"
                    mem_used = mem_full.split(' / ')[0] 
                    
                    # Fix: If Docker returns 0B (cgroup missing on Pi), use psutil fallback
                    if mem_used == "0B":
                        try:
                            # We can't easily map name -> pid here without client.
                            # So mark it as needing fallback
                            stats_dict[name] = {'cpu': cpu, 'mem': 'BATCH_FALLBACK'} 
                        except:
                            pass
                    else:
                        stats_dict[name] = {'cpu': cpu, 'mem': mem_used}
    except Exception as e:
        print(f"Docker stats error: {e}")
    return stats_dict

# --- New Features APIs ---

# 1. Start/Stop Cloudflare Tunnel & List Ports
@app.route('/api/network/tunnels')
@login_required
def get_tunnels():
    tunnels = []
    # 1. Search for any cloudflared service
    try:
        # List all units matching cloudflared*
        # systemctl list-units --all --no-pager --plain --no-legend 'cloudflared*'
        cmd = ['systemctl', 'list-units', '--all', '--no-pager', '--plain', '--no-legend', 'cloudflared*']
        if os.geteuid() != 0:
            cmd = ['sudo'] + cmd
            
        output = subprocess.check_output(cmd, text=True)
        # Output format: unit_name loaded active running description...
        for line in output.splitlines():
            parts = line.split()
            if parts:
                service_name = parts[0]
                status = parts[3] # running, exited, failed
                # Get a cleaner name
                name = service_name.replace('.service', '').replace('cloudflared-', '').title()
                tunnels.append({
                    "name": name, 
                    "service": service_name, 
                    "status": 'active' if status == 'running' else 'inactive'
                })
    except Exception as e:
        print(f"Error listing tunnels: {e}")
        # Fallback to hardcoded list if search fails (e.g. no permission)
        pass

    if not tunnels:
        # Fallback check for common names if list command failed or returned nothing but services exist hidden
        fallback_list = ["cloudflared", "cloudflared-tanh", "cloudflared-aceda"]
        for svc in fallback_list:
            full_svc = f"{svc}.service"
            try:
                subprocess.check_output(['systemctl', 'status', full_svc], stderr=subprocess.DEVNULL)
                # If status command succeeds, it exists
                is_active = subprocess.call(['systemctl', 'is-active', '--quiet', full_svc]) == 0
                tunnels.append({
                    "name": svc.replace('cloudflared-', '').title(),
                    "service": full_svc,
                    "status": "active" if is_active else "inactive"
                })
            except:
                pass

    return jsonify(tunnels)

@app.route('/api/network/tunnel/control', methods=['POST'])
@login_required
def control_tunnel():
    data = request.json
    service = data.get('service')
    action = data.get('action') # start, stop, restart
    
    if action not in ['start', 'stop', 'restart']:
        return jsonify({"success": False, "error": "Invalid action"})
    
    # Security check: ensure it is a cloudflared service
    if 'cloudflared' not in service or '..' in service or '/' in service:
         return jsonify({"success": False, "error": "Service not allowed"})

    cmd_prefix = []
    if os.geteuid() != 0:
        cmd_prefix = ['sudo']

    try:
        subprocess.run(cmd_prefix + ['systemctl', action, service], check=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/network/ports')
@login_required
def get_open_ports():
    ports = []
    try:
        # Use netstat or ss to get listening ports
        # ss -tuln
        cmd = ['ss', '-tuln']
        # If run as non-root, ss might show less info, mainly owned processes.
        # But for list of ports it usually works. 
        # If fails, try sudo
        try:
            output = subprocess.check_output(cmd, text=True)
        except:
             if os.geteuid() != 0:
                 cmd = ['sudo', 'ss', '-tuln']
                 output = subprocess.check_output(cmd, text=True)
             else:
                 raise

        # Parse output
        lines = output.splitlines()[1:] # Skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 5:
                # State Recv-Q Send-Q Local Address:Port Peer Address:Port
                # LISTEN 0 128 *:80 *:*
                proto = parts[0] # u_str
                local_addr = parts[4]
                if ':' in local_addr:
                    port = local_addr.split(':')[-1]
                    ports.append({"proto": proto.upper(), "port": port, "address": local_addr}) # Fix proto case
    except Exception as e:
        print(f"Error getting ports: {e}")
    
    unique_ports = list({v['port']:v for v in ports}.values())
    return jsonify(sorted(unique_ports, key=lambda x: int(x['port']) if x['port'].isdigit() else 99999))

# 2. Storage
@app.route('/api/storage')
@login_required
def get_storage():
    parts = []
    seen_mounts = set()
    
    # Try getting all partitions including loops but filter wisely
    for part in psutil.disk_partitions(all=False):
        if 'loop' in part.device or part.mountpoint in seen_mounts: continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            parts.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": round(usage.total / 1024**3, 2), # GB
                "used": round(usage.used / 1024**3, 2),
                "free": round(usage.free / 1024**3, 2),
                "percent": usage.percent
            })
            seen_mounts.add(part.mountpoint)
        except:
             pass
    
    # Ensure root / is present if missing (psutil bug in some containers)
    if '/' not in seen_mounts:
        try:
            usage = psutil.disk_usage('/')
            parts.insert(0, {
                "device": "root",
                "mountpoint": "/",
                "fstype": "ext4/overlay",
                "total": round(usage.total / 1024**3, 2),
                "used": round(usage.used / 1024**3, 2),
                "free": round(usage.free / 1024**3, 2),
                "percent": usage.percent
            })
        except:
            pass

    return jsonify(parts)

# 3. Pi-hole Proxy
@app.route('/api/pihole/summary')
@login_required
def pihole_summary():
    # Attempt multiple likely locations if ENV not set
    # 1. ENV, 2. Localhost, 3. Localhost:8080 (common alternative), 4. Docker Gateway (172.17.0.1)
    
    potential_urls = []
    if os.environ.get('PIHOLE_URL'):
        potential_urls.append(os.environ.get('PIHOLE_URL'))
    
    potential_urls.extend([
        'http://localhost/admin/api.php?summary',
        'http://127.0.0.1/admin/api.php?summary',
        'http://localhost:8080/admin/api.php?summary', # Non-standard port
        'http://pi.hole/admin/api.php?summary',
        'http://172.17.0.1/admin/api.php?summary' # Docker Host IP
    ])

    error_logs = []
    for url in potential_urls:
        try:
            resp = requests.get(url, timeout=2) # Fast timeout
            if resp.status_code == 200:
                return jsonify(resp.json())
        except Exception as e:
            error_logs.append(f"{url}: {str(e)}")
            continue

    return jsonify({"error": "Cannot connect to Pi-hole", "details": error_logs}), 502

@app.route('/api/pihole/disable', methods=['POST'])
@login_required
def pihole_disable():
    # Usually requires API Token &auth=TOKEN
    PIHOLE_TOKEN = os.environ.get('PIHOLE_TOKEN', '')
    PIHOLE_HOST = os.environ.get('PIHOLE_HOST', 'http://localhost')
    duration = request.json.get('duration', 300) # 5 mins
    
    url = f"{PIHOLE_HOST}/admin/api.php?disable={duration}&auth={PIHOLE_TOKEN}"
    try:
        resp = requests.get(url, timeout=5)
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 4. App Store (Simple implementation)
@app.route('/api/appstore/install', methods=['POST'])
@login_required
def install_app():
    app_name = request.json.get('app_name')
    # Define map of app_name -> docker-compose content or file path
    # For MVP, we'll just simulate success
    return jsonify({"success": True, "message": f"Installing {app_name} (Simulation)"})

def get_container_memory_usage(container):
    try:
        # Get PID of the container's main process
        pid = container.attrs['State']['Pid']
        if pid == 0: return "0 B"

        total_rss = 0
        try:
            p = psutil.Process(pid)
            total_rss += p.memory_info().rss
            for child in p.children(recursive=True):
                try:
                    total_rss += child.memory_info().rss
                except: pass
        except psutil.NoSuchProcess:
            pass
            
        # Convert to readable string
        if total_rss < 1024 * 1024:
            return f"{round(total_rss/1024, 2)} KiB"
        elif total_rss < 1024 * 1024 * 1024:
            return f"{round(total_rss/1024/1024, 2)} MiB"
        else:
             return f"{round(total_rss/1024/1024/1024, 2)} GiB"
    except Exception as e:
        return "0 B"

@app.route('/api/docker/containers')
@login_required
def get_containers():
    if not client:
        return jsonify({"error": "Docker not connected"}), 503

    # Get real stats using the helper function
    real_stats = get_real_docker_stats()
    
    containers_list = []
    try:
        containers = client.containers.list(all=True)
        for c in containers:
            cpu_usage = "0.00%"
            mem_usage = "0 B"
            
            # Use real stats if available and container is running
            if c.status == 'running':
                if c.name in real_stats:
                    s = real_stats[c.name]
                    if s['mem'] == 'BATCH_FALLBACK':
                         # Calculate manually via psutil
                         mem_usage = get_container_memory_usage(c)
                         cpu_usage = s['cpu'] # Keep docker's CPU if available, or 0.00%
                    else:
                         cpu_usage = s['cpu']
                         mem_usage = s['mem']
                else:
                    # Fallback if missed by docker stats (e.g. just started)
                    mem_usage = get_container_memory_usage(c)

            img_name = c.image.tags[0] if c.image.tags else c.image.id[:12] if c.image.id else "unknown"
            containers_list.append({
                "id": c.short_id,
                "name": c.name,
                "status": c.status,
                "image": img_name,
                "cpu": cpu_usage,
                "mem": mem_usage
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # Sort by 'running' first
    containers_list.sort(key=lambda x: x['status'] != 'running')
    return jsonify(containers_list)

@app.route('/api/docker/images')
def get_images():
    if not client:
        return jsonify({"error": "Docker not connected"}), 503
    try:
        images_list = []
        for img in client.images.list():
            if img.tags:
                for tag in img.tags:
                    images_list.append({"id": img.short_id, "tag": tag, "size": round(img.attrs['Size']/1024/1024, 2)})
            else:
                 images_list.append({"id": img.short_id, "tag": "<none>", "size": round(img.attrs['Size']/1024/1024, 2)})
        return jsonify(images_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/docker/image_action', methods=['POST'])
def image_action():
    action = request.json.get('action')
    target = request.json.get('target') # image name or id
    
    try:
        if action == 'pull':
            client.images.pull(target)
            return jsonify({"success": True, "message": f"Pulled {target}"})
        elif action == 'remove':
            client.images.remove(target, force=True)
            return jsonify({"success": True, "message": f"Removed {target}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": False, "error": "Unknown action"})

@app.route('/api/docker/action', methods=['POST'])
def docker_action():
    if not client:
         return jsonify({"success": False, "error": "Docker not connected"})

    data = request.json
    container_id = data.get('id')
    action = data.get('action')
    
    try:
        container = client.containers.get(container_id)
        if action == 'start':
            container.start()
        elif action == 'stop':
            container.stop()
        elif action == 'restart':
            container.restart()
        elif action == 'remove':
            container.remove(force=True)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/docker/logs/<container_id>')
def get_docker_logs(container_id):
    if not client:
        return jsonify({"error": "Docker not connected"}), 503
    try:
        container = client.containers.get(container_id)
        # Get last 100 lines
        logs = container.logs(tail=100).decode('utf-8', errors='ignore')
        return jsonify({"logs": logs, "name": container.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/fan', methods=['POST'])
def set_fan():
    global FAN_MODE
    data = request.json
    
    response_data = {"success": True}

    # Handle Mode Switch
    if 'mode' in data:
        mode = data.get('mode')
        if mode in ['auto', 'manual']:
            FAN_MODE = mode
            response_data["mode"] = FAN_MODE

    # Handle Speed Set (Only if Manual)
    if 'speed' in data:
        if FAN_MODE == 'auto':
             return jsonify({"error": "Cannot set speed in Auto mode"}), 400
        
        try:
            speed = int(data.get('speed', 0))
            if 0 <= speed <= 100:
                fan_ctrl.set_speed(speed)
                response_data["speed"] = speed
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return jsonify(response_data)
            
    return jsonify({"error": "Invalid request"}), 400

@app.route('/api/speedtest/result')
def get_speedtest_result():
    return jsonify({"running": SPEEDTEST_RUNNING, "result": SPEEDTEST_RESULT})

@app.route('/api/speedtest/run', methods=['POST'])
def run_speedtest():
    global SPEEDTEST_RUNNING
    if SPEEDTEST_RUNNING:
        return jsonify({"status": "already_running"})
    
    def run_job():
        global SPEEDTEST_RUNNING, SPEEDTEST_RESULT
        SPEEDTEST_RUNNING = True
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            dl = st.download() / 10**6 # Mbps
            ul = st.upload() / 10**6 # Mbps
            ping = st.results.ping
            SPEEDTEST_RESULT = {
                "ping": round(ping, 1),
                "download": round(dl, 2),
                "upload": round(ul, 2),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"Speedtest failed: {e}")
        finally:
            SPEEDTEST_RUNNING = False

    thread = threading.Thread(target=run_job)
    thread.start()
    return jsonify({"status": "started"})

# --- Terminal SocketIO Logic ---
def read_terminal_output(fd, sid):
    """ Reads from PTY and emits to socket """
    try:
        while True:
            # Check if session still exists
            if sid not in TERMINAL_SESSIONS:
                break
                
            try:
                # Use select to check for data
                (r, w, x) = select.select([fd], [], [], 1.0)
                if fd in r:
                    data = os.read(fd, 1024)
                    if not data:
                        break # EOF
                    socketio.emit('output', data.decode('utf-8', errors='ignore'), room=sid, namespace='/terminal')
            except OSError:
                break
    except Exception as e:
        print(f"Terminal Read Error: {e}")
    finally:
        # Cleanup if loop exits
        pass

@socketio.on('connect', namespace='/terminal')
def terminal_connect():
    if not session.get('logged_in'):
        return False

    sid = request.sid
    # Create PTY
    (child_pid, fd) = pty.fork()
    
    if child_pid == 0:
        # Child: set TERM and run bash
        os.environ['TERM'] = 'xterm-256color'
        os.chdir(os.path.expanduser('~'))
        # Using bash
        os.execv('/bin/bash', ['bash'])
    else:
        # Parent
        TERMINAL_SESSIONS[sid] = {"fd": fd, "pid": child_pid}
        
        # Start reader task
        socketio.start_background_task(target=read_terminal_output, fd=fd, sid=sid)
        print(f"Terminal session started: {sid} (PID: {child_pid})")

@socketio.on('disconnect', namespace='/terminal')
def terminal_disconnect():
    sid = request.sid
    if sid in TERMINAL_SESSIONS:
        info = TERMINAL_SESSIONS.pop(sid)
        fd = info['fd']
        pid = info['pid']
        try:
            os.close(fd)
            os.kill(pid, 9)
        except:
            pass
        print(f"Terminal session ended: {sid}")

@socketio.on('input', namespace='/terminal')
def terminal_input(data):
    sid = request.sid
    if sid in TERMINAL_SESSIONS:
        fd = TERMINAL_SESSIONS[sid]['fd']
        try:
            os.write(fd, data.encode())
        except Exception as e:
            print(f"Write Error: {e}")

@socketio.on('resize', namespace='/terminal')
def terminal_resize(data):
    sid = request.sid
    if sid in TERMINAL_SESSIONS:
        fd = TERMINAL_SESSIONS[sid]['fd']
        cols = data.get('cols', 80)
        rows = data.get('rows', 24)
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except:
            pass

if __name__ == '__main__':
    # Start Monitor Thread
    socketio.start_background_task(target=uptime_monitor_loop)

    print("🚀 Bật server Production (SocketIO) tại cổng 5000...")
    # Thêm allow_unsafe_werkzeug=True để tránh lỗi RuntimeError nếu eventlet không load được
    # Nhưng tốt nhất là nên chạy với eventlet, gevent hoặc uwsgi
    try:
        import eventlet
        socketio.run(app, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"Không thể chạy Eventlet: {e}, chuyển sang chế độ fallback (Werkzeug)")
        socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
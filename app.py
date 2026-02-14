import os
import time
import threading
import psutil
import docker
import speedtest
import subprocess
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from datetime import datetime
from functools import wraps

try:
    import lgpio
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("lgpio not found, running in simulation mode for Fan Control")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'phamtuananh_super_secret_key_4607')

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
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == 'admin' and data.get('password') == 'Phamtuananh4607?/':
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

# --- Routes ---




@app.route('/api/stats')
@login_required
def get_stats():
    global LAST_NET_IO
    
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
        "top_procs": top_procs
    })

@app.route('/api/system/power', methods=['POST'])
def system_power():
    action = request.json.get('action')
    try:
        if action == 'reboot':
            # Try systemctl first (systemd)
            # Since we are pid:host, we might be able to talk to system
            # Or use nsenter
            import subprocess
            # This 'nsenter' targeting PID 1 (systemd) usually works if privileged
            subprocess.Popen(["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "--", "reboot"])
            return jsonify({"success": True, "message": "Rebooting..."})
        elif action == 'shutdown':
            import subprocess
            subprocess.Popen(["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "--", "shutdown", "-h", "now"])
            return jsonify({"success": True, "message": "Shutting down..."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": False, "error": "Invalid action"})

@app.route('/api/system_log')
def system_log():
    try:
        # Use journalctl to get last 100 lines of system log
        # --no-pager makes it output text directly
        cmd = ['journalctl', '-n', '100', '--no-pager']
        
        # Check if we should point to host mounts
        if os.path.exists('/var/log/journal'):
             cmd.extend(['-D', '/var/log/journal'])
        elif os.path.exists('/run/log/journal'):
             cmd.extend(['-D', '/run/log/journal'])
             
        log_out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        return jsonify({'log': log_out})
    except subprocess.CalledProcessError as e:
        return jsonify({'log': f"Error reading log: {e.output}"})
    except Exception as e:
        try:
            # Fallback
            if os.path.exists('/var/log/syslog'):
                 res = subprocess.check_output(['tail', '-n', '100', '/var/log/syslog'], text=True)
                 return jsonify({'log': res})
        except:
             pass
        return jsonify({'log': f"Log access failed: {str(e)}\nEnsure /var/log is mounted."})

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
                    stats_dict[name] = {
                        'cpu': cpu,
                        'mem': mem_used
                    }
        return stats_dict
    except Exception as e:
        print(f"Error getting docker stats: {e}")
        return {}

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
            if c.status == 'running' and c.name in real_stats:
                cpu_usage = real_stats[c.name]['cpu']
                mem_usage = real_stats[c.name]['mem']

            img_name = c.image.tags[0] if c.image.tags else c.image.id[:12]
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
    
    # Handle Mode Switch
    if 'mode' in data:
        mode = data.get('mode')
        if mode in ['auto', 'manual']:
            FAN_MODE = mode
            if mode == 'auto':
                 # Trigger immediate update in loop eventually, or rely on loop
                 pass
            return jsonify({"success": True, "mode": FAN_MODE})

    # Handle Speed Set (Only if Manual)
    if 'speed' in data:
        if FAN_MODE == 'auto':
             return jsonify({"error": "Cannot set speed in Auto mode"}), 400
        
        try:
            speed = int(data.get('speed', 0))
            if 0 <= speed <= 100:
                fan_ctrl.set_speed(speed)
                return jsonify({"success": True, "speed": speed})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

// Initialize Chart
const ctx = document.getElementById('statsChart').getContext('2d');
const statsChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'CPU %',
            data: [],
            borderColor: '#ff6384',
            backgroundColor: 'rgba(255, 99, 132, 0.2)',
            tension: 0.4,
            fill: true
        }, {
            label: 'RAM %',
            data: [],
            borderColor: '#36a2eb',
            backgroundColor: 'rgba(54, 162, 235, 0.2)',
            tension: 0.4,
            fill: true
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                max: 100,
                grid: { color: '#444' }
            },
            x: {
                grid: { color: '#444' }
            }
        },
        plugins: {
             legend: { labels: { color: '#fff' } }
        },
        animation: false
    }
});

// Pi-hole Chart
let phChartCtx = document.getElementById('piholeChart');
let phChart = null;

if(phChartCtx) {
    phChart = new Chart(phChartCtx.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: ['Blocked', 'Allowed'],
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#dc3545', '#198754'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
             plugins: {
                legend: { position: 'bottom', labels: { color: '#fff' } }
            }
        }
    });
}


// Speed Gauge
const speedCtx = document.getElementById('speedChart').getContext('2d');
const speedChart = new Chart(speedCtx, {
    type: 'doughnut',
    data: {
        labels: ['Download', 'Upload', 'Rest'],
        datasets: [{
            data: [0, 0, 100],
            backgroundColor: ['#4bc0c0', '#9966ff', '#333'],
            borderWidth: 0,
            circumference: 180,
            rotation: 270
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: { display: false },
            title: { display: true, text: 'Download / Upload (Mbps)', color: '#ccc' }
        }
    }
});

// --- Fan Control ---
let fanMode = 'manual';

function setFanPreset(val) {
    if(fanMode === 'auto') {
        // Switch to Manual Mode first
        setFanMode('manual');
        // Small delay to allow mode switch to register visually
        setTimeout(() => {
            const slider = document.getElementById('fanRange');
            slider.value = val;
            slider.dispatchEvent(new Event('change'));
        }, 50);
        return;
    }
    const slider = document.getElementById('fanRange');
    slider.value = val;
    slider.dispatchEvent(new Event('change'));
}

function setFanMode(mode) {
    // Optimistic UI Update
    if(mode === 'auto') {
        fanMode = 'auto';
        showToast('Fan Mode', 'Switched to Auto Mode 🤖');
        updateFanUI('auto');
    } else {
        fanMode = 'manual';
        showToast('Fan Mode', 'Switched to Manual Mode 🛠️');
        updateFanUI('manual');
    }

    // Send mode and current slider value as speed (for continuity when switching to manual)
    const currentSpeed = parseInt(document.getElementById('fanRange').value) || 0;
    
    fetch('/api/fan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ mode: mode, speed: currentSpeed })
    })
    .catch(err => {
        showToast('Error', 'Failed to change fan mode');
        console.error(err);
    });
}

function updateFanUI(mode) {
    const slider = document.getElementById('fanRange');
    const badge = document.getElementById('fan-mode-badge');
    const display = document.getElementById('fan-display');
    
    if(mode === 'auto') {
        badge.textContent = "AUTO";
        badge.className = "badge bg-info";
        slider.disabled = true;
    } else {
        badge.textContent = "MANUAL";
        badge.className = "badge bg-secondary";
        slider.disabled = false;
    }
}


let procPage = 1;
const procLimit = 5;
let fullProcList = [];

function changeProcPage(d) {
    const maxPage = Math.ceil(fullProcList.length / procLimit) || 1;
    let next = procPage + d;
    if(next < 1) next = 1;
    if(next > maxPage) next = maxPage;
    procPage = next;
    renderProcTable();
}

function renderProcTable() {
    const procBody = document.getElementById('top-proc-body');
    const start = (procPage - 1) * procLimit;
    const end = start + procLimit;
    const pageData = fullProcList.slice(start, end);

    if(procBody) {
        procBody.innerHTML = pageData.map(p => `
            <tr>
                <td><small>${p.pid}</small></td>
                <td>${p.name}</td>
                <td class="text-warning">${p.cpu}%</td>
                <td>${p.mem} MB</td>
            </tr>
        `).join('');
    }
    
    // Update Page Count
    const ind = document.getElementById('proc-page-ind');
    if(ind) ind.textContent = `${procPage} / ${Math.ceil(fullProcList.length / procLimit) || 1}`;
}

// Stats Update
function updateStats() {
    // Optimization: Don't update if tab is hidden to save resources/battery
    // But to fix "lag on return", we might want a slower interval instead of full stop.
    // However, chart.js animation often causes the catch-up lag.
    if(document.hidden) return; 

    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            // Update Text
            const cpuEl = document.getElementById('cpu-val');
            if(cpuEl) cpuEl.textContent = data.cpu + '%';
            
            const ramEl = document.getElementById('ram-val');
            if(ramEl) ramEl.textContent = data.ram_percent + '%';
            if(document.getElementById('ram-detail')) document.getElementById('ram-detail').textContent = `${data.ram_used}/${data.ram_total} GB`;
            
            const tempEl = document.getElementById('temp-val');
            if(tempEl) {
                tempEl.textContent = data.temp + '°C';
                // Color Logic for Temp
                if(data.temp < 60) {
                     tempEl.className = 'stat-value text-success';
                } else if (data.temp < 75) {
                     tempEl.className = 'stat-value text-warning';
                } else {
                     tempEl.className = 'stat-value text-danger blink-anim';
                }
            }

            // Network I/O
            if(document.getElementById('net-tx')) {
                 document.getElementById('net-tx').textContent = formatBytes(data.net_tx) + '/s';
                 document.getElementById('net-rx').textContent = formatBytes(data.net_rx) + '/s';
            }

            // Disk I/O
            if(document.getElementById('disk-read-val')) {
                document.getElementById('disk-read-val').textContent = formatBytes(data.disk_read || 0) + '/s';
                document.getElementById('disk-write-val').textContent = formatBytes(data.disk_write || 0) + '/s';
            }

            // Top Processes
            if(data.top_procs) {
                fullProcList = data.top_procs;
                renderProcTable();
            }

            // Always update global elements (Clock & Uptime)
            const clockEl = document.getElementById('clock');
            if(clockEl) clockEl.textContent = data.time;
            
            const uptimeEl = document.getElementById('uptime');
            if(data.uptime && uptimeEl) uptimeEl.textContent = `Uptime: ${data.uptime}`;

            // Only update Chart and Fan if on Dashboard Tab (Optimization)
            const activeTab = document.querySelector('.nav-link.active').id;
            
            if(activeTab === 'dashboard-tab') {
                if(document.getElementById('disk-val')) document.getElementById('disk-val').textContent = data.disk_percent + '%';

                // Sync Fan if not dragging
                if(document.activeElement.id !== "fanRange") {
                    if (data.fan_mode === 'auto') {
                        document.getElementById('fanRange').value = data.fan_speed;
                    }
                    document.getElementById('fan-display').textContent = data.fan_speed;
                }
                
                // Update Fan Icon Speed CSS
                const fanIcon = document.getElementById('fan-icon');
                if(data.fan_speed > 0) {
                     fanIcon.classList.add('fa-spin');
                } else {
                     fanIcon.classList.remove('fa-spin');
                }

                if(fanMode !== data.fan_mode) {
                    fanMode = data.fan_mode;
                    updateFanUI(fanMode);
                }

                // Update Chart
                const label = data.time;
                statsChart.data.labels.push(label);
                statsChart.data.datasets[0].data.push(data.cpu);
                statsChart.data.datasets[1].data.push(data.ram_percent);

                if (statsChart.data.labels.length > 20) {
                    statsChart.data.labels.shift();
                    statsChart.data.datasets[0].data.shift();
                    statsChart.data.datasets[1].data.shift();
                }
                statsChart.update('none'); // 'none' mode prevents animation lag
            }
        });
}

// --- New Features Logic ---

// 1. Storage
function updateStorage() {
    fetch('/api/storage')
    .then(r => r.json())
    .then(data => {
        const list = document.getElementById('disk-list');
        list.innerHTML = data.map(d => `
            <div class="col-md-6 mb-3">
                <div class="card p-3">
                    <div class="d-flex justify-content-between">
                        <span class="fw-bold"><i class="fa-solid fa-hard-drive"></i> ${d.device}</span>
                        <small class="text-muted">${d.fstype}</small>
                    </div>
                    <small>${d.mountpoint}</small>
                    <div class="progress my-2 bg-secondary" style="height: 15px;">
                        <div class="progress-bar ${getDiskColor(d.percent)}" style="width: ${d.percent}%">${d.percent}%</div>
                    </div>
                    <div class="d-flex justify-content-between small text-muted">
                        <span>Used: ${d.used} GB</span>
                        <span>Total: ${d.total} GB</span>
                    </div>
                </div>
            </div>
        `).join('');
    });
}

function getDiskColor(p) {
    if(p < 70) return 'bg-success';
    if(p < 90) return 'bg-warning';
    return 'bg-danger';
}

// 2. Network & Tunnels
function updateNetwork() {
    console.log("updateNetwork called");
    // Tunnels
    fetch('/api/network/tunnels')
    .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
    })
    .then(data => {
        const list = document.getElementById('tunnels-list');
        if (list) {
            list.innerHTML = data.map(t => `
            <div class="d-flex justify-content-between align-items-center border-bottom py-2">
                <div>
                    <i class="fa-solid fa-cloud"></i> ${t.name}
                    <div class="small text-muted">${t.service}</div>
                </div>
                <div class="d-flex align-items-center gap-2">
                     <span class="badge ${t.status === 'active' ? 'bg-success' : 'bg-danger'}">${t.status}</span>
                     ${t.status === 'active' ? 
                         `<button class="btn btn-sm btn-outline-danger" onclick="controlTunnel('${t.service}', 'stop')">Stop</button>` :
                         `<button class="btn btn-sm btn-outline-success" onclick="controlTunnel('${t.service}', 'start')">Start</button>`
                     }
                     <button class="btn btn-sm btn-outline-secondary" onclick="controlTunnel('${t.service}', 'restart')"><i class="fa-solid fa-rotate"></i></button>
                </div>
            </div>
            `).join('');
        }
    })
    .catch(e => console.error("Tunnel error:", e));

    // Ports
    fetch('/api/network/ports')
    .then(r => {
        if (!r.ok) throw new Error("HTTP error " + r.status);
        return r.json();
    })
    .then(data => {
        const list = document.getElementById('ports-list');
        if (list) {
            list.innerHTML = data.map(p => `
            <li class="list-group-item d-flex justify-content-between">
                <span><span class="badge bg-secondary">${p.proto}</span> ${p.port}</span>
                <span class="text-muted small">${p.address}</span>
            </li>
            `).join('');
        }
    })
    .catch(e => console.error("Ports error:", e));
}

function controlTunnel(service, action) {
    showConfirmModal('Control Tunnel', `${action.toUpperCase()} ${service}?`, () => {
        fetch('/api/network/tunnel/control', {
             method: 'POST', 
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({service, action})
        })
        .then(r => r.json())
        .then(d => {
            if(d.success) {
                showToast('Tunnel', `${action} command sent.`);
                setTimeout(updateNetwork, 1000); // Wait for systemd
            } else {
                showToast('Error', d.error);
            }
        });
    });
}

// 3. Pi-hole
function updatePihole() {
    fetch('/api/pihole/summary')
    .then(r => r.json())
    .then(data => {
        if(data.error) {
            // handle error state visually
            return;
        }
        
        // Update Chart
        if(phChart) {
            // Assuming data.ads_blocked_today and data.dns_queries_today
             const blocked = parseInt(data.ads_blocked_today) || 0;
             const total = parseInt(data.dns_queries_today) || 0;
             const allowed = total - blocked;
             
             phChart.data.datasets[0].data = [blocked, allowed];
             phChart.update();
        }

        // Update Text
        document.getElementById('ph-queries').textContent = data.dns_queries_today;
        document.getElementById('ph-blocked').textContent = data.ads_blocked_today;
        document.getElementById('ph-percent').textContent = data.ads_percentage_today + '%';

    })
    .catch(() => {});
}

function disablePihole(duration) {
    fetch('/api/pihole/disable', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({duration})
    })
    .then(r => r.json())
    .then(d => {
        if(d.status) showToast('Pi-hole', `Status: ${d.status}`);
        else showToast('Pi-hole', 'Command sent (could not parse response)');
    });
}

// 4. App Store
function installApp(appName) {
    showConfirmModal('Install App', `Are you sure you want to install ${appName}? This will run 'docker-compose up'.`, () => {
        fetch('/api/appstore/install', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({app_name: appName})
        })
        .then(r=>r.json())
        .then(d => showToast('App Store', d.message));
    });
}

// --- Helper: Custom Confirm Modal ---
function formatBytes(bytes, decimals = 2) {
    if (!+bytes) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

// --- Helper: Custom Confirm Modal ---
function showConfirmModal(title, message, onConfirm) {
    const modalEl = document.getElementById('confirmModal');
    const modal = new bootstrap.Modal(modalEl);
    
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalBody').textContent = message;
    
    // Clear old listeners to avoid multiple triggers
    const confirmBtn = document.getElementById('confirmModalBtn');
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    
    newBtn.addEventListener('click', () => {
        modal.hide();
        onConfirm();
    });
    
    modal.show();
}

function systemPower(action) {
    showConfirmModal(
        'System Power', 
        `DANGER: Are you sure you want to ${action.toUpperCase()} the system?`, 
        () => {
            fetch('/api/system/power', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: action })
            })
            .then(r => r.json())
            .then(res => {
                if(res.success) showToast('System', res.message);
                else showToast('Error', res.error, 'bg-danger');
            });
        }
    );
}

function showToast(title, message, headerClass = 'bg-primary') {
    const toastEl = document.getElementById('liveToast');
    const toast = new bootstrap.Toast(toastEl);
    
    document.getElementById('toast-title').textContent = title;
    document.getElementById('toast-body').textContent = message;
    // Simple color logic if needed
    toast.show();
}

function updateDocker() {
    // Only fetch if Docker tab is active
     if(document.querySelector('.nav-link.active').id !== 'docker-tab') return;
     
    // Fetch Containers
    fetch('/api/docker/containers')
        .then(response => response.json())
        .then(data => {
            const tbody = document.getElementById('docker-table-body');
            tbody.innerHTML = '';
            
            if(data.error) {
                tbody.innerHTML = `<tr><td colspan="4" class="text-danger">${data.error}</td></tr>`;
                return;
            }

            data.forEach(c => {
                const tr = document.createElement('tr');
                
                let badgeClass = 'bg-secondary';
                if(c.status === 'running') badgeClass = 'bg-success';
                else if(c.status === 'exited') badgeClass = 'bg-danger';

                tr.innerHTML = `
                    <td><strong>${c.name}</strong><br><small class="text-muted">${c.image}</small></td>
                    <td></td>
                    <td>
                        <small class="d-block text-warning"><i class="fa-solid fa-microchip"></i> ${c.cpu || '0%'}</small>
                        <small class="d-block text-info"><i class="fa-solid fa-memory"></i> ${c.mem || '0 B'}</small>
                    </td>
                    <td><span class="badge ${badgeClass}">${c.status.toUpperCase()}</span></td>
                    <td class="text-end">
                        <div class="btn-group">
                            <button class="btn btn-sm btn-outline-success" title="Start" onclick="dockerAction('${c.id}', 'start')"><i class="fa-solid fa-play"></i></button>
                            <button class="btn btn-sm btn-outline-warning" title="Restart" onclick="dockerAction('${c.id}', 'restart')"><i class="fa-solid fa-rotate-right"></i></button>
                            <button class="btn btn-sm btn-outline-secondary" title="Stop" onclick="dockerAction('${c.id}', 'stop')"><i class="fa-solid fa-stop"></i></button>
                            <button class="btn btn-sm btn-outline-info" title="Logs" onclick="showLogs('${c.id}')"><i class="fa-solid fa-terminal"></i></button>
                             <button class="btn btn-sm btn-outline-danger" title="Remove" onclick="dockerAction('${c.id}', 'remove')"><i class="fa-solid fa-trash"></i></button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        });
    
    // Also update Images
    updateImages();
}

function updateImages() {
     fetch('/api/docker/images')
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('image-table-body');
            tbody.innerHTML = '';
             data.forEach(img => {
                 const tr = document.createElement('tr');
                 tr.innerHTML = `
                    <td class="text-truncate" style="max-width: 150px;" title="${img.tag}">${img.tag}</td>
                    <td><small>${img.size} MB</small></td>
                    <td class="text-end"><button class="btn btn-sm btn-link text-danger p-0" onclick="imageAction('remove', '${img.id}')"><i class="fa-solid fa-trash"></i></button></td>
                 `;
                 tbody.appendChild(tr);
             });
        });
}

function pullImage() {
    const target = document.getElementById('pull-image-name').value;
    if(!target) return;
    
    showToast('Docker', `Pulling ${target}... this may take a while.`);
    imageAction('pull', target);
}

function imageAction(action, target) {
    const performAction = () => {
        fetch('/api/docker/image_action', {
             method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: action, target: target })
        })
        .then(r => r.json())
        .then(res => {
            if(res.success) {
                showToast('Docker', res.message);
                updateImages();
            } else {
                 showToast('Error', res.error, 'bg-danger');
            }
        });
    };

    if(action === 'remove') {
        showConfirmModal(
            'Delete Image', 
            `Are you sure you want to remove image ${target}?`, 
            performAction
        );
    } else {
        performAction();
    }
}

function showLogs(id) {
    const modal = new bootstrap.Modal(document.getElementById('logsModal'));
    document.getElementById('logs-content').textContent = "Loading logs...";
    modal.show();
    
    fetch(`/api/docker/logs/${id}`)
    .then(r => r.json())
    .then(data => {
         document.getElementById('logsModalTitle').textContent = `Logs: ${data.name || id}`;
         document.getElementById('logs-content').textContent = data.logs || "No logs found.";
    });
}

function dockerAction(id, action) {
    showConfirmModal(
        'Container Action', 
        `Confirm ${action} for container ${id}?`, 
        () => {
            fetch('/api/docker/action', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ id: id, action: action })
            })
            .then(r => r.json())
            .then(res => {
                if(res.success) {
                    showToast('Docker', `Container ${id} ${action}ed successfully.`);
                    updateDocker(); 
                } else {
                    showToast('Error', res.error, 'bg-danger');
                }
            });
        }
    );
}

// Fan Control Slider
const fanInput = document.getElementById('fanRange');
fanInput.addEventListener('change', function() {
    const speed = parseInt(this.value);
    document.getElementById('fan-display').textContent = speed;

    // If manually dragged while in Auto, switch to Manual first (or simultaneously)
    if(fanMode === 'auto') {
        fanMode = 'manual'; // Optimistic update to prevent double firing
        updateFanUI('manual');
        showToast('Fan Mode', 'Switched to Manual Mode 🛠️');
        
        // Send both mode and speed
        fetch('/api/fan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ mode: 'manual', speed: speed })
        });
    } else {
        // Just send speed
        fetch('/api/fan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ speed: speed })
        });
    }
});
fanInput.addEventListener('input', function() {
    document.getElementById('fan-display').textContent = this.value;
});

// Speedtest
document.getElementById('btn-speedtest').addEventListener('click', function() {
    this.disabled = true;
    document.getElementById('speedtest-status').textContent = 'Initialising...';
    
    fetch('/api/speedtest/run', { method: 'POST' })
        .then(r => r.json())
        .then(res => {
            if(res.status === 'already_running') {
                document.getElementById('speedtest-status').textContent = 'Busy...';
            }
            checkSpeedtest();
        });
});

function checkSpeedtest() {
    fetch('/api/speedtest/result')
        .then(r => r.json())
        .then(data => {
            if (data.running) {
                document.getElementById('speedtest-status').textContent = 'Testing in progress...';
                setTimeout(checkSpeedtest, 1000);
            } else {
                document.getElementById('btn-speedtest').disabled = false;
                document.getElementById('speedtest-status').textContent = data.result.timestamp ? ('Last Run: ' + data.result.timestamp) : '';
                
                // Update Gauge
                const dl = data.result.download || 0;
                const ul = data.result.upload || 0;
                const max = Math.max(dl + ul, 100); // Dynamic scale
                
                speedChart.data.datasets[0].data = [dl, ul, max - (dl + ul)];
                speedChart.update();
            }
        });
}

function loadLogs() {
    fetch('/api/system_log')
        .then(res => res.json())
        .then(data => {
            let logBox = document.getElementById('log-container');
            if(!logBox) return; 
            // Đổ text log vào khung
            logBox.textContent = data.log;
            // Scroll to bottom
            logBox.scrollTop = logBox.scrollHeight;
        })
        .catch(err => console.error("Lỗi tải log:", err));
}

// Tab Event Listener to trigger updates immediately on switch
const tabEls = document.querySelectorAll('button[data-bs-toggle="tab"]');
tabEls.forEach(tabEl => {
    tabEl.addEventListener('shown.bs.tab', event => {
        const id = event.target.id;
        if(id === 'docker-tab') {
            updateDocker(); // Fetch immediately
        } else if (id === 'dashboard-tab') {
            updateStats();
        } else if (id === 'term-tab') {
            loadLogs(); // Fetch logs immediately
        } else if (id === 'pihole-tab') {
             updatePihole();
        } else if (id === 'network-tab') {
             updateNetwork();
        } else if (id === 'storage-tab') {
             updateStorage();
        }
    });
});

// Initial Loops
setInterval(updateStats, 1000); // 1s interval
setInterval(updateDocker, 3000);
setInterval(loadLogs, 5000);

// Add intervals for new tabs to handle auto-refresh
setInterval(() => {
    const activeId = document.querySelector('.nav-link.active')?.id;
    if (activeId === 'pihole-tab') updatePihole();
    else if (activeId === 'network-tab') updateNetwork();
    else if (activeId === 'storage-tab') updateStorage();
}, 5000);

updateStats();
updateDocker();
checkSpeedtest();
// loadLogs is called by interval and tab switch


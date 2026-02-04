import { invoke } from '@tauri-apps/api/tauri';

// =====================================================
// DOM Elements
// =====================================================
const serverStatus = document.getElementById('server-status');
const estopStatus = document.getElementById('estop-status');
const eventsList = document.getElementById('events-list');

const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnDashboard = document.getElementById('btn-dashboard');
const btnEstopOn = document.getElementById('btn-estop-on');
const btnEstopOff = document.getElementById('btn-estop-off');
const btnLogs = document.getElementById('btn-logs');
const btnDiagnostic = document.getElementById('btn-diagnostic');

// =====================================================
// Status Update
// =====================================================
async function updateStatus() {
    try {
        const status = await invoke('get_server_status');

        // Server status
        if (status.running) {
            serverStatus.textContent = 'Server: Running';
            serverStatus.className = 'status-badge running';
            btnStart.disabled = true;
            btnStop.disabled = false;
        } else {
            serverStatus.textContent = 'Server: Stopped';
            serverStatus.className = 'status-badge stopped';
            btnStart.disabled = false;
            btnStop.disabled = true;
        }

        // E-STOP status
        if (status.estop) {
            estopStatus.textContent = 'E-STOP: ON';
            estopStatus.className = 'status-badge estop-on';
        } else {
            estopStatus.textContent = 'E-STOP: OFF';
            estopStatus.className = 'status-badge estop-off';
        }

        // Load events if server is running
        if (status.running) {
            await loadEvents();
        }
    } catch (error) {
        console.error('Status update failed:', error);
        serverStatus.textContent = 'Server: Error';
        serverStatus.className = 'status-badge stopped';
    }
}

// =====================================================
// Events
// =====================================================
async function loadEvents() {
    try {
        const data = await invoke('get_home_data');

        if (data.recent_events && data.recent_events.length > 0) {
            eventsList.innerHTML = data.recent_events.map(event => `
                <div class="event-item">
                    <div>
                        <span class="symbol">${event.symbol}</span>
                        <span class="type">${event.event_type}</span>
                    </div>
                    <span class="time">${formatTime(event.created_at)}</span>
                </div>
            `).join('');
        } else {
            eventsList.innerHTML = '<p class="empty">No recent events</p>';
        }
    } catch (error) {
        console.error('Failed to load events:', error);
        eventsList.innerHTML = '<p class="empty">Failed to load events</p>';
    }
}

function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// =====================================================
// Toast Notifications
// =====================================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// =====================================================
// Event Handlers
// =====================================================
btnStart.addEventListener('click', async () => {
    btnStart.disabled = true;
    try {
        await invoke('start_server');
        showToast('Server starting...');
        setTimeout(updateStatus, 2000);
    } catch (error) {
        showToast('Failed to start server', 'error');
        btnStart.disabled = false;
    }
});

btnStop.addEventListener('click', async () => {
    btnStop.disabled = true;
    try {
        await invoke('stop_server');
        showToast('Server stopped');
        setTimeout(updateStatus, 1000);
    } catch (error) {
        showToast('Failed to stop server', 'error');
        btnStop.disabled = false;
    }
});

btnDashboard.addEventListener('click', async () => {
    try {
        await invoke('open_dashboard');
    } catch (error) {
        showToast('Failed to open dashboard', 'error');
    }
});

btnEstopOn.addEventListener('click', async () => {
    try {
        await invoke('set_estop', { enabled: true });
        showToast('E-STOP activated', 'warning');
        updateStatus();
    } catch (error) {
        showToast('Failed to set E-STOP', 'error');
    }
});

btnEstopOff.addEventListener('click', async () => {
    try {
        await invoke('set_estop', { enabled: false });
        showToast('E-STOP deactivated');
        updateStatus();
    } catch (error) {
        showToast('Failed to set E-STOP', 'error');
    }
});

btnLogs.addEventListener('click', async () => {
    try {
        await invoke('open_logs_folder');
    } catch (error) {
        showToast('Failed to open logs folder', 'error');
    }
});

btnDiagnostic.addEventListener('click', async () => {
    btnDiagnostic.disabled = true;
    btnDiagnostic.textContent = 'Exporting...';
    try {
        const path = await invoke('export_diagnostic');
        showToast(`Diagnostic exported: ${path}`);
    } catch (error) {
        showToast('Failed to export diagnostic', 'error');
    } finally {
        btnDiagnostic.disabled = false;
        btnDiagnostic.textContent = 'Export Diagnostic';
    }
});

// =====================================================
// Initialize
// =====================================================
updateStatus();

// Periodic status update
setInterval(updateStatus, 5000);

import { invoke } from '@tauri-apps/api/tauri';

// =====================================================
// DOM Elements
// =====================================================
const serverStatus = document.getElementById('server-status');
const estopStatus = document.getElementById('estop-status');
const eventsList = document.getElementById('events-list');

// Status lights
const lightServer = document.getElementById('light-server');
const lightEstop = document.getElementById('light-estop');

// Status overview
const lastSignal = document.getElementById('last-signal');
const lastOrder = document.getElementById('last-order');
const lastFilled = document.getElementById('last-filled');
const systemStatusEl = document.getElementById('system-status');

// Timeline & Connectors
const timelineList = document.getElementById('timeline-list');
const connectorList = document.getElementById('connector-list');

// Error guide
const errorGuide = document.getElementById('error-guide');
const errorMessage = document.getElementById('error-message');
const errorSolution = document.getElementById('error-solution');

// Buttons
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnDashboard = document.getElementById('btn-dashboard');
const btnEstopOn = document.getElementById('btn-estop-on');
const btnEstopOff = document.getElementById('btn-estop-off');
const btnLogs = document.getElementById('btn-logs');
const btnDiagnostic = document.getElementById('btn-diagnostic');

// Navigation
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');
const subscriptionBadge = document.getElementById('subscription-badge');

// Page titles mapping
const pageTitles = {
    dashboard: 'Dashboard',
    accounts: 'Accounts & API Keys',
    templates: 'TradingView Templates',
    settings: 'System Settings',
    logs: 'Trade Logs'
};

// =====================================================
// Navigation
// =====================================================
navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        navigateTo(page);
    });
});

function navigateTo(page) {
    // Update nav active state
    navItems.forEach(nav => {
        nav.classList.toggle('active', nav.dataset.page === page);
    });

    // Update page title
    pageTitle.textContent = pageTitles[page] || 'Dashboard';

    // Show/hide pages
    document.querySelectorAll('.page-content').forEach(pageEl => {
        pageEl.style.display = 'none';
    });
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Page-specific initialization
    if (page === 'accounts') {
        loadAccounts();
    }
}

// =====================================================
// Status Update
// =====================================================
async function updateStatus() {
    try {
        const status = await invoke('get_server_status');

        // Server status with light
        if (status.running) {
            serverStatus.textContent = 'Server: Running';
            lightServer.className = 'status-light green';
            btnStart.disabled = true;
            btnStop.disabled = false;
            systemStatusEl.textContent = 'Normal';
            systemStatusEl.style.color = '#22C55E';
        } else {
            serverStatus.textContent = 'Server: Stopped';
            lightServer.className = 'status-light red';
            btnStart.disabled = false;
            btnStop.disabled = true;
            systemStatusEl.textContent = 'Offline';
            systemStatusEl.style.color = '#EF4444';
        }

        // E-STOP status with light
        if (status.estop) {
            estopStatus.textContent = 'E-STOP: ON';
            lightEstop.className = 'status-light red';
            systemStatusEl.textContent = 'E-STOP Active';
            systemStatusEl.style.color = '#EF4444';
        } else {
            estopStatus.textContent = 'E-STOP: OFF';
            lightEstop.className = 'status-light green';
        }

        // Load data if server is running
        if (status.running) {
            await Promise.all([
                loadEvents(),
                loadTimeline(),
                loadStatusOverview(),
                loadConnectorStatus(),
                loadSubscription()
            ]);
            hideError();
        }
    } catch (error) {
        console.error('Status update failed:', error);
        serverStatus.textContent = 'Server: Error';
        lightServer.className = 'status-light red';
        showError('CONNECTION_ERROR', 'Cannot connect to server');
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
                        <span class="symbol">${event.symbol || '--'}</span>
                        <span class="type">${event.event_type || ''}</span>
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

function formatDateTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
        return date.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    return date.toLocaleDateString('ko-KR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// =====================================================
// Status Overview
// =====================================================
async function loadStatusOverview() {
    try {
        const data = await invoke('get_home_data');

        if (data.items && data.items.length > 0) {
            let recentSignal = null;
            let recentOrder = null;
            let recentFilled = null;

            for (const item of data.items) {
                if (item.last_signal_at) {
                    if (!recentSignal || new Date(item.last_signal_at) > new Date(recentSignal)) {
                        recentSignal = item.last_signal_at;
                    }
                }
                if (item.last_order_at) {
                    if (!recentOrder || new Date(item.last_order_at) > new Date(recentOrder)) {
                        recentOrder = item.last_order_at;
                    }
                }
                if (item.last_filled_qty) {
                    if (!recentFilled || new Date(item.last_checked_at) > new Date(recentFilled)) {
                        recentFilled = item.last_checked_at;
                    }
                }
            }

            lastSignal.textContent = formatDateTime(recentSignal);
            lastOrder.textContent = formatDateTime(recentOrder);
            lastFilled.textContent = recentFilled ? formatDateTime(recentFilled) : '--';
        }
    } catch (error) {
        console.error('Failed to load status overview:', error);
    }
}

// =====================================================
// Order Timeline (using new Tauri command)
// =====================================================
async function loadTimeline() {
    try {
        // Try new fetch_timeline command first
        let timelineData = [];
        try {
            timelineData = await invoke('fetch_timeline', { limit: 10 });
        } catch (e) {
            // Fallback to get_home_data
            const data = await invoke('get_home_data');
            if (data.items) {
                timelineData = data.items
                    .filter(item => item.last_order_at)
                    .map(item => ({
                        timestamp: item.last_order_at,
                        event_type: item.last_order_status || 'unknown',
                        message: item.symbol,
                        symbol: item.symbol
                    }));
            }
        }

        if (timelineData && timelineData.length > 0) {
            timelineList.innerHTML = timelineData.slice(0, 5).map(event => {
                const status = event.event_type || 'received';
                const statusClass = getStatusClass(status);

                return `
                    <div class="timeline-item ${statusClass}">
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <span class="timeline-symbol">${event.symbol || event.message || '--'}</span>
                                <span class="timeline-status ${statusClass}">${status}</span>
                            </div>
                            <div class="timeline-details">${event.message || ''}</div>
                            <div class="timeline-time">${formatDateTime(event.timestamp)}</div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            timelineList.innerHTML = '<p class="empty">No recent orders</p>';
        }
    } catch (error) {
        console.error('Failed to load timeline:', error);
        timelineList.innerHTML = '<p class="empty">Failed to load timeline</p>';
    }
}

function getStatusClass(status) {
    const statusMap = {
        'sent': 'sent',
        'filled': 'filled',
        'partial': 'partial',
        'failed': 'failed',
        'received': 'received',
        'signal': 'received',
        'order': 'sent'
    };
    return statusMap[status.toLowerCase()] || 'received';
}

// =====================================================
// Connector Status (using new Tauri command)
// =====================================================
async function loadConnectorStatus() {
    try {
        let connectors = [];
        try {
            connectors = await invoke('fetch_connector_status');
        } catch (e) {
            // If API not available, show default connectors
            connectors = [
                { exchange: 'OKX', connected: false, last_ping: null },
                { exchange: 'KIS', connected: false, last_ping: null }
            ];
        }

        if (connectors && connectors.length > 0) {
            connectorList.innerHTML = connectors.map(conn => {
                const statusClass = conn.connected ? 'connected' : 'disconnected';
                const statusText = conn.connected ? 'Connected' : 'Disconnected';
                const statusIcon = conn.connected ? '●' : '○';

                return `
                    <div class="connector-item">
                        <span class="connector-name">${conn.exchange}</span>
                        <span class="connector-status ${statusClass}">
                            ${statusIcon} ${statusText}
                        </span>
                    </div>
                `;
            }).join('');
        } else {
            connectorList.innerHTML = '<p class="empty">No connectors configured</p>';
        }
    } catch (error) {
        console.error('Failed to load connector status:', error);
        connectorList.innerHTML = '<p class="empty">Failed to load connectors</p>';
    }
}

// =====================================================
// Subscription (using new Tauri command)
// =====================================================
async function loadSubscription() {
    try {
        const subscription = await invoke('fetch_subscription');

        if (subscription) {
            subscriptionBadge.textContent = subscription.plan || 'Free';

            // Update badge style based on plan
            subscriptionBadge.className = 'subscription-badge';
            if (subscription.plan === 'Pro') {
                subscriptionBadge.classList.add('pro');
            } else if (subscription.plan === 'Hub') {
                subscriptionBadge.classList.add('hub');
            }
        }
    } catch (error) {
        console.error('Failed to load subscription:', error);
        subscriptionBadge.textContent = 'Free';
    }
}

// =====================================================
// Error Guide with Human-readable Messages
// =====================================================
const ERROR_GUIDES = {
    'CONNECTION_ERROR': {
        message: 'Server connection failed',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Check if the server is running</li>
                <li>Click <strong>Start Server</strong> button</li>
                <li>Verify port 8000 is not in use</li>
            </ul>
        `
    },
    'INSUFFICIENT_BAL': {
        message: 'Insufficient balance for order',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Check your exchange account balance</li>
                <li>Reduce order quantity</li>
                <li>Deposit more funds to your trading account</li>
            </ul>
        `
    },
    'ESTOP_ACTIVE': {
        message: 'E-STOP is active - all orders blocked',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Click <strong>E-STOP OFF</strong> to resume trading</li>
                <li>Verify system is ready before resuming</li>
            </ul>
        `
    },
    'API_KEY_INVALID': {
        message: 'API key authentication failed',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Verify API key is correct</li>
                <li>Check API key permissions (trading enabled)</li>
                <li>Regenerate API key if necessary</li>
            </ul>
        `
    },
    'RATE_LIMITED': {
        message: 'Too many requests - rate limited by exchange',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Wait 1-2 minutes before retrying</li>
                <li>Reduce signal frequency</li>
            </ul>
        `
    }
};

function showError(errorCode, rawMessage) {
    const guide = ERROR_GUIDES[errorCode] || {
        message: rawMessage || 'An error occurred',
        solution: `
            <h4>General Steps:</h4>
            <ul>
                <li>Check server logs for details</li>
                <li>Export diagnostic report</li>
                <li>Contact support if issue persists</li>
            </ul>
        `
    };

    errorMessage.textContent = guide.message;
    errorSolution.innerHTML = guide.solution;
    errorGuide.style.display = 'block';
}

function hideError() {
    errorGuide.style.display = 'none';
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
    // Confirmation dialog
    if (!confirm('E-STOP을 켜시겠습니까?\n\n모든 주문 전송이 차단됩니다.')) {
        return;
    }

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
        showToast(`Diagnostic exported`);
    } catch (error) {
        showToast('Failed to export diagnostic', 'error');
    } finally {
        btnDiagnostic.disabled = false;
        btnDiagnostic.textContent = 'Export Diagnostic';
    }
});

// =====================================================
// Accounts Page
// =====================================================

// DOM Elements for Accounts
const accountsList = document.getElementById('accounts-list');
const btnAddAccount = document.getElementById('btn-add-account');
const accountModal = document.getElementById('account-modal');
const modalTitle = document.getElementById('modal-title');
const modalClose = document.getElementById('modal-close');
const accountForm = document.getElementById('account-form');
const accountName = document.getElementById('account-name');
const accountExchange = document.getElementById('account-exchange');
const apiKey = document.getElementById('api-key');
const apiSecret = document.getElementById('api-secret');
const apiPassphrase = document.getElementById('api-passphrase');
const passphraseGroup = document.getElementById('passphrase-group');
const btnTestConnection = document.getElementById('btn-test-connection');
const formMessage = document.getElementById('form-message');

// Delete Modal
const deleteModal = document.getElementById('delete-modal');
const deleteModalClose = document.getElementById('delete-modal-close');
const deleteAccountName = document.getElementById('delete-account-name');
const btnCancelDelete = document.getElementById('btn-cancel-delete');
const btnConfirmDelete = document.getElementById('btn-confirm-delete');

let editingAccount = null;
let deletingAccount = null;

// Load accounts when navigating to Accounts page
async function loadAccounts() {
    try {
        // Try to get accounts from server first, then fall back to local
        let accounts = [];
        try {
            accounts = await invoke('fetch_server_accounts');
        } catch (e) {
            console.log('Server accounts not available, loading local');
        }

        // Merge with local accounts
        const localAccounts = await invoke('list_local_accounts');

        // Combine and deduplicate
        const accountMap = new Map();
        for (const acc of [...accounts, ...localAccounts]) {
            const key = `${acc.name}-${acc.exchange}`;
            if (!accountMap.has(key)) {
                accountMap.set(key, acc);
            }
        }

        const allAccounts = Array.from(accountMap.values());

        if (allAccounts.length === 0) {
            accountsList.innerHTML = `
                <div class="empty-state">
                    <p class="empty">No accounts registered yet.</p>
                    <p class="empty">Click "Add Account" to register your first exchange account.</p>
                </div>
            `;
            return;
        }

        accountsList.innerHTML = allAccounts.map(account => `
            <div class="account-card" data-name="${account.name}" data-exchange="${account.exchange}">
                <div class="account-card-header">
                    <div class="account-info">
                        <h3>${account.name}</h3>
                        <div class="account-exchange">
                            <span class="exchange-badge ${account.exchange.toLowerCase()}">${account.exchange}</span>
                        </div>
                    </div>
                    <div class="account-status ${account.is_active ? 'active' : 'inactive'}">
                        ${account.is_active ? '● Active' : '○ Inactive'}
                    </div>
                </div>
                <div class="account-card-body">
                    <div class="account-detail">
                        <span class="account-detail-label">API Key</span>
                        <span class="account-detail-value">****${account.has_keys ? '(saved)' : '(not set)'}</span>
                    </div>
                    <div class="account-detail">
                        <span class="account-detail-label">Last Health Check</span>
                        <span class="account-detail-value">${account.last_health_check ? formatDateTime(account.last_health_check) : '--'}</span>
                    </div>
                    <div class="account-detail">
                        <span class="account-detail-label">Status</span>
                        <span class="account-detail-value">${account.health_status || '--'}</span>
                    </div>
                </div>
                <div class="account-card-actions">
                    <button class="btn btn-secondary btn-edit" data-name="${account.name}" data-exchange="${account.exchange}">Edit</button>
                    <button class="btn btn-secondary btn-test" data-name="${account.name}" data-exchange="${account.exchange}">Test</button>
                    <button class="btn btn-danger btn-delete" data-name="${account.name}" data-exchange="${account.exchange}">Delete</button>
                </div>
            </div>
        `).join('');

        // Add event listeners to buttons
        document.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => openEditModal(btn.dataset.name, btn.dataset.exchange));
        });

        document.querySelectorAll('.btn-test').forEach(btn => {
            btn.addEventListener('click', () => testAccountConnection(btn.dataset.name, btn.dataset.exchange, btn));
        });

        document.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.name, btn.dataset.exchange));
        });

    } catch (error) {
        console.error('Failed to load accounts:', error);
        accountsList.innerHTML = '<p class="empty">Failed to load accounts</p>';
    }
}

// Open Add Account Modal
function openAddModal() {
    editingAccount = null;
    modalTitle.textContent = 'Add Account';
    accountForm.reset();
    passphraseGroup.style.display = 'none';
    formMessage.style.display = 'none';
    accountName.disabled = false;
    accountExchange.disabled = false;
    accountModal.style.display = 'flex';
}

// Open Edit Account Modal
async function openEditModal(name, exchange) {
    editingAccount = { name, exchange };
    modalTitle.textContent = 'Edit Account';
    accountName.value = name;
    accountName.disabled = true;
    accountExchange.value = exchange;
    accountExchange.disabled = true;

    // Show passphrase field for OKX
    passphraseGroup.style.display = exchange === 'OKX' ? 'block' : 'none';

    // Clear sensitive fields
    apiKey.value = '';
    apiSecret.value = '';
    apiPassphrase.value = '';

    formMessage.style.display = 'none';
    accountModal.style.display = 'flex';
}

// Close Modal
function closeModal() {
    accountModal.style.display = 'none';
    editingAccount = null;
}

// Show/hide passphrase based on exchange
accountExchange.addEventListener('change', () => {
    passphraseGroup.style.display = accountExchange.value === 'OKX' ? 'block' : 'none';
});

// Add Account Button
btnAddAccount.addEventListener('click', openAddModal);

// Close Modal
modalClose.addEventListener('click', closeModal);
accountModal.addEventListener('click', (e) => {
    if (e.target === accountModal) closeModal();
});

// Test Connection
btnTestConnection.addEventListener('click', async () => {
    const exchange = accountExchange.value;
    const name = accountName.value;

    if (!exchange || !name) {
        showFormMessage('Please fill in account name and exchange', 'error');
        return;
    }

    showFormMessage('Testing connection...', 'loading');
    btnTestConnection.disabled = true;

    try {
        const result = await invoke('test_account_connection', {
            exchange: exchange,
            accountName: name
        });
        showFormMessage(result, 'success');
    } catch (error) {
        showFormMessage(`Connection failed: ${error}`, 'error');
    } finally {
        btnTestConnection.disabled = false;
    }
});

// Save Account
accountForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = accountName.value.trim();
    const exchange = accountExchange.value;
    const key = apiKey.value.trim();
    const secret = apiSecret.value.trim();
    const passphrase = apiPassphrase.value.trim();

    if (!name || !exchange || !key || !secret) {
        showFormMessage('Please fill in all required fields', 'error');
        return;
    }

    showFormMessage('Saving account...', 'loading');

    try {
        await invoke('save_account_keys', {
            accountName: name,
            exchange: exchange,
            keys: {
                api_key: key,
                api_secret: secret,
                passphrase: passphrase || null
            }
        });

        showFormMessage('Account saved successfully!', 'success');
        setTimeout(() => {
            closeModal();
            loadAccounts();
        }, 1000);
    } catch (error) {
        showFormMessage(`Failed to save: ${error}`, 'error');
    }
});

// Test connection from card
async function testAccountConnection(name, exchange, btn) {
    const originalText = btn.textContent;
    btn.textContent = 'Testing...';
    btn.disabled = true;

    try {
        await invoke('test_account_connection', {
            exchange: exchange,
            accountName: name
        });
        showToast(`${name}: Connection successful`, 'success');
    } catch (error) {
        showToast(`${name}: ${error}`, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// Delete Modal
function openDeleteModal(name, exchange) {
    deletingAccount = { name, exchange };
    deleteAccountName.textContent = `${name} (${exchange})`;
    deleteModal.style.display = 'flex';
}

function closeDeleteModal() {
    deleteModal.style.display = 'none';
    deletingAccount = null;
}

deleteModalClose.addEventListener('click', closeDeleteModal);
btnCancelDelete.addEventListener('click', closeDeleteModal);
deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) closeDeleteModal();
});

btnConfirmDelete.addEventListener('click', async () => {
    if (!deletingAccount) return;

    btnConfirmDelete.disabled = true;
    btnConfirmDelete.textContent = 'Deleting...';

    try {
        await invoke('delete_account_keys', {
            accountName: deletingAccount.name,
            exchange: deletingAccount.exchange
        });
        showToast(`${deletingAccount.name} deleted successfully`);
        closeDeleteModal();
        loadAccounts();
    } catch (error) {
        showToast(`Failed to delete: ${error}`, 'error');
    } finally {
        btnConfirmDelete.disabled = false;
        btnConfirmDelete.textContent = 'Delete';
    }
});

// Form message helper
function showFormMessage(message, type) {
    formMessage.textContent = message;
    formMessage.className = `form-message ${type}`;
    formMessage.style.display = 'block';
}

// =====================================================
// Initialize
// =====================================================
updateStatus();

// Periodic status update (every 5 seconds)
setInterval(updateStatus, 5000);

// Load accounts when page loads if on accounts page
if (document.querySelector('.nav-item[data-page="accounts"].active')) {
    loadAccounts();
}

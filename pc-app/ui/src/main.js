import { invoke } from '@tauri-apps/api/tauri';
import { open } from '@tauri-apps/api/shell';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import { API_BASE_URL, CONNECTION_TIMEOUT, MAX_RETRIES } from './config.js';
import { Chart, registerables } from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';

// Chart.js + ChartDataLabels 즉시 등록 (ESM 통합)
Chart.register(...registerables, ChartDataLabels);
console.log('[Chart] Chart.js + ChartDataLabels 등록 완료');

// 디버깅용 전역 노출
window.invokeCmd = invoke;

// =====================================================
// Authentication State
// =====================================================
const auth = {
    accessToken: null,
    refreshToken: null,
    user: null,
    isHubMode: false,

    saveTokens(access, refresh) {
        this.accessToken = access;
        this.refreshToken = refresh;
        localStorage.setItem('bbooster_access_token', access || '');
        localStorage.setItem('bbooster_refresh_token', refresh || '');
    },

    loadTokens() {
        this.accessToken = localStorage.getItem('bbooster_access_token') || null;
        this.refreshToken = localStorage.getItem('bbooster_refresh_token') || null;
        this.isHubMode = localStorage.getItem('bbooster_hub_mode') === 'true';
    },

    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        this.user = null;
        this.isHubMode = false;
        localStorage.removeItem('bbooster_access_token');
        localStorage.removeItem('bbooster_refresh_token');
        localStorage.removeItem('bbooster_hub_mode');
    },

    setHubMode(enabled) {
        this.isHubMode = enabled;
        localStorage.setItem('bbooster_hub_mode', enabled ? 'true' : 'false');
    },

    isLoggedIn() {
        return !!this.accessToken || this.isHubMode;
    }
};

// =====================================================
// [BUG FIX] DOM 안전 조작 함수 - null 방지
// =====================================================

/**
 * 안전하게 텍스트 설정 (null 요소 방지)
 * @param {string} selector - CSS 선택자 또는 요소 ID
 * @param {string} text - 설정할 텍스트
 */
function safeSetText(selector, text) {
    const el = typeof selector === 'string'
        ? (document.querySelector(selector) || document.getElementById(selector?.replace('#', '')))
        : selector;
    if (el) el.textContent = text ?? '';
}

/**
 * 안전하게 HTML 설정 (null 요소 방지)
 * @param {string} selector - CSS 선택자 또는 요소 ID
 * @param {string} html - 설정할 HTML
 */
function safeSetHTML(selector, html) {
    const el = typeof selector === 'string'
        ? (document.querySelector(selector) || document.getElementById(selector?.replace('#', '')))
        : selector;
    if (el) el.innerHTML = html ?? '';
}

/**
 * 안전하게 요소 표시/숨김 (null 요소 방지)
 * @param {string} selector - CSS 선택자 또는 요소 ID
 * @param {boolean} visible - 표시 여부
 */
function safeSetVisible(selector, visible) {
    const el = typeof selector === 'string'
        ? (document.querySelector(selector) || document.getElementById(selector?.replace('#', '')))
        : selector;
    if (el) el.style.display = visible ? '' : 'none';
}

// =====================================================
// [BUG FIX 8] 공통 유틸리티 - 타임아웃 + 에러 처리
// =====================================================

/**
 * Tauri invoke 래퍼 - 타임아웃 + 에러 처리
 * @param {string} command - Tauri 명령어
 * @param {object} args - 인자
 * @param {number} timeout - 타임아웃 (ms)
 * @returns {Promise<any>}
 */
async function invokeWithTimeout(command, args = {}, timeout = 10000) {
    try {
        const result = await Promise.race([
            invoke(command, args),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('TIMEOUT')), timeout)
            )
        ]);
        return result;
    } catch (e) {
        console.error(`[${command}] Error:`, e);
        if (e.message === 'TIMEOUT') {
            throw new Error('요청 시간이 초과되었습니다');
        }
        throw e;
    }
}

/**
 * 로딩 상태 표시 + 타임아웃 자동 에러 전환
 * @param {HTMLElement} element - 로딩 표시할 요소
 * @param {number} maxTime - 최대 대기 시간 (ms)
 */
function showLoadingWithTimeout(element, maxTime = 15000) {
    if (!element) return null;
    element.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    const timeoutId = setTimeout(() => {
        if (element.innerHTML.includes('로딩 중')) {
            element.innerHTML = `
                <div class="error-state">
                    <p>데이터를 불러올 수 없습니다</p>
                    <button class="btn btn-sm btn-primary retry-btn">다시 시도</button>
                </div>
            `;
        }
    }, maxTime);

    return timeoutId;
}

/**
 * 에러 상태 표시
 * @param {HTMLElement} element
 * @param {string} message
 * @param {Function} retryFn - 다시 시도 콜백
 */
function showErrorState(element, message = '데이터를 불러올 수 없습니다', retryFn = null) {
    if (!element) return;
    element.innerHTML = `
        <div class="error-state">
            <p>${message}</p>
            ${retryFn ? '<button class="btn btn-sm btn-primary retry-btn">다시 시도</button>' : ''}
        </div>
    `;
    if (retryFn) {
        element.querySelector('.retry-btn')?.addEventListener('click', retryFn);
    }
}

// =====================================================
// [BUG FIX 1] 종목 검색 자동완성 공통 컴포넌트
// =====================================================

/**
 * 종목 자동완성 컴포넌트 생성
 * @param {HTMLInputElement} inputElement - 검색 입력 필드
 * @param {Function} onSelect - 종목 선택 시 콜백 ({code, name, exchange, market})
 * @param {object} options - 옵션 {exchange, category, showBadge}
 * @returns {object} - 컴포넌트 인스턴스
 */
function createSymbolAutocomplete(inputElement, onSelect, options = {}) {
    if (!inputElement) return null;

    const {
        exchange: initialExchange = 'all',
        category = 'all',
        showBadge = true,
        maxResults = 10
    } = options;

    // 상태
    let currentExchange = initialExchange;  // 변경 가능한 exchange
    let selectedSymbol = null;
    let dropdownVisible = false;
    let highlightedIndex = -1;
    let debounceTimer = null;
    let searchRequestId = 0;  // Race condition 방지용

    // 드롭다운 생성
    const wrapper = document.createElement('div');
    wrapper.className = 'autocomplete-wrapper';
    inputElement.parentNode.insertBefore(wrapper, inputElement);
    wrapper.appendChild(inputElement);

    const dropdown = document.createElement('div');
    dropdown.className = 'autocomplete-dropdown';
    dropdown.style.display = 'none';
    wrapper.appendChild(dropdown);

    // 선택 배지 (입력 필드 옆)
    const badge = document.createElement('span');
    badge.className = 'selected-symbol-badge';
    badge.style.display = 'none';
    wrapper.appendChild(badge);

    // 검색 함수 (race condition 방지)
    async function search(query) {
        if (!query || query.length < 1) {
            hideDropdown();
            return;
        }

        // 현재 요청 ID 저장 (이후 응답에서 최신 요청인지 확인)
        const thisRequestId = ++searchRequestId;

        try {
            const result = await invokeWithTimeout('search_symbols', {
                accessToken: auth.accessToken || '',
                query: query,
                exchange: currentExchange !== 'all' ? currentExchange : null
            }, 5000);

            // 이 요청이 최신 요청이 아니면 무시 (race condition 방지)
            if (thisRequestId !== searchRequestId) {
                console.log('[Search] 오래된 요청 무시:', query);
                return;
            }

            const symbols = result?.symbols || result || [];

            if (symbols.length === 0) {
                showNoResults();
                return;
            }

            renderDropdown(symbols.slice(0, maxResults));
        } catch (error) {
            // 최신 요청이 아니면 에러도 무시
            if (thisRequestId !== searchRequestId) return;
            console.error('Symbol search error:', error);
            showNoResults();
        }
    }

    // 드롭다운 렌더링
    function renderDropdown(symbols) {
        dropdown.innerHTML = symbols.map((s, idx) => `
            <div class="autocomplete-item ${idx === highlightedIndex ? 'highlighted' : ''}"
                 data-code="${s.symbol || s.code}"
                 data-name="${s.name}"
                 data-exchange="${s.exchange}"
                 data-market="${s.market || ''}">
                <span class="symbol-name">${s.name}</span>
                <span class="symbol-code">(${s.symbol || s.code})</span>
                <span class="symbol-market">${s.market || s.exchange}</span>
            </div>
        `).join('');

        dropdown.querySelectorAll('.autocomplete-item').forEach((item, idx) => {
            item.addEventListener('click', () => selectItem(idx));
            item.addEventListener('mouseenter', () => {
                highlightedIndex = idx;
                updateHighlight();
            });
        });

        showDropdown();
    }

    function showNoResults() {
        dropdown.innerHTML = '<div class="autocomplete-no-result">검색 결과가 없습니다</div>';
        showDropdown();
    }

    function showDropdown() {
        dropdown.style.display = 'block';
        dropdownVisible = true;
    }

    function hideDropdown() {
        dropdown.style.display = 'none';
        dropdownVisible = false;
        highlightedIndex = -1;
    }

    function updateHighlight() {
        dropdown.querySelectorAll('.autocomplete-item').forEach((item, idx) => {
            item.classList.toggle('highlighted', idx === highlightedIndex);
        });
    }

    function selectItem(idx) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (idx >= 0 && idx < items.length) {
            const item = items[idx];
            selectedSymbol = {
                code: item.dataset.code,
                name: item.dataset.name,
                exchange: item.dataset.exchange,
                market: item.dataset.market
            };

            inputElement.value = selectedSymbol.name;
            hideDropdown();

            // 배지 표시
            if (showBadge) {
                badge.innerHTML = `${selectedSymbol.name} ${selectedSymbol.code} <span class="badge-close">✕</span>`;
                badge.style.display = 'inline-flex';
                badge.querySelector('.badge-close').addEventListener('click', clearSelection);
            }

            // 콜백 호출
            if (onSelect) {
                onSelect(selectedSymbol);
            }
        }
    }

    function clearSelection() {
        selectedSymbol = null;
        inputElement.value = '';
        badge.style.display = 'none';
        if (onSelect) {
            onSelect(null);
        }
    }

    // 이벤트 바인딩
    console.log('[createSymbolAutocomplete] input 이벤트 바인딩:', inputElement.id);
    inputElement.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        console.log('[createSymbolAutocomplete] INPUT EVENT:', query);

        // 선택 해제
        if (selectedSymbol && query !== selectedSymbol.name) {
            selectedSymbol = null;
            badge.style.display = 'none';
        }

        // 디바운스 (200ms)
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => search(query), 300);
    });

    inputElement.addEventListener('keydown', (e) => {
        if (!dropdownVisible) return;

        const items = dropdown.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
            updateHighlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            highlightedIndex = Math.max(highlightedIndex - 1, 0);
            updateHighlight();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (highlightedIndex >= 0) {
                selectItem(highlightedIndex);
            } else if (items.length > 0) {
                selectItem(0);
            }
        } else if (e.key === 'Escape') {
            hideDropdown();
        }
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            hideDropdown();
        }
    });

    // 반환 인터페이스
    return {
        getSelected: () => selectedSymbol,
        isValid: () => !!selectedSymbol,
        clear: clearSelection,
        setExchange: (newExchange) => {
            currentExchange = newExchange || 'all';
            // 선택 초기화 + 입력 필드 초기화
            clearSelection();
        },
        getExchange: () => currentExchange,
        destroy: () => {
            wrapper.parentNode.insertBefore(inputElement, wrapper);
            wrapper.remove();
        }
    };
}

// =====================================================
// DOM Elements
// =====================================================
const loginScreen = document.getElementById('login-screen');
const appElement = document.getElementById('app');
const btnGoogleLogin = document.getElementById('btn-google-login');
const btnSkipLogin = document.getElementById('btn-skip-login');

// =====================================================
// Login Screen Functions
// =====================================================
function ensureLoginScreenVisible() {
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function showLoginScreen() {
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function hideLoginScreen() {
    if (loginScreen) loginScreen.style.cssText = 'display: none !important';
    if (appElement) appElement.style.cssText = 'display: flex !important';
}

ensureLoginScreenVisible();

// Google Login
async function loginWithGoogle() {
    try {
        await open(`${API_BASE_URL}/api/auth/google/login`);
        showToast('브라우저에서 로그인을 완료해주세요', 'info');
        startLoginPolling();
    } catch (error) {
        showToast('로그인 페이지를 열 수 없습니다', 'error');
    }
}

let loginPollingInterval = null;
function startLoginPolling() {
    if (loginPollingInterval) clearInterval(loginPollingInterval);
    let attempts = 0;
    const maxAttempts = 60;

    loginPollingInterval = setInterval(async () => {
        attempts++;
        auth.loadTokens();
        if (auth.accessToken) {
            clearInterval(loginPollingInterval);
            loginPollingInterval = null;
            await loadUserInfo();
            hideLoginScreen();
            showToast('로그인 성공', 'success');
            checkServerConnection();
            return;
        }
        if (attempts >= maxAttempts) {
            clearInterval(loginPollingInterval);
            loginPollingInterval = null;
            showToast('로그인 시간이 초과되었습니다', 'warning');
        }
    }, 2000);
}

function skipLogin() {
    auth.setHubMode(true);
    hideLoginScreen();
    updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
    showToast('허브 모드로 시작합니다', 'info');
    checkServerConnection();
}

// Email Login/Register
const emailLoginForm = document.getElementById('email-login-form');
const emailRegisterForm = document.getElementById('email-register-form');
const loginTitle = document.getElementById('login-title');
const showRegisterLink = document.getElementById('show-register');
const showLoginLink = document.getElementById('show-login');
const btnEmailLogin = document.getElementById('btn-email-login');
const btnEmailRegister = document.getElementById('btn-email-register');

function showEmailLoginForm() {
    if (emailLoginForm) emailLoginForm.style.display = 'flex';
    if (emailRegisterForm) emailRegisterForm.style.display = 'none';
    if (loginTitle) loginTitle.textContent = '로그인';
    clearAuthErrors();
}

function showEmailRegisterForm() {
    if (emailLoginForm) emailLoginForm.style.display = 'none';
    if (emailRegisterForm) emailRegisterForm.style.display = 'flex';
    if (loginTitle) loginTitle.textContent = '회원가입';
    clearAuthErrors();
}

function clearAuthErrors() {
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');
    if (loginError) loginError.textContent = '';
    if (registerError) registerError.textContent = '';
}

function showLoginError(message) {
    const el = document.getElementById('login-error');
    if (el) el.textContent = message;
}

function showRegisterError(message) {
    const el = document.getElementById('register-error');
    if (el) el.textContent = message;
}

async function handleEmailLogin() {
    const email = document.getElementById('login-email')?.value?.trim();
    const password = document.getElementById('login-password')?.value;

    if (!email || !password) {
        showLoginError('이메일과 비밀번호를 입력하세요');
        return;
    }

    if (btnEmailLogin) {
        btnEmailLogin.disabled = true;
        btnEmailLogin.textContent = '로그인 중...';
    }
    clearAuthErrors();

    try {
        const data = await invoke('login_with_email', { email, password });
        auth.saveTokens(data.access_token, data.refresh_token);
        await loadUserInfo();
        hideLoginScreen();
        showToast('로그인 성공', 'success');
        checkServerConnection();
    } catch (error) {
        showLoginError(error || '로그인에 실패했습니다');
    } finally {
        if (btnEmailLogin) {
            btnEmailLogin.disabled = false;
            btnEmailLogin.textContent = '로그인';
        }
    }
}

// 비밀번호 검증 함수 (Day14: 12자리 + 특수문자 필수)
function validatePassword(password) {
    return {
        length: password.length >= 12,
        letter: /[A-Za-z]/.test(password),
        number: /[0-9]/.test(password),
        special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]/.test(password)
    };
}

function getPasswordErrors(password) {
    const checks = validatePassword(password);
    const errors = [];
    if (!checks.length) errors.push('12자리 이상');
    if (!checks.letter) errors.push('영문자 포함');
    if (!checks.number) errors.push('숫자 포함');
    if (!checks.special) errors.push('특수문자 포함 (!@#$%^&* 등)');
    return errors;
}

async function handleEmailRegister() {
    const name = document.getElementById('register-name')?.value?.trim();
    const email = document.getElementById('register-email')?.value?.trim();
    const password = document.getElementById('register-password')?.value;
    const passwordConfirm = document.getElementById('register-password-confirm')?.value;

    if (!email || !password) {
        showRegisterError('이메일과 비밀번호를 입력하세요');
        return;
    }

    if (password !== passwordConfirm) {
        showRegisterError('비밀번호가 일치하지 않습니다');
        return;
    }

    // Day14: 강화된 비밀번호 정책
    const pwdErrors = getPasswordErrors(password);
    if (pwdErrors.length > 0) {
        showRegisterError('비밀번호 조건: ' + pwdErrors.join(', '));
        return;
    }

    if (btnEmailRegister) {
        btnEmailRegister.disabled = true;
        btnEmailRegister.textContent = '회원가입 중...';
    }
    clearAuthErrors();

    try {
        const data = await invoke('register_with_email', { email, password, name: name || null });
        auth.saveTokens(data.access_token, data.refresh_token);
        await loadUserInfo();
        hideLoginScreen();
        showToast('회원가입 및 로그인 성공', 'success');
        checkServerConnection();
    } catch (error) {
        showRegisterError(error || '회원가입에 실패했습니다');
    } finally {
        if (btnEmailRegister) {
            btnEmailRegister.disabled = false;
            btnEmailRegister.textContent = '회원가입';
        }
    }
}

showRegisterLink?.addEventListener('click', showEmailRegisterForm);
showLoginLink?.addEventListener('click', showEmailLoginForm);
btnEmailLogin?.addEventListener('click', handleEmailLogin);
btnEmailRegister?.addEventListener('click', handleEmailRegister);
document.getElementById('login-password')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleEmailLogin(); });
document.getElementById('register-password-confirm')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleEmailRegister(); });

// Day14: 비밀번호 실시간 검증
document.getElementById('register-password')?.addEventListener('input', (e) => {
    const password = e.target.value;
    const checks = validatePassword(password);
    document.getElementById('pwd-length').textContent = (checks.length ? '✅' : '❌') + ' 12자리 이상';
    document.getElementById('pwd-letter').textContent = (checks.letter ? '✅' : '❌') + ' 영문자 포함';
    document.getElementById('pwd-number').textContent = (checks.number ? '✅' : '❌') + ' 숫자 포함';
    document.getElementById('pwd-special').textContent = (checks.special ? '✅' : '❌') + ' 특수문자 포함';
});

async function loadUserInfo() {
    if (!auth.accessToken) return;
    try {
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        updateUserUI(auth.user);

        // Show admin menus if admin
        if (user.role === 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        }
    } catch (error) {
        console.error('Failed to load user info:', error);
        if (String(error).includes('401') || String(error).includes('Unauthorized')) {
            await refreshAuthToken();
        }
    }
}

async function refreshAuthToken() {
    const success = await tryRefreshToken();
    if (!success) {
        showLoginScreen();
    }
}

function updateUserUI(user) {
    const badge = document.getElementById('subscription-badge');
    const badgeText = document.getElementById('subscription-text');
    const userName = document.getElementById('user-name');
    const userAvatar = document.getElementById('user-avatar');

    const isAdmin = user.role === 'admin';

    // Update user name (admin 표시 포함)
    if (userName) {
        const displayName = user.name || user.email?.split('@')[0] || '사용자';
        userName.textContent = isAdmin ? `${displayName} (Admin)` : displayName;
    }

    // Update avatar (first letter or emoji, admin은 특별 표시)
    if (userAvatar) {
        if (isAdmin) {
            userAvatar.textContent = '👑';
        } else {
            const name = user.name || user.email || '사용자';
            userAvatar.textContent = name.charAt(0).toUpperCase();
        }
    }

    // Update subscription badge
    // [BUG FIX 5] admin이면 Admin 배지, 아니면 요금제 배지
    if (isAdmin) {
        if (badge) badge.className = 'subscription-badge admin';
        if (badgeText) badgeText.textContent = 'Admin';
    } else {
        const planDisplayMap = {
            'premium': { class: 'premium', text: 'Premium' },
            'pro': { class: 'pro', text: 'Pro' },
            'standard': { class: 'standard', text: 'Standard' },
            'hub': { class: 'standard', text: 'Standard' },
            'starter': { class: 'starter', text: 'Starter' },
            'free': { class: 'starter', text: 'Starter' },
        };
        const planInfo = planDisplayMap[user.plan] || planDisplayMap['starter'];
        if (badge) badge.className = `subscription-badge ${planInfo.class}`;
        if (badgeText) badgeText.textContent = planInfo.text;
    }

    // Show admin menu if admin
    if (isAdmin) {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        document.getElementById('admin-menu-group')?.style.setProperty('display', 'block');
    } else {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
    }
}

function logout() {
    localStorage.removeItem('bbooster_access_token');
    localStorage.removeItem('bbooster_refresh_token');
    localStorage.removeItem('bbooster_hub_mode');
    window.location.reload();
}

async function initAuth() {
    ensureLoginScreenVisible();
    auth.loadTokens();

    if (auth.isHubMode) {
        hideLoginScreen();
        updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
        return true;
    }

    if (!auth.accessToken) {
        return false;
    }

    try {
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        updateUserUI(auth.user);
        if (user.role === 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        }
        hideLoginScreen();
        return true;
    } catch (error) {
        const refreshed = await tryRefreshToken();
        if (refreshed) {
            hideLoginScreen();
            return true;
        }
    }

    auth.clearTokens();
    return false;
}

async function tryRefreshToken() {
    if (!auth.refreshToken) return false;
    try {
        const tokens = await invoke('refresh_auth_token', { refreshToken: auth.refreshToken });
        auth.saveTokens(tokens.access_token, tokens.refresh_token);
        await loadUserInfo();
        return true;
    } catch (error) {
        console.error('Token refresh failed:', error);
    }
    auth.clearTokens();
    return false;
}

btnGoogleLogin?.addEventListener('click', loginWithGoogle);
btnSkipLogin?.addEventListener('click', skipLogin);

// =====================================================
// Navigation - New Collapsible Sidebar Structure
// =====================================================
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const mainWrapper = document.querySelector('.main-wrapper');
const pageTitle = document.getElementById('page-title');

const pageTitles = {
    home: '홈',
    'tv-connect': '트레이딩뷰 연결',
    'premium-strategy': '프리미엄 전략',
    // 종목검색
    screener: '종목검색',
    // BBooster AI
    'bbooster-ai': 'BBooster AI',
    // 시장분석
    'market-kr': '국내시장',
    'market-us': '해외시장',
    'market-etf': 'ETF',
    'market-crypto': '코인시장',
    // 종목분석
    'stock-kr': '국내주식',
    'stock-us': '해외주식',
    'stock-etf': 'ETF 분석',
    'stock-crypto': '코인분석',
    // 기타
    watchlist: '관심종목',
    symbols: '종목분석', // legacy
    'market-overview': '시장현황', // legacy
    'sector-analysis': '업종분석', // legacy
    'stock-ranking': '종목순위', // legacy
    'featured-stocks': '특징주', // legacy
    'market-events': '이벤트일정', // legacy
    accounts: '계정관리',
    notifications: '알림설정',
    'app-info': '앱정보',
    'admin-users': '사용자관리',
    'admin-system': '시스템상태'
};

// Sidebar Toggle (Collapse/Expand)
sidebarToggle?.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    if (mainWrapper) {
        mainWrapper.style.marginLeft = sidebar.classList.contains('collapsed') ? '60px' : '240px';
    }
    localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
});

// Restore sidebar state
if (localStorage.getItem('sidebar_collapsed') === 'true') {
    sidebar?.classList.add('collapsed');
    if (mainWrapper) mainWrapper.style.marginLeft = '60px';
}

// Accordion Submenu Toggle
document.querySelectorAll('.nav-parent').forEach(parent => {
    parent.addEventListener('click', (e) => {
        e.preventDefault();
        const group = parent.closest('.nav-group');
        if (group) {
            // Close other groups
            document.querySelectorAll('.nav-group').forEach(g => {
                if (g !== group) g.classList.remove('open');
            });
            group.classList.toggle('open');
        }
    });
});

// Nav Item Click (Page Navigation)
document.querySelectorAll('.nav-item[data-page]').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        if (page) navigateTo(page);
    });
});

window.navigateTo = function(page) {
    // Update active state
    document.querySelectorAll('.nav-item').forEach(nav => {
        nav.classList.toggle('active', nav.dataset.page === page);
    });

    // Open parent group if navigating to submenu item
    const activeItem = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (activeItem) {
        const parentGroup = activeItem.closest('.nav-group');
        if (parentGroup) parentGroup.classList.add('open');
    }

    // Update page title
    if (pageTitle) pageTitle.textContent = pageTitles[page] || page;

    // Show target page
    document.querySelectorAll('.page-content').forEach(pageEl => {
        pageEl.style.display = 'none';
    });
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Update URL hash
    window.location.hash = page;

    // Page-specific initialization
    if (page === 'home') loadHomePage();
    else if (page === 'tv-connect') loadTVConnectPage();
    else if (page === 'symbols') loadSymbolsPage();
    else if (page === 'premium-strategy') loadPremiumStrategyPage();
    // 종목검색 (Phase 7)
    else if (page === 'screener') loadScreener();
    // BBooster AI (Phase 11)
    else if (page === 'bbooster-ai') loadBBoosterAI();
    // 시장분석 (신규)
    else if (page === 'market-kr') loadMarketKr();
    else if (page === 'market-us') loadMarketUs();
    else if (page === 'market-etf') loadMarketEtf();
    else if (page === 'market-crypto') loadMarketCrypto();
    // 종목분석 (신규)
    else if (page === 'stock-kr') loadStockKr();
    else if (page === 'stock-us') loadStockUs();
    else if (page === 'stock-etf') loadStockEtf();
    else if (page === 'stock-crypto') loadStockCrypto();
    // 관심종목 (신규)
    else if (page === 'watchlist') loadWatchlist();
    // 기존 (legacy)
    else if (page === 'market-overview') loadMarketOverview();
    else if (page === 'sector-analysis') loadSectorAnalysis();
    else if (page === 'stock-ranking') loadStockRanking();
    else if (page === 'featured-stocks') loadFeaturedStocks();
    else if (page === 'market-events') loadMarketEvents();
    else if (page === 'accounts') loadAccountsPage();
    else if (page === 'app-info') loadAppInfoPage();
    else if (page === 'admin-users') loadAdminUsersPage();
    else if (page === 'admin-system') loadAdminSystemPage();
};

// Handle URL hash navigation
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.slice(1);
    if (hash && pageTitles[hash]) {
        navigateTo(hash);
    }
});

// Sidebar Logout Button
document.getElementById('sidebar-logout-btn')?.addEventListener('click', logout);

// =====================================================
// Toast Notifications
// =====================================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// =====================================================
// Connection Check
// =====================================================
let isConnected = false;
let retryCount = 0;

async function checkServerConnection() {
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingMessage = document.getElementById('loading-message');
    const retryBtn = document.getElementById('btn-retry-connection');

    if (loadingOverlay) loadingOverlay.style.display = 'flex';
    if (loadingMessage) loadingMessage.textContent = '서버 연결 중...';
    if (retryBtn) retryBtn.style.display = 'none';

    try {
        const result = await invoke('check_server_health');
        if (result.ok) {
            isConnected = true;
            retryCount = 0;
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            updateServerStatus(true);
            loadHomePage();
            return true;
        }
        throw new Error(result.message || 'Server not responding');
    } catch (error) {
        console.error('Connection failed:', error);
        isConnected = false;
        retryCount++;

        if (loadingMessage) {
            loadingMessage.textContent = '서버에 연결할 수 없습니다.\n네트워크를 확인해주세요.';
        }
        if (retryBtn) retryBtn.style.display = 'block';

        if (retryCount < MAX_RETRIES) {
            if (loadingMessage) {
                loadingMessage.textContent = `연결 재시도 중... (${retryCount}/${MAX_RETRIES})`;
            }
            setTimeout(checkServerConnection, 3000);
        }
        return false;
    }
}

document.getElementById('btn-retry-connection')?.addEventListener('click', () => {
    retryCount = 0;
    checkServerConnection();
});

function updateServerStatus(connected) {
    const serverStatus = document.getElementById('server-status');
    const lightServer = document.getElementById('light-server');

    if (connected) {
        if (serverStatus) serverStatus.textContent = '서버: 연결됨';
        if (lightServer) lightServer.className = 'status-light green';
    } else {
        if (serverStatus) serverStatus.textContent = '서버: 오프라인';
        if (lightServer) lightServer.className = 'status-light red';
    }
}

// =====================================================
// Home Page (PHASE 3) - Portfolio Dashboard
// =====================================================
let allocationChart = null;

async function loadHomePage() {
    // Load server status
    try {
        const status = await invoke('get_server_status');
        updateServerStatus(status.running);
    } catch (e) {
        console.error('Failed to get server status:', e);
    }

    // Load portfolio data
    await loadPortfolioSummary();
    await loadHoldings();  // 자산배분 차트도 함께 업데이트
    await loadActiveStrategies();
    await loadRecentTrades();
}

async function loadPortfolioSummary() {
    try {
        if (!auth.accessToken) {
            updateSummaryCards({ total_assets_formatted: '₩0', total_profit_rate: 0, daily_change_formatted: '₩0', daily_change_rate: 0, active_strategies: 0 });
            return;
        }

        const summary = await invoke('get_portfolio_summary', { accessToken: auth.accessToken });
        updateSummaryCards(summary);
    } catch (e) {
        console.error('Failed to load portfolio summary:', e);
        updateSummaryCards({ total_assets_formatted: '₩0', total_profit_rate: 0, daily_change_formatted: '₩0', daily_change_rate: 0, active_strategies: 0 });
    }
}

function updateSummaryCards(summary) {
    const totalAssets = document.getElementById('total-assets');
    const totalProfit = document.getElementById('total-profit');
    const dailyChange = document.getElementById('daily-change');
    const activeStrategies = document.getElementById('active-strategies-count');

    if (totalAssets) totalAssets.textContent = summary.total_assets_formatted || '₩0';

    if (totalProfit) {
        const rate = summary.total_profit_rate || 0;
        totalProfit.textContent = (rate >= 0 ? '+' : '') + rate.toFixed(2) + '%';
        totalProfit.className = 'summary-value ' + (rate >= 0 ? 'profit' : 'loss');
    }

    if (dailyChange) {
        const change = summary.daily_change_formatted || '₩0';
        const rate = summary.daily_change_rate || 0;
        dailyChange.textContent = `${change} (${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%)`;
        dailyChange.className = 'summary-value ' + (rate >= 0 ? 'profit' : 'loss');
    }

    if (activeStrategies) activeStrategies.textContent = (summary.active_strategies || 0) + '개';

    // 수익률 기간 상태 업데이트
    if (summary.first_snapshot_date && typeof profitPeriodState !== 'undefined') {
        profitPeriodState.firstSnapshotDate = summary.first_snapshot_date;
    }

    // 자산배분 도넛차트 업데이트 (summary.allocation 사용) - 5개 카테고리
    if (summary.allocation) {
        const alloc = summary.allocation;
        console.log('[Summary] Allocation from API:', alloc);

        // 1. Chart.js 도넛차트 업데이트 (5개 카테고리)
        const allocData = [
            alloc.domestic || 0,
            alloc.foreign || 0,
            alloc.crypto || 0,
            alloc.cash_krw || 0,
            alloc.cash_usd || 0
        ];
        initAllocationChart(allocData);

        // 2. 범례 퍼센트 텍스트 업데이트 (5개)
        const allocDomestic = document.getElementById('alloc-domestic');
        const allocForeign = document.getElementById('alloc-foreign');
        const allocCrypto = document.getElementById('alloc-crypto');
        const allocCashKrw = document.getElementById('alloc-cash-krw');
        const allocCashUsd = document.getElementById('alloc-cash-usd');

        if (allocDomestic) allocDomestic.textContent = (alloc.domestic || 0) + '%';
        if (allocForeign) allocForeign.textContent = (alloc.foreign || 0) + '%';
        if (allocCrypto) allocCrypto.textContent = (alloc.crypto || 0) + '%';
        if (allocCashKrw) allocCashKrw.textContent = (alloc.cash_krw || 0) + '%';
        if (allocCashUsd) allocCashUsd.textContent = (alloc.cash_usd || 0) + '%';

        // 3. 테이블 퍼센트 업데이트 (5개)
        const domesticPct = document.getElementById('alloc-domestic-pct');
        const foreignPct = document.getElementById('alloc-foreign-pct');
        const cryptoPct = document.getElementById('alloc-crypto-pct');
        const cashKrwPct = document.getElementById('alloc-cash-krw-pct');
        const cashUsdPct = document.getElementById('alloc-cash-usd-pct');

        if (domesticPct) domesticPct.textContent = (alloc.domestic || 0) + '%';
        if (foreignPct) foreignPct.textContent = (alloc.foreign || 0) + '%';
        if (cryptoPct) cryptoPct.textContent = (alloc.crypto || 0) + '%';
        if (cashKrwPct) cashKrwPct.textContent = (alloc.cash_krw || 0) + '%';
        if (cashUsdPct) cashUsdPct.textContent = (alloc.cash_usd || 0) + '%';

        // 4. 테이블 금액 업데이트 (5개)
        const domesticValue = document.getElementById('alloc-domestic-value');
        const foreignValue = document.getElementById('alloc-foreign-value');
        const cryptoValue = document.getElementById('alloc-crypto-value');
        const cashKrwValue = document.getElementById('alloc-cash-krw-value');
        const cashUsdValue = document.getElementById('alloc-cash-usd-value');

        if (domesticValue) domesticValue.textContent = '₩' + Math.round(alloc.domestic_value || 0).toLocaleString('ko-KR');
        if (foreignValue) foreignValue.textContent = '$' + (alloc.foreign_value || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        if (cryptoValue) cryptoValue.textContent = '$' + (alloc.crypto_value ? alloc.crypto_value / 1450 : 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        if (cashKrwValue) cashKrwValue.textContent = '₩' + Math.round(alloc.cash_krw_value || 0).toLocaleString('ko-KR');
        if (cashUsdValue) cashUsdValue.textContent = '$' + (alloc.cash_usd_value || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

        console.log('[Summary] Updated allocation legend & table (5 categories)');
    }
}

function initAllocationChart(allocData) {
    const ctx = document.getElementById('allocation-chart');
    if (!ctx) return;

    if (allocationChart) allocationChart.destroy();

    // Default allocation (5 categories: 국내주식, 해외주식, 암호화폐, 현금(원화), 현금(달러))
    const data = allocData || [0, 0, 0, 0, 0];

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['국내주식', '해외주식', '암호화폐', '현금(원화)', '현금(달러)'],
            datasets: [{
                data: data,
                backgroundColor: ['#3B82F6', '#8B5CF6', '#F59E0B', '#6B7280', '#9CA3AF'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: { legend: { display: false } }
        }
    });
}

// 전역 holdings 데이터 저장
let _holdingsData = [];

async function loadHoldings() {
    const tbody = document.getElementById('holdings-tbody');
    if (!tbody) return;

    try {
        let holdings = [];
        if (auth.accessToken) {
            holdings = await invoke('get_holdings', { accessToken: auth.accessToken });
        }

        console.log('[Holdings DEBUG] Raw holdings count:', holdings?.length);
        console.log('[Holdings DEBUG] First item:', holdings?.[0]);

        // currency 필드가 없으면 exchange 기반으로 추가
        holdings = holdings.map(h => {
            if (!h.currency) {
                const ex = (h.exchange || '').toUpperCase();
                h.currency = ['UPBIT', 'KIS_KR', 'KIS', 'KIWOOM'].includes(ex) ? 'KRW' : 'USD';
            }
            return h;
        });

        _holdingsData = holdings;  // 전역 저장

        renderHoldings();

        // 자산배분은 loadPortfolioSummary에서 summary.allocation으로 업데이트됨
        // 여기서는 도넛차트를 업데이트하지 않음 (덮어쓰기 방지)
        console.log('[Holdings] Loaded', holdings?.length, 'items. Donut chart updated by summary API.');

    } catch (e) {
        console.error('Failed to load holdings:', e);
    }
}

/**
 * 보유자산 기반 자산배분 계산
 * @returns [국내주식%, 해외주식%, 암호화폐%, 현금%]
 */
function calculateAllocation(holdings) {
    console.log('[Allocation DEBUG] holdings count:', holdings?.length);
    console.log('[Allocation DEBUG] holdings raw:', JSON.stringify(holdings, null, 2));

    if (!holdings || holdings.length === 0) {
        return [0, 0, 0, 100];  // 데이터 없으면 현금 100%
    }

    let krStock = 0;      // 국내주식
    let usStock = 0;      // 해외주식
    let crypto = 0;       // 암호화폐
    let cash = 0;         // 현금

    // 스테이블코인 목록
    const stablecoins = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD'];
    // KRW 거래소 목록
    const krwExchanges = ['UPBIT', 'KIS_KR', 'KIS', 'KIWOOM'];

    holdings.forEach(h => {
        const exchange = (h.exchange || '').toUpperCase();
        const symbol = (h.symbol || '').toUpperCase();
        // currency가 없으면 exchange로 판단
        const currency = h.currency ? h.currency.toUpperCase() : (krwExchanges.includes(exchange) ? 'KRW' : 'USD');

        // 평가금액 계산 - 여러 소스에서 시도
        let value = 0;
        if (h.current_price && h.quantity) {
            value = h.current_price * h.quantity;
        } else if (h.value && h.value > 0) {
            value = h.value;
        } else if (h.value_krw && h.value_krw > 0) {
            value = h.value_krw;
        } else if (h.value_usd && h.value_usd > 0) {
            value = h.value_usd;
        }

        // USD → KRW 변환 (환율 1450원)
        let valueKRW = value;
        if (currency === 'USD') {
            valueKRW = value * 1450;
        }

        console.log(`[Alloc] ${symbol}: exchange=${exchange}, currency=${currency}, price=${h.current_price}, qty=${h.quantity}, value=${value}, valueKRW=${valueKRW}`);

        // 거래소별 분류
        if (exchange === 'KIS_KR' || exchange === 'KIS') {
            if (symbol === 'KRW' || h.name === '예수금') {
                cash += valueKRW;
            } else {
                krStock += valueKRW;
            }
        } else if (exchange === 'KIS_US') {
            usStock += valueKRW;
        } else if (['OKX', 'BINANCE', 'BYBIT', 'UPBIT'].includes(exchange)) {
            if (stablecoins.includes(symbol) || symbol === 'KRW') {
                cash += valueKRW;
            } else {
                crypto += valueKRW;
            }
        }
    });

    // 총액 계산
    const total = krStock + usStock + crypto + cash;
    console.log(`[Allocation] 국내주식: ₩${krStock.toLocaleString()}, 해외주식: ₩${usStock.toLocaleString()}, 암호화폐: ₩${crypto.toLocaleString()}, 현금: ₩${cash.toLocaleString()}, 총: ₩${total.toLocaleString()}`);

    if (total <= 0) {
        return [0, 0, 0, 100];
    }

    // 비율 계산 (소수점 1자리)
    const krStockPct = Math.round((krStock / total) * 1000) / 10;
    const usStockPct = Math.round((usStock / total) * 1000) / 10;
    const cryptoPct = Math.round((crypto / total) * 1000) / 10;
    const cashPct = Math.round((100 - krStockPct - usStockPct - cryptoPct) * 10) / 10;

    console.log(`[Allocation] 국내주식: ${krStockPct}%, 해외주식: ${usStockPct}%, 암호화폐: ${cryptoPct}%, 현금: ${cashPct}%`);

    return [krStockPct, usStockPct, cryptoPct, cashPct];
}

function renderHoldings() {
    const tbody = document.getElementById('holdings-tbody');
    if (!tbody) return;

    const filterSelect = document.getElementById('holdings-exchange-filter');
    const selectedExchange = filterSelect?.value || 'all';

    // 필터 적용
    let filtered = _holdingsData;
    if (selectedExchange !== 'all') {
        filtered = _holdingsData.filter(h => h.exchange.toLowerCase() === selectedExchange.toLowerCase());
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="8">
                    <div class="empty-state">
                        <p>${selectedExchange === 'all' ? '연결된 계정이 없습니다.' : `${selectedExchange.toUpperCase()} 자산이 없습니다.`}</p>
                        <p>설정 → 계정관리에서 거래소를 연결하세요.</p>
                        <button class="btn btn-primary" onclick="navigateTo('accounts')">계정 연결하기</button>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    // 거래소별 그룹화
    const byExchange = {};
    filtered.forEach(h => {
        const ex = h.exchange.toUpperCase();
        if (!byExchange[ex]) byExchange[ex] = [];
        byExchange[ex].push(h);
    });

    // 거래소별 정렬 (수익률 높은 순)
    Object.keys(byExchange).forEach(ex => {
        byExchange[ex].sort((a, b) => (b.profit_rate || 0) - (a.profit_rate || 0));
    });

    // 테이블 렌더링
    let html = '';
    Object.keys(byExchange).sort().forEach(ex => {
        const assets = byExchange[ex];
        const subtotal = assets.reduce((sum, h) => sum + (h.current_price * h.quantity || 0), 0);

        // 거래소 헤더
        if (selectedExchange === 'all' && Object.keys(byExchange).length > 1) {
            // 거래소별 통화 확인
            const isKRWExchange = ['UPBIT', 'KIS_KR', 'KIS'].includes(ex);
            const subtotalFormatted = isKRWExchange
                ? '₩' + Math.round(subtotal).toLocaleString('ko-KR')
                : '$' + subtotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            html += `<tr class="exchange-group-header"><td colspan="8"><strong>${ex}</strong> (${assets.length}개 자산, ${subtotalFormatted})</td></tr>`;
        }

        assets.forEach(h => {
            // 예수금/현금 특별 처리
            const isDeposit = h.symbol === 'KRW' || h.name === '예수금';

            if (isDeposit) {
                // 예수금 전용 표시
                const depositAmount = h.quantity || h.value_krw || 0;
                html += `
                    <tr>
                        <td title="예수금">${h.name || '예수금'}</td>
                        <td><span class="exchange-badge ${h.exchange.toLowerCase()}">${h.exchange}</span></td>
                        <td>-</td>
                        <td>-</td>
                        <td>-</td>
                        <td style="color: #F59E0B; font-weight: 600;">₩${Math.round(depositAmount).toLocaleString('ko-KR')}</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>
                `;
            } else {
                // 일반 자산 표시
                const currency = h.currency || h.exchange;
                const avgPrice = h.avg_price > 0 ? formatCurrency(h.avg_price, currency) : '-';
                const currentPrice = h.current_price > 0 ? formatCurrency(h.current_price, currency) : '-';
                // 평가액 계산: 현재가 × 보유수량
                const evalAmount = h.current_price > 0 && h.quantity > 0
                    ? formatCurrency(h.current_price * h.quantity, currency)
                    : '-';
                const profitLoss = h.avg_price > 0 ? formatProfitLoss(h.profit_loss, currency) : '-';
                const profitRate = h.avg_price > 0 ? `${h.profit_rate >= 0 ? '+' : ''}${h.profit_rate.toFixed(2)}%` : '-';
                const profitClass = h.profit_rate >= 0 ? 'profit' : 'loss';

                html += `
                    <tr class="clickable-row" data-symbol="${h.symbol}" data-exchange="${h.exchange}" data-name="${h.name || h.symbol}" style="cursor: pointer;">
                        <td title="${h.name || h.symbol}">${h.symbol}</td>
                        <td><span class="exchange-badge ${h.exchange.toLowerCase()}">${h.exchange}</span></td>
                        <td>${formatQuantity(h.quantity)}</td>
                        <td>${avgPrice}</td>
                        <td>${currentPrice}</td>
                        <td style="color: #F59E0B; font-weight: 600;">${evalAmount}</td>
                        <td class="${h.avg_price > 0 ? profitClass : ''}">${profitLoss}</td>
                        <td class="${h.avg_price > 0 ? profitClass : ''}">${profitRate}</td>
                    </tr>
                `;
            }
        });
    });

    tbody.innerHTML = html;

    // 클릭 이벤트 핸들러 추가 (보유자산 → 거래내역)
    tbody.querySelectorAll('.clickable-row').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            const exchange = row.dataset.exchange;
            const name = row.dataset.name;
            showAssetTradesModal(symbol, exchange, name);
        });
    });
}

// 자산 거래내역 모달 표시
async function showAssetTradesModal(symbol, exchange, name) {
    const modal = document.getElementById('asset-trades-modal');
    const title = document.getElementById('asset-trades-title');
    const exchangeBadge = document.getElementById('asset-trades-exchange');
    const tbody = document.getElementById('asset-trades-tbody');

    if (!modal) return;

    title.textContent = `${name || symbol} 거래내역`;
    exchangeBadge.textContent = exchange;
    exchangeBadge.className = `exchange-badge ${exchange.toLowerCase()}`;

    // 로딩 표시
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;">거래내역 로딩 중...</td></tr>';
    modal.style.display = 'flex';

    try {
        // 해당 종목의 거래내역 조회
        const trades = await invoke('get_asset_trades', {
            accessToken: auth.accessToken,
            symbol: symbol,
            exchange: exchange,
            limit: 100
        });

        if (!trades || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #9CA3AF;">거래내역이 없습니다.</td></tr>';
            return;
        }

        // 누적 수익 계산
        let cumulative = 0;
        let html = '';

        trades.forEach(t => {
            const side = t.side?.toUpperCase() === 'BUY' ? '매수' : '매도';
            const sideClass = t.side?.toUpperCase() === 'BUY' ? 'profit' : 'loss';
            const date = t.executed_at ? new Date(t.executed_at).toLocaleDateString('ko-KR') : '-';
            const quantity = formatQuantity(t.quantity || 0);
            const amount = formatCurrency(t.total_amount || (t.price * t.quantity) || 0, exchange);
            const profit = t.profit_loss || 0;
            const profitRate = t.profit_rate || 0;
            cumulative += profit;

            const profitClass = profit >= 0 ? 'profit' : 'loss';
            const profitStr = profit !== 0 ? formatProfitLoss(profit, exchange) : '-';
            const profitRateStr = profitRate !== 0 ? `${profitRate >= 0 ? '+' : ''}${profitRate.toFixed(2)}%` : '-';
            const cumulativeStr = formatProfitLoss(cumulative, exchange);

            html += `
                <tr>
                    <td>${t.strategy_name || '-'}</td>
                    <td class="${sideClass}">${side}</td>
                    <td>${date}</td>
                    <td>${quantity}</td>
                    <td>${amount}</td>
                    <td class="${profitClass}">${profitStr}</td>
                    <td class="${profitClass}">${profitRateStr}</td>
                    <td class="${cumulative >= 0 ? 'profit' : 'loss'}">${cumulativeStr}</td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    } catch (e) {
        console.error('Failed to load asset trades:', e);
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #EF4444;">거래내역을 불러올 수 없습니다.</td></tr>';
    }
}

// 자산 거래내역 모달 닫기
document.getElementById('asset-trades-modal-close')?.addEventListener('click', () => {
    document.getElementById('asset-trades-modal').style.display = 'none';
});

document.getElementById('asset-trades-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'asset-trades-modal') {
        e.target.style.display = 'none';
    }
});

function formatUSD(value) {
    return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// 거래소 필터 이벤트
document.getElementById('holdings-exchange-filter')?.addEventListener('change', renderHoldings);

async function loadActiveStrategies() {
    const tbody = document.getElementById('strategies-tbody');
    if (!tbody) return;

    try {
        let strategies = [];
        if (auth.accessToken) {
            strategies = await invoke('get_active_strategies', { accessToken: auth.accessToken });
        }
        // API가 { strategies: [...] } 또는 [...] 형태일 수 있음
        if (strategies.strategies) strategies = strategies.strategies;

        if (!strategies || strategies.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="6">
                        <div class="empty-state">
                            <p>활성 전략이 없습니다.</p>
                            <p>전략설정에서 전략을 추가하세요.</p>
                            <button class="btn btn-primary" onclick="navigateTo('tv-connect')">전략 추가하기</button>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = strategies.map(s => {
            const isRunning = s.status === 'running';
            const statusClass = isRunning ? 'running' : 'paused';
            const statusText = isRunning ? '실행중' : '일시정지';
            const rowClass = isRunning ? '' : ' class="paused-row"';
            // 전략명에서 특수문자 이스케이프
            const safeName = s.name.replace(/'/g, "\\'").replace(/"/g, '&quot;');

            return `
            <tr${rowClass}>
                <td class="strategy-name-cell" title="${s.name}">${s.name}</td>
                <td class="strategy-symbol-cell">${s.symbol}</td>
                <td>${s.exchange}</td>
                <td class="strategy-trades-cell">${s.trades_today}건</td>
                <td><span class="strategy-status-badge ${statusClass}">${statusText}</span></td>
                <td class="strategy-actions-cell">
                    ${isRunning
                        ? `<button class="btn-action btn-pause" onclick="toggleAsset(${s.id}, '${safeName}')">정지</button>`
                        : `<button class="btn-action btn-resume" onclick="toggleAsset(${s.id}, '${safeName}')">재개</button>`
                    }
                    <button class="btn-action btn-delete" onclick="deleteAsset(${s.id}, '${safeName}')">삭제</button>
                </td>
            </tr>
            `;
        }).join('');

    } catch (e) {
        console.error('Failed to load active strategies:', e);
    }
}

async function toggleAsset(assetId, name) {
    console.log('[toggleAsset] called with assetId:', assetId, 'name:', name);
    try {
        console.log('[toggleAsset] invoking toggle_asset with assetId:', assetId);
        // Tauri는 camelCase → snake_case 자동 변환 (strategyId → strategy_id 패턴 따름)
        const res = await invoke('toggle_asset', { accessToken: auth.accessToken, assetId: assetId });
        console.log('[toggleAsset] response:', res);
        const statusText = res.is_active ? '재개' : '일시정지';
        showToast(`${name} 전략이 ${statusText}되었습니다.`);
        await loadActiveStrategies();
    } catch (e) {
        console.error('[toggleAsset] error:', e);
        showToast(`전략 변경 실패: ${e}`, 'error');
    }
}

async function deleteAsset(assetId, name) {
    if (!confirm(`"${name}" 전략을 삭제하시겠습니까?\n삭제 후 복구할 수 없습니다.`)) return;
    console.log('[deleteAsset] called with assetId:', assetId);
    try {
        const res = await invoke('delete_asset', { accessToken: auth.accessToken, assetId: assetId });
        console.log('[deleteAsset] response:', res);
        showToast(`${name} 전략이 삭제되었습니다.`);
        await loadActiveStrategies();
    } catch (e) {
        console.error('[deleteAsset] error:', e);
        showToast(`전략 삭제 실패: ${e}`, 'error');
    }
}

// Vite 모듈 스코프 문제 해결: 인라인 onclick에서 접근 가능하도록 window에 등록
window.toggleAsset = toggleAsset;
window.deleteAsset = deleteAsset;

// =====================================================
// 거래 내역 로드
// =====================================================
let tradesOffset = 0;
const TRADES_LIMIT = 10;

async function loadRecentTrades(append = false) {
    const tbody = document.getElementById('trades-tbody');
    const moreBtn = document.getElementById('trades-more');
    if (!tbody) return;

    try {
        if (!append) tradesOffset = 0;
        if (!auth.accessToken) return;

        const data = await invoke('get_trade_history', {
            accessToken: auth.accessToken,
            exchange: null,
            symbol: null,
            limit: TRADES_LIMIT,
            offset: tradesOffset
        });
        const trades = data.trades || [];
        const total = data.total || trades.length;

        if (trades.length === 0 && !append) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="6">
                        <div class="empty-state"><p>거래 내역이 없습니다.</p></div>
                    </td>
                </tr>
            `;
            if (moreBtn) moreBtn.style.display = 'none';
            return;
        }

        const rowsHtml = trades.map(trade => {
            const side = (trade.side || '').toLowerCase();
            const sideText = side.includes('buy') ? '매수' : side.includes('sell') ? '매도' : trade.side || '-';
            const sideClass = side.includes('buy') ? 'buy' : 'sell';

            const status = (trade.status || 'filled').toLowerCase();
            const statusText = status === 'filled' ? '체결' :
                              status === 'failed' ? '실패' :
                              status === 'skipped' ? '스킵' :
                              status === 'sent' ? '전송' : status;
            const statusClass = status === 'filled' ? 'filled' :
                               status === 'failed' || status === 'skipped' ? 'failed' : 'pending';

            const qty = trade.quantity || 0;
            const price = trade.price || 0;
            const time = trade.executed_at ? new Date(trade.executed_at).toLocaleString('ko-KR') : '-';

            const errorMsg = trade.submit_err || trade.reason_text || trade.reason_code || '';
            const hasError = (status === 'failed' || status === 'skipped') && errorMsg;

            let html = `
                <tr>
                    <td>${time}</td>
                    <td style="font-family: monospace;">${trade.symbol || '-'}</td>
                    <td><span class="trade-side ${sideClass}">${sideText}</span></td>
                    <td>${formatQuantity(qty)}</td>
                    <td>${price > 0 ? formatCurrency(price, trade.exchange) : '-'}</td>
                    <td><span class="trade-status ${statusClass}">${statusText}</span></td>
                </tr>`;

            if (hasError) {
                html += `
                <tr class="trade-error-row">
                    <td colspan="6">
                        <div class="trade-error-msg">
                            <span>⚠️</span>
                            <span>사유: ${errorMsg}</span>
                        </div>
                    </td>
                </tr>`;
            }
            return html;
        }).join('');

        if (append) {
            tbody.insertAdjacentHTML('beforeend', rowsHtml);
        } else {
            tbody.innerHTML = rowsHtml;
        }

        tradesOffset += trades.length;
        if (moreBtn) moreBtn.style.display = tradesOffset < total ? 'block' : 'none';
    } catch (e) {
        console.error('Failed to load trades:', e);
    }
}

// Utility functions for formatting
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString('ko-KR', { maximumFractionDigits: 8 });
}

function formatCurrency(value, exchangeOrCurrency) {
    if (value === null || value === undefined) return '-';

    // currency 필드가 직접 전달되는 경우
    const currencyUpper = exchangeOrCurrency?.toUpperCase() || '';

    // KRW 거래소 (Upbit, KIS 국내)
    const isKRW = ['KRW', 'UPBIT', 'KIS_KR', 'KIS', 'KIWOOM'].includes(currencyUpper);
    // USD 거래소 (OKX, Binance, Bybit, KIS 해외)
    const isUSD = ['USD', 'OKX', 'BINANCE', 'BYBIT', 'KIS_US'].includes(currencyUpper);

    if (isKRW) {
        return '₩' + Math.round(value).toLocaleString('ko-KR');
    } else if (isUSD) {
        return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    // 기본값
    return value.toLocaleString('ko-KR', { minimumFractionDigits: 2 });
}

// 수량 포맷 (소수점 4자리까지, USDT/KRW는 정수)
function formatQuantity(num) {
    if (num === null || num === undefined) return '0';
    if (num >= 1) {
        return num.toLocaleString('ko-KR', { maximumFractionDigits: 4 });
    }
    // 소수점 이하 수량은 4자리까지
    return num.toLocaleString('ko-KR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

// 손익 포맷 (부호 포함, 축약)
function formatProfitLoss(value, exchangeOrCurrency) {
    if (value === null || value === undefined) return '-';

    const currencyUpper = exchangeOrCurrency?.toUpperCase() || '';
    const isKRW = ['KRW', 'UPBIT', 'KIS_KR', 'KIS', 'KIWOOM'].includes(currencyUpper);
    const sign = value >= 0 ? '+' : '';

    if (isKRW) {
        return sign + '₩' + Math.round(value).toLocaleString('ko-KR');
    }
    return sign + '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Refresh buttons
document.getElementById('btn-refresh-holdings')?.addEventListener('click', loadHoldings);
document.getElementById('btn-refresh-strategies')?.addEventListener('click', loadActiveStrategies);
document.getElementById('btn-refresh-trades')?.addEventListener('click', () => loadRecentTrades(false));
document.getElementById('btn-load-more-trades')?.addEventListener('click', () => loadRecentTrades(true));

// Emergency stop button
document.getElementById('btn-emergency-stop')?.addEventListener('click', async () => {
    if (!confirm('모든 자동매매를 즉시 정지하시겠습니까?\n\n모든 활성 전략이 중단됩니다.')) return;

    try {
        if (auth.accessToken) {
            await invoke('emergency_stop', { accessToken: auth.accessToken });
        } else {
            await invoke('set_estop', { enabled: true });
        }
        showToast('긴급 정지가 활성화되었습니다', 'warning');
        loadActiveStrategies(); // Refresh strategies
    } catch (error) {
        showToast('긴급 정지 실패: ' + error, 'error');
    }
});

// =====================================================
// TV Connect Page (PHASE 4)
// =====================================================
let selectedExchange = null;
let selectedSymbol = null;
let tvWizardStep = 1;

async function loadTVConnectPage() {
    loadExchangeSelection();
    loadWebhookLogs();
    loadUserWebhookUrl();
    updateTVWizardUI(1);
    // [BUG FIX 3] 자동완성 초기화
    initTVAssetAutocomplete();
}

async function loadExchangeSelection() {
    const container = document.getElementById('exchange-selection');
    if (!container) return;

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        if (accounts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>등록된 거래소 계정이 없습니다.</p>
                    <button class="btn btn-primary" onclick="navigateTo('accounts')">계정 등록하기</button>
                </div>
            `;
            return;
        }

        container.innerHTML = accounts.map(acc => `
            <div class="exchange-card" data-id="${acc.id}" data-exchange="${acc.exchange}" data-name="${acc.name}">
                <div class="exchange-icon">${acc.exchange === 'OKX' ? '🪙' : '📈'}</div>
                <div class="exchange-name">${acc.name}</div>
                <div class="exchange-type">${acc.exchange}</div>
            </div>
        `).join('');

        container.querySelectorAll('.exchange-card').forEach(card => {
            card.addEventListener('click', () => {
                container.querySelectorAll('.exchange-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedExchange = { id: parseInt(card.dataset.id), exchange: card.dataset.exchange, name: card.dataset.name };
                document.getElementById('btn-tv-next-1').disabled = false;
            });
        });
    } catch (error) {
        container.innerHTML = '<p class="empty">계정 로딩 실패</p>';
    }
}

async function loadWebhookLogs() {
    const tbody = document.getElementById('webhook-logs-tbody');
    if (!tbody) return;

    try {
        let logs = [];
        if (auth.accessToken) {
            logs = await invoke('get_webhook_logs', { accessToken: auth.accessToken, limit: 20 });
        }

        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">최근 수신 웹훅 없음</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(log => {
            const statusClass = log.status === 'success' ? 'success' : log.status === 'rejected' ? 'warning' : 'error';
            const statusText = log.status === 'success' ? '성공' : log.status === 'rejected' ? '거부' : '실패';
            const timeStr = log.received_at ? new Date(log.received_at).toLocaleString('ko-KR') : '-';
            const content = log.error_message || `${log.action} ${log.symbol}`;

            return `
                <tr>
                    <td>${timeStr}</td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${log.exchange || '-'}</td>
                    <td>${log.symbol || '-'}</td>
                    <td title="${log.error_message || ''}">${content}</td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error('Failed to load webhook logs:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">로그 로딩 실패</td></tr>';
    }
}

async function loadUserWebhookUrl() {
    const webhookUrlEl = document.getElementById('webhook-url');
    if (!webhookUrlEl) return;

    try {
        if (auth.accessToken) {
            const urlInfo = await invoke('get_webhook_url', { accessToken: auth.accessToken });
            webhookUrlEl.textContent = urlInfo.webhook_url;
        } else if (auth.user && auth.user.id) {
            webhookUrlEl.textContent = `http://76.13.180.30/api/webhook/${auth.user.id}`;
        }
    } catch (error) {
        console.error('Failed to load webhook URL:', error);
    }
}

function updateTVWizardUI(step) {
    tvWizardStep = step;

    document.querySelectorAll('.wizard-step').forEach(stepEl => {
        const stepNum = parseInt(stepEl.dataset.step);
        stepEl.classList.remove('active', 'completed');
        if (stepNum === step) stepEl.classList.add('active');
        else if (stepNum < step) stepEl.classList.add('completed');
    });

    for (let i = 1; i <= 4; i++) {
        const content = document.getElementById(`tv-step-${i}`);
        if (content) content.style.display = i === step ? 'block' : 'none';
    }

    // Step 2 진입 시 선택된 거래소로 자동완성 필터 업데이트
    if (step === 2 && tvAssetAutocomplete && selectedExchange) {
        tvAssetAutocomplete.setExchange(selectedExchange.exchange);
    }

    // Step 3 진입 시 조건부 필드 초기화 (v2)
    if (step === 3) {
        updateSignalParamsConditionalFields();
    }
}

/**
 * UI에서 signal_params 수집 (v2)
 */
function collectSignalParams() {
    // Sizing (v2: select로 변경, currency 추가, reduce.mode 추가)
    const sizingMode = document.getElementById('sizing-mode')?.value || 'balance_pct';
    const sizingValue = parseFloat(document.getElementById('sizing-value')?.value) || 30;
    const sizingBase = document.querySelector('input[name="sizing-base"]:checked')?.value || 'free';
    const sizingCurrency = document.getElementById('sizing-currency')?.value || 'USDT';
    const maxNotional = parseFloat(document.getElementById('sizing-max-notional')?.value) || 0;
    const minNotional = parseFloat(document.getElementById('sizing-min-notional')?.value) || 0;
    const reduceMode = document.getElementById('sizing-reduce-mode')?.value || 'full';
    const reduceDefaultPct = parseFloat(document.getElementById('sizing-reduce-pct')?.value) || 100;

    // Risk (v2: select로 변경)
    const execMode = document.getElementById('risk-exec-mode')?.value || 'tv_exit_signal';
    const leverageValue = parseInt(document.getElementById('risk-leverage-value')?.value) || 1;

    const slEnabled = document.getElementById('risk-sl-enabled')?.checked || false;
    const slType = document.getElementById('risk-sl-type')?.value || 'pct';
    const slValue = parseFloat(document.getElementById('risk-sl-value')?.value) || 0;

    const tpEnabled = document.getElementById('risk-tp-enabled')?.checked || false;
    const tpType = document.getElementById('risk-tp-type')?.value || 'pct';
    const tpValue = parseFloat(document.getElementById('risk-tp-value')?.value) || 0;

    const trailingEnabled = document.getElementById('risk-trailing-enabled')?.checked || false;
    const trailingValue = parseFloat(document.getElementById('risk-trailing-value')?.value) || 0;
    const reduceOnly = document.getElementById('risk-reduce-only')?.checked ?? true;

    // Limits (v2: 객체 구조로 변경)
    const idempotencyEnabled = document.getElementById('limits-idempotency-enabled')?.checked ?? true;
    const cooldown = parseInt(document.getElementById('limits-cooldown')?.value) || 0;
    const oneTradePerBar = document.getElementById('limits-one-trade-per-bar')?.checked || false;

    const dailyTradesEnabled = document.getElementById('limits-daily-trades-enabled')?.checked || false;
    const dailyMaxTrades = parseInt(document.getElementById('limits-daily-max-trades')?.value) || 10;

    const dailyNotionalEnabled = document.getElementById('limits-daily-notional-enabled')?.checked || false;
    const dailyMaxNotional = parseFloat(document.getElementById('limits-daily-max-notional')?.value) || 1000000;

    const maxPositionsEnabled = document.getElementById('limits-max-positions-enabled')?.checked || false;
    const maxOpenPositions = parseInt(document.getElementById('limits-max-open-positions')?.value) || 5;

    const allowSameSideAdd = document.getElementById('limits-allow-same-side-add')?.checked ?? true;

    return {
        sizing: {
            mode: sizingMode,
            value: sizingValue,
            base: sizingBase,
            currency: sizingCurrency,
            max_notional_per_order: maxNotional,
            min_notional_per_order: minNotional,
            reduce: {
                mode: reduceMode,
                default_pct: reduceMode === 'partial' ? reduceDefaultPct : 100
            }
        },
        risk: {
            exec_mode: execMode,
            leverage_policy: 'fixed',
            leverage_value: leverageValue,
            sl: {
                enabled: slEnabled,
                type: slType,
                value: slValue,
                basis: 'entry',
                order_type: 'market'
            },
            tp: {
                enabled: tpEnabled,
                type: tpType,
                value: tpValue,
                basis: 'entry',
                order_type: 'market'
            },
            trailing: {
                enabled: trailingEnabled,
                type: 'pct',
                value: trailingValue
            },
            reduce_only: reduceOnly
        },
        limits: {
            idempotency: {
                enabled: idempotencyEnabled,
                key: 'alert_id'
            },
            cooldown_seconds: cooldown,
            one_trade_per_bar: oneTradePerBar,
            daily_max_trades: { enabled: dailyTradesEnabled, value: dailyMaxTrades },
            daily_max_notional: { enabled: dailyNotionalEnabled, value: dailyMaxNotional },
            max_open_positions: { enabled: maxPositionsEnabled, value: maxOpenPositions },
            allow_same_side_add: allowSameSideAdd
        },
        meta: {
            version: 2,
            notes: ''
        }
    };
}

/**
 * TradingView 웹훅 템플릿 생성 (v2: 간소화 - 설정은 서버에 저장)
 */
function generateTemplate() {
    // v2: 웹훅 JSON은 필수 필드만 포함 (sizing/risk/limits는 서버에 저장)
    const template = {
        action: '{{strategy.order.action}}',  // TV 변수로 동적 설정
        symbol: selectedSymbol || 'BTC-USDT',
        exchange: selectedExchange?.exchange || 'OKX',
        alert_id: '{{timenow}}'  // 중복 방지용
    };

    return JSON.stringify(template, null, 2);
}

/**
 * 전략/종목을 서버에 저장 (Tauri invoke 사용)
 * @returns {Promise<{ok: boolean, strategyId?: number, assetId?: number, error?: string}>}
 */
async function saveStrategyAndAsset() {
    if (!selectedExchange || !selectedSymbol) {
        return { ok: false, error: '거래소와 종목을 선택해주세요' };
    }

    if (!auth.accessToken) {
        return { ok: false, error: '로그인이 필요합니다' };
    }

    const signalParams = collectSignalParams();
    const strategyName = `${selectedExchange.exchange}_${selectedSymbol}_${Date.now()}`;
    const tvSecret = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    try {
        // 1. 전략 생성 (Tauri invoke)
        const strategyData = await invoke('create_strategy_with_params', {
            accessToken: auth.accessToken,
            name: strategyName,
            tvSecret: tvSecret,
            signalParams: signalParams
        });

        const strategyId = strategyData.id;
        if (!strategyId) {
            throw new Error('전략 ID를 받지 못했습니다');
        }

        // 2. signal_params 저장 (별도 API로 확실히 저장)
        try {
            await invoke('save_signal_params', {
                accessToken: auth.accessToken,
                strategyId: strategyId,
                signalParams: signalParams
            });
        } catch (e) {
            console.warn('signal_params 저장 실패, 계속 진행:', e);
        }

        // 3. 종목(asset) 생성
        const assetData = await invoke('create_asset', {
            accessToken: auth.accessToken,
            accountId: selectedExchange.id,
            strategyId: strategyId,
            symbol: selectedSymbol,
            market: 'spot'
        });

        return {
            ok: true,
            strategyId: strategyId,
            assetId: assetData.id,
            tvSecret: tvSecret
        };

    } catch (error) {
        console.error('saveStrategyAndAsset error:', error);
        return { ok: false, error: error.toString() };
    }
}

/**
 * signal_params를 UI에 로드 (v2)
 */
function loadSignalParamsToUI(params) {
    if (!params) return;

    const sizing = params.sizing || {};
    const risk = params.risk || {};
    const limits = params.limits || {};

    // Sizing (v2: select로 변경)
    const sizingModeEl = document.getElementById('sizing-mode');
    if (sizingModeEl) sizingModeEl.value = sizing.mode || 'balance_pct';

    const sizingValueEl = document.getElementById('sizing-value');
    if (sizingValueEl) sizingValueEl.value = sizing.value ?? 30;

    const sizingCurrencyEl = document.getElementById('sizing-currency');
    if (sizingCurrencyEl) sizingCurrencyEl.value = sizing.currency || 'USDT';

    const baseRadio = document.querySelector(`input[name="sizing-base"][value="${sizing.base || 'free'}"]`);
    if (baseRadio) baseRadio.checked = true;

    const maxNotionalEl = document.getElementById('sizing-max-notional');
    if (maxNotionalEl) maxNotionalEl.value = sizing.max_notional_per_order ?? 0;

    const minNotionalEl = document.getElementById('sizing-min-notional');
    if (minNotionalEl) minNotionalEl.value = sizing.min_notional_per_order ?? 0;

    const reduceModeEl = document.getElementById('sizing-reduce-mode');
    if (reduceModeEl) reduceModeEl.value = sizing.reduce?.mode || 'full';

    const reducePctEl = document.getElementById('sizing-reduce-pct');
    if (reducePctEl) reducePctEl.value = sizing.reduce?.default_pct ?? 100;

    // Risk (v2: select로 변경)
    const execModeEl = document.getElementById('risk-exec-mode');
    if (execModeEl) execModeEl.value = risk.exec_mode || 'tv_exit_signal';

    const leverageValueEl = document.getElementById('risk-leverage-value');
    if (leverageValueEl) leverageValueEl.value = risk.leverage_value ?? 1;

    // SL
    const slEnabledEl = document.getElementById('risk-sl-enabled');
    if (slEnabledEl) slEnabledEl.checked = risk.sl?.enabled ?? false;

    const slTypeEl = document.getElementById('risk-sl-type');
    if (slTypeEl) slTypeEl.value = risk.sl?.type ?? 'pct';

    const slValueEl = document.getElementById('risk-sl-value');
    if (slValueEl) slValueEl.value = risk.sl?.value ?? 2;

    // TP
    const tpEnabledEl = document.getElementById('risk-tp-enabled');
    if (tpEnabledEl) tpEnabledEl.checked = risk.tp?.enabled ?? false;

    const tpTypeEl = document.getElementById('risk-tp-type');
    if (tpTypeEl) tpTypeEl.value = risk.tp?.type ?? 'pct';

    const tpValueEl = document.getElementById('risk-tp-value');
    if (tpValueEl) tpValueEl.value = risk.tp?.value ?? 5;

    // Trailing
    const trailingEnabledEl = document.getElementById('risk-trailing-enabled');
    if (trailingEnabledEl) trailingEnabledEl.checked = risk.trailing?.enabled ?? false;

    const trailingValueEl = document.getElementById('risk-trailing-value');
    if (trailingValueEl) trailingValueEl.value = risk.trailing?.value ?? 1;

    const reduceOnlyEl = document.getElementById('risk-reduce-only');
    if (reduceOnlyEl) reduceOnlyEl.checked = risk.reduce_only ?? true;

    // Limits (v2: 객체 구조)
    const idempotencyEnabledEl = document.getElementById('limits-idempotency-enabled');
    if (idempotencyEnabledEl) idempotencyEnabledEl.checked = limits.idempotency?.enabled ?? true;

    const cooldownEl = document.getElementById('limits-cooldown');
    if (cooldownEl) cooldownEl.value = limits.cooldown_seconds ?? 0;

    const oneTradePerBarEl = document.getElementById('limits-one-trade-per-bar');
    if (oneTradePerBarEl) oneTradePerBarEl.checked = limits.one_trade_per_bar ?? false;

    // v2: 객체 구조 또는 v1 호환 (숫자)
    const dailyTradesObj = limits.daily_max_trades;
    const dailyTradesEnabledEl = document.getElementById('limits-daily-trades-enabled');
    const dailyMaxTradesEl = document.getElementById('limits-daily-max-trades');
    if (typeof dailyTradesObj === 'object') {
        if (dailyTradesEnabledEl) dailyTradesEnabledEl.checked = dailyTradesObj?.enabled ?? false;
        if (dailyMaxTradesEl) dailyMaxTradesEl.value = dailyTradesObj?.value ?? 10;
    } else {
        if (dailyTradesEnabledEl) dailyTradesEnabledEl.checked = (dailyTradesObj || 0) > 0;
        if (dailyMaxTradesEl) dailyMaxTradesEl.value = dailyTradesObj || 10;
    }

    const dailyNotionalObj = limits.daily_max_notional;
    const dailyNotionalEnabledEl = document.getElementById('limits-daily-notional-enabled');
    const dailyMaxNotionalEl = document.getElementById('limits-daily-max-notional');
    if (typeof dailyNotionalObj === 'object') {
        if (dailyNotionalEnabledEl) dailyNotionalEnabledEl.checked = dailyNotionalObj?.enabled ?? false;
        if (dailyMaxNotionalEl) dailyMaxNotionalEl.value = dailyNotionalObj?.value ?? 1000000;
    } else {
        if (dailyNotionalEnabledEl) dailyNotionalEnabledEl.checked = (dailyNotionalObj || 0) > 0;
        if (dailyMaxNotionalEl) dailyMaxNotionalEl.value = dailyNotionalObj || 1000000;
    }

    const maxPosObj = limits.max_open_positions;
    const maxPosEnabledEl = document.getElementById('limits-max-positions-enabled');
    const maxOpenPositionsEl = document.getElementById('limits-max-open-positions');
    if (typeof maxPosObj === 'object') {
        if (maxPosEnabledEl) maxPosEnabledEl.checked = maxPosObj?.enabled ?? false;
        if (maxOpenPositionsEl) maxOpenPositionsEl.value = maxPosObj?.value ?? 5;
    } else {
        if (maxPosEnabledEl) maxPosEnabledEl.checked = (maxPosObj || 0) > 0;
        if (maxOpenPositionsEl) maxOpenPositionsEl.value = maxPosObj || 5;
    }

    const allowSameSideAddEl = document.getElementById('limits-allow-same-side-add');
    if (allowSameSideAddEl) allowSameSideAddEl.checked = limits.allow_same_side_add ?? true;

    // 조건부 필드 표시 업데이트
    updateSignalParamsConditionalFields();
}

/**
 * Step 3 조건부 필드 표시/숨김 업데이트 (v2)
 */
function updateSignalParamsConditionalFields() {
    // Sizing: mode에 따른 조건부 표시
    const sizingMode = document.getElementById('sizing-mode')?.value || 'balance_pct';
    const sizingValueLabel = document.getElementById('sizing-value-label');
    const sizingValueSuffix = document.getElementById('sizing-value-suffix');
    const sizingBaseGroup = document.getElementById('sizing-base-group');
    const sizingMaxGroup = document.getElementById('sizing-max-notional-group');
    const sizingMinGroup = document.getElementById('sizing-min-notional-group');

    if (sizingMode === 'balance_pct') {
        if (sizingValueLabel) sizingValueLabel.textContent = '비율';
        if (sizingValueSuffix) sizingValueSuffix.textContent = '%';
        if (sizingBaseGroup) sizingBaseGroup.style.display = '';
        if (sizingMaxGroup) sizingMaxGroup.style.display = '';
        if (sizingMinGroup) sizingMinGroup.style.display = '';
    } else if (sizingMode === 'fixed_amount') {
        if (sizingValueLabel) sizingValueLabel.textContent = '금액';
        const currency = document.getElementById('sizing-currency')?.value || 'USDT';
        if (sizingValueSuffix) sizingValueSuffix.textContent = currency;
        if (sizingBaseGroup) sizingBaseGroup.style.display = 'none';
        if (sizingMaxGroup) sizingMaxGroup.style.display = '';
        if (sizingMinGroup) sizingMinGroup.style.display = '';
    } else if (sizingMode === 'fixed_qty') {
        if (sizingValueLabel) sizingValueLabel.textContent = '수량';
        if (sizingValueSuffix) sizingValueSuffix.textContent = '개';
        if (sizingBaseGroup) sizingBaseGroup.style.display = 'none';
        if (sizingMaxGroup) sizingMaxGroup.style.display = 'none';
        if (sizingMinGroup) sizingMinGroup.style.display = 'none';
    }

    // Sizing: reduce mode에 따른 조건부 표시
    const reduceMode = document.getElementById('sizing-reduce-mode')?.value || 'full';
    const reducePctGroup = document.getElementById('sizing-reduce-pct-group');
    if (reducePctGroup) reducePctGroup.style.display = reduceMode === 'partial' ? '' : 'none';

    // Currency suffix 업데이트
    const currency = document.getElementById('sizing-currency')?.value || 'USDT';
    const maxSuffix = document.getElementById('sizing-max-suffix');
    const minSuffix = document.getElementById('sizing-min-suffix');
    const dailySuffix = document.getElementById('limits-daily-suffix');
    if (maxSuffix) maxSuffix.textContent = currency;
    if (minSuffix) minSuffix.textContent = currency;
    if (dailySuffix) dailySuffix.textContent = currency;

    // Risk: exec_mode에 따른 SL/TP 섹션 표시
    const execMode = document.getElementById('risk-exec-mode')?.value || 'tv_exit_signal';
    const sltpSection = document.getElementById('risk-sltp-section');
    if (sltpSection) sltpSection.style.display = execMode === 'exchange_bracket' ? '' : 'none';

    // Risk: SL/TP/Trailing 체크박스에 따른 값 필드 표시
    const slEnabled = document.getElementById('risk-sl-enabled')?.checked || false;
    document.querySelectorAll('.sl-field').forEach(el => el.style.display = slEnabled ? '' : 'none');

    const tpEnabled = document.getElementById('risk-tp-enabled')?.checked || false;
    document.querySelectorAll('.tp-field').forEach(el => el.style.display = tpEnabled ? '' : 'none');

    const trailingEnabled = document.getElementById('risk-trailing-enabled')?.checked || false;
    document.querySelectorAll('.trailing-field').forEach(el => el.style.display = trailingEnabled ? '' : 'none');

    // Limits: 체크박스에 따른 값 필드 표시
    const dailyTradesEnabled = document.getElementById('limits-daily-trades-enabled')?.checked || false;
    const dailyTradesValueGroup = document.getElementById('limits-daily-trades-value-group');
    if (dailyTradesValueGroup) dailyTradesValueGroup.style.display = dailyTradesEnabled ? '' : 'none';

    const dailyNotionalEnabled = document.getElementById('limits-daily-notional-enabled')?.checked || false;
    const dailyNotionalValueGroup = document.getElementById('limits-daily-notional-value-group');
    if (dailyNotionalValueGroup) dailyNotionalValueGroup.style.display = dailyNotionalEnabled ? '' : 'none';

    const maxPosEnabled = document.getElementById('limits-max-positions-enabled')?.checked || false;
    const maxPosValueGroup = document.getElementById('limits-max-positions-value-group');
    if (maxPosValueGroup) maxPosValueGroup.style.display = maxPosEnabled ? '' : 'none';
}

// TV Wizard navigation
document.getElementById('btn-tv-next-1')?.addEventListener('click', () => updateTVWizardUI(2));
document.getElementById('btn-tv-prev-2')?.addEventListener('click', () => updateTVWizardUI(1));
document.getElementById('btn-tv-next-2')?.addEventListener('click', () => updateTVWizardUI(3));
document.getElementById('btn-tv-prev-3')?.addEventListener('click', () => updateTVWizardUI(2));
document.getElementById('btn-tv-next-3')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-tv-next-3');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '저장 중...';
    }

    try {
        // 서버에 전략/종목 저장
        const result = await saveStrategyAndAsset();

        if (!result.ok) {
            showToast(result.error || '저장 실패', 'error');
            return;
        }

        showToast('전략 및 종목이 저장되었습니다', 'success');

        // 템플릿 생성
        const templateCode = document.getElementById('template-code');
        if (templateCode) templateCode.textContent = generateTemplate();

        // 웹훅 URL 설정 (저장된 tvSecret 사용)
        const webhookUrl = document.getElementById('webhook-url');
        if (webhookUrl) {
            webhookUrl.textContent = `${API_BASE_URL}/tv?secret=${result.tvSecret}`;
        }

        updateTVWizardUI(4);
    } catch (error) {
        console.error('btn-tv-next-3 error:', error);
        showToast('저장 중 오류가 발생했습니다', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '템플릿 생성';
        }
    }
});
document.getElementById('btn-tv-prev-4')?.addEventListener('click', () => updateTVWizardUI(3));
document.getElementById('btn-tv-restart')?.addEventListener('click', () => {
    selectedExchange = null;
    selectedSymbol = null;
    document.querySelectorAll('.exchange-card').forEach(c => c.classList.remove('selected'));
    document.getElementById('btn-tv-next-1').disabled = true;
    updateTVWizardUI(1);
});

document.getElementById('btn-copy-template')?.addEventListener('click', async () => {
    const code = document.getElementById('template-code')?.textContent;
    if (code) {
        await navigator.clipboard.writeText(code);
        showToast('템플릿이 복사되었습니다', 'success');
    }
});

document.getElementById('btn-copy-webhook-url')?.addEventListener('click', async () => {
    const url = document.getElementById('webhook-url')?.textContent;
    if (url) {
        await navigator.clipboard.writeText(url);
        showToast('웹훅 URL이 복사되었습니다', 'success');
    }
});

document.getElementById('btn-refresh-webhook-logs')?.addEventListener('click', loadWebhookLogs);

// Step 3 조건부 필드 이벤트 리스너 (v2)
document.getElementById('sizing-mode')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('sizing-currency')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('sizing-reduce-mode')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('risk-exec-mode')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('risk-sl-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('risk-tp-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('risk-trailing-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('limits-daily-trades-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('limits-daily-notional-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);
document.getElementById('limits-max-positions-enabled')?.addEventListener('change', updateSignalParamsConditionalFields);

// Asset tags
document.querySelectorAll('.asset-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        selectedSymbol = tag.dataset.symbol;
        document.getElementById('btn-tv-next-2').disabled = false;
        showToast(`${selectedSymbol} 선택됨`, 'info');
    });
});

// =====================================================
// [BUG FIX 3] 자동완성 초기화 - 4곳에 적용
// =====================================================

// 자동완성 인스턴스 저장
let tvAssetAutocomplete = null;
let customSymbolAutocomplete = null;
let reversalSymbolAutocomplete = null;
let trendSymbolAutocomplete = null;
let stockKrAutocomplete = null;
let watchlistAddAutocomplete = null;

// 1. TV Connect Step 2: 자산 선택 자동완성
function initTVAssetAutocomplete() {
    const input = document.getElementById('asset-search-input');
    if (!input || tvAssetAutocomplete) return;

    tvAssetAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            selectedSymbol = symbol.code;
            document.getElementById('btn-tv-next-2').disabled = false;
            // 자산 리스트에 선택된 종목 표시
            const listEl = document.getElementById('tv-asset-list');
            if (listEl) {
                listEl.innerHTML = `
                    <div class="selected-asset-card">
                        <span class="asset-name">${symbol.name}</span>
                        <span class="asset-code">(${symbol.code})</span>
                        <span class="asset-market">${symbol.market || symbol.exchange}</span>
                    </div>
                `;
            }
            showToast(`${symbol.name} (${symbol.code}) 선택됨`, 'success');
        } else {
            selectedSymbol = null;
            document.getElementById('btn-tv-next-2').disabled = true;
            const listEl = document.getElementById('tv-asset-list');
            if (listEl) listEl.innerHTML = '<p class="empty">자산을 검색하세요</p>';
        }
    }, { exchange: 'all', showBadge: false });
}

// 2. Premium Strategy: 커스텀 전략 종목 선택
function initCustomSymbolAutocomplete() {
    const input = document.getElementById('custom-symbol');
    const exchangeSelect = document.getElementById('custom-exchange');
    if (!input || customSymbolAutocomplete) return;

    const initialExchange = exchangeSelect?.value || 'all';
    customSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: initialExchange, showBadge: true });

    // 거래소 변경 시 자동완성 필터 업데이트
    exchangeSelect?.addEventListener('change', () => {
        if (customSymbolAutocomplete) {
            customSymbolAutocomplete.setExchange(exchangeSelect.value);
        }
    });
}

// 3. Premium Strategy: 역추세 전략 종목 선택
function initReversalSymbolAutocomplete() {
    const input = document.getElementById('reversal-symbol');
    const exchangeSelect = document.getElementById('reversal-exchange');
    if (!input || reversalSymbolAutocomplete) return;

    const initialExchange = exchangeSelect?.value || 'all';
    reversalSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: initialExchange, showBadge: true });

    // 거래소 변경 시 자동완성 필터 업데이트
    exchangeSelect?.addEventListener('change', () => {
        if (reversalSymbolAutocomplete) {
            reversalSymbolAutocomplete.setExchange(exchangeSelect.value);
        }
    });
}

// 4. Premium Strategy: 추세 전략 종목 선택
function initTrendSymbolAutocomplete() {
    const input = document.getElementById('trend-symbol');
    const exchangeSelect = document.getElementById('trend-exchange');
    if (!input || trendSymbolAutocomplete) return;

    const initialExchange = exchangeSelect?.value || 'all';
    trendSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: initialExchange, showBadge: true });

    // 거래소 변경 시 자동완성 필터 업데이트
    exchangeSelect?.addEventListener('change', () => {
        if (trendSymbolAutocomplete) {
            trendSymbolAutocomplete.setExchange(exchangeSelect.value);
        }
    });
}

// 5. Stock KR: 종목 검색 자동완성
function initStockKrAutocomplete() {
    const input = document.getElementById('stock-kr-search');
    console.log('[initStockKrAutocomplete] input:', input, 'stockKrAutocomplete:', stockKrAutocomplete);
    if (!input || stockKrAutocomplete) {
        console.log('[initStockKrAutocomplete] 종료 - input없음 또는 이미 초기화됨');
        return;
    }

    console.log('[initStockKrAutocomplete] createSymbolAutocomplete 호출');
    stockKrAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        console.log('[initStockKrAutocomplete] onSelect:', symbol);
        if (symbol) {
            // 종목 상세 열기
            openStockDetail(symbol.code, symbol.exchange || 'KIS_KR');
        }
    }, { exchange: 'kis_kr', showBadge: false });
    console.log('[initStockKrAutocomplete] 완료:', stockKrAutocomplete);
}

// Stock KR 프리뷰 표시
async function showStockKrPreview(symbol) {
    const preview = document.getElementById('stock-kr-preview');
    if (!preview) return;

    document.getElementById('preview-stock-name').textContent = symbol.name;
    document.getElementById('preview-stock-code').textContent = symbol.code;
    preview.style.display = 'block';

    try {
        const detail = await invokeWithTimeout('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol.code,
            exchange: 'KIS_KR'
        }, 5000);

        if (detail) {
            const priceEl = document.getElementById('preview-price');
            const changeEl = document.getElementById('preview-change');
            const rsEl = document.getElementById('preview-rs');

            if (priceEl) priceEl.textContent = detail.price_formatted || detail.price || '-';
            if (changeEl) {
                const change = detail.change || 0;
                changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
                changeEl.className = change >= 0 ? 'positive' : 'negative';
            }
            if (rsEl) rsEl.textContent = detail.rs_total || '-';
        }
    } catch (e) {
        console.error('Failed to load stock preview:', e);
    }
}

function hideStockKrPreview() {
    const preview = document.getElementById('stock-kr-preview');
    if (preview) preview.style.display = 'none';
}

// 6. Watchlist: 종목 추가 모달 자동완성
let watchlistAddModal = null;
let watchlistAddSelectedSymbol = null;

function showWatchlistAddModal() {
    // 기존 모달이 없으면 생성
    if (!watchlistAddModal) {
        watchlistAddModal = document.createElement('div');
        watchlistAddModal.className = 'modal';
        watchlistAddModal.id = 'watchlist-add-modal';
        watchlistAddModal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h3>종목 추가</h3>
                    <button class="close-btn" id="close-watchlist-add-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>종목 검색</label>
                        <input type="text" id="watchlist-add-search" class="form-input" placeholder="종목명 또는 종목코드 검색..." autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label>메모 (선택)</label>
                        <input type="text" id="watchlist-add-memo" class="form-input" placeholder="메모 입력">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="btn-cancel-watchlist-add">취소</button>
                    <button class="btn btn-primary" id="btn-confirm-watchlist-add" disabled>추가</button>
                </div>
            </div>
        `;
        document.body.appendChild(watchlistAddModal);

        // 이벤트 바인딩
        document.getElementById('close-watchlist-add-modal').addEventListener('click', hideWatchlistAddModal);
        document.getElementById('btn-cancel-watchlist-add').addEventListener('click', hideWatchlistAddModal);
        document.getElementById('btn-confirm-watchlist-add').addEventListener('click', confirmWatchlistAdd);

        // 자동완성 초기화
        const searchInput = document.getElementById('watchlist-add-search');
        watchlistAddAutocomplete = createSymbolAutocomplete(searchInput, (symbol) => {
            watchlistAddSelectedSymbol = symbol;
            document.getElementById('btn-confirm-watchlist-add').disabled = !symbol;
        }, { exchange: 'all', showBadge: true });
    }

    watchlistAddSelectedSymbol = null;
    document.getElementById('watchlist-add-search').value = '';
    document.getElementById('watchlist-add-memo').value = '';
    document.getElementById('btn-confirm-watchlist-add').disabled = true;
    watchlistAddModal.style.display = 'flex';
}

function hideWatchlistAddModal() {
    if (watchlistAddModal) {
        watchlistAddModal.style.display = 'none';
    }
}

async function confirmWatchlistAdd() {
    if (!watchlistAddSelectedSymbol) {
        showToast('종목을 선택해주세요', 'warning');
        return;
    }

    const memo = document.getElementById('watchlist-add-memo')?.value || '';
    const group = document.querySelector('.group-tab.active')?.dataset.group || 'default';

    try {
        await invokeWithTimeout('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupName: group,
            symbol: watchlistAddSelectedSymbol.code,
            exchange: watchlistAddSelectedSymbol.exchange,
            memo: memo
        }, 5000);

        showToast(`${watchlistAddSelectedSymbol.name} 관심종목에 추가됨`, 'success');
        hideWatchlistAddModal();
        loadWatchlistItems(group); // 리스트 새로고침
    } catch (e) {
        showToast('종목 추가 실패: ' + e, 'error');
    }
}

// Watchlist 종목 추가 버튼 이벤트
document.getElementById('btn-add-watchlist-item')?.addEventListener('click', showWatchlistAddModal);

// 페이지 로드 시 자동완성 초기화
function initAllAutocompletes() {
    initTVAssetAutocomplete();
    // initStockKrAutocomplete는 loadStockKr()에서 호출 (DOM 준비 후)
}

// TV Connect 페이지 로드 시 자동완성 초기화
const originalLoadTVConnectPage = typeof loadTVConnectPage === 'function' ? loadTVConnectPage : null;

// Premium Strategy 페이지 로드 시 자동완성 초기화
function initPremiumStrategyAutocomplete() {
    initCustomSymbolAutocomplete();
    initReversalSymbolAutocomplete();
    initTrendSymbolAutocomplete();
}

// =====================================================
// Symbols Page (PHASE 5) — Real Exchange API Integration
// =====================================================
let currentSymbolExchange = 'all';
let symbolsData = [];
let symbolSearchTimeout = null;
let isSymbolsLoading = false;

// 디바운스 함수
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function loadSymbolsPage() {
    // Check user plan
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';

    if (plan === 'free' && role !== 'admin') {
        document.getElementById('symbols-restriction').style.display = 'flex';
        return;
    }

    document.getElementById('symbols-restriction').style.display = 'none';
    await loadPopularSymbols();
}

function showSymbolsLoading() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;
    isSymbolsLoading = true;
    tbody.innerHTML = `
        <tr>
            <td colspan="6" class="empty-cell">
                <div class="loading-spinner"></div>
                <span style="margin-left: 8px;">거래소에서 데이터 로딩 중...</span>
            </td>
        </tr>
    `;
}

async function loadPopularSymbols() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    showSymbolsLoading();

    try {
        let allSymbols = [];

        if (auth.accessToken) {
            // 거래소 필터에 따라 인기 종목 조회
            const exchangeParam = currentSymbolExchange === 'all' ? null : currentSymbolExchange;
            const data = await invoke('get_popular_symbols', {
                accessToken: auth.accessToken,
                exchange: exchangeParam
            });

            // 각 거래소별 결과 합치기
            if (data.okx) allSymbols = allSymbols.concat(data.okx);
            if (data.binance) allSymbols = allSymbols.concat(data.binance);
            if (data.bybit) allSymbols = allSymbols.concat(data.bybit);
            if (data.upbit) allSymbols = allSymbols.concat(data.upbit);
            if (data.kis_kr) allSymbols = allSymbols.concat(data.kis_kr);
            if (data.kis_kr_etf) allSymbols = allSymbols.concat(data.kis_kr_etf);
            if (data.kis_us) allSymbols = allSymbols.concat(data.kis_us);
            if (data.kis_us_etf) allSymbols = allSymbols.concat(data.kis_us_etf);

            // 현재 선택된 거래소만 필터
            if (currentSymbolExchange !== 'all') {
                allSymbols = allSymbols.filter(s => {
                    const exLower = s.exchange.toLowerCase().replace(/_/g, '-');
                    const filterLower = currentSymbolExchange.toLowerCase().replace(/_/g, '-');
                    return exLower === filterLower;
                });
            }
        }

        symbolsData = allSymbols;
        renderSymbolsTable(allSymbols);
    } catch (error) {
        console.error('Failed to load popular symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">인기 종목 로딩 실패</td></tr>';
    } finally {
        isSymbolsLoading = false;
    }
}

let searchSymbolsRequestId = 0;  // Race condition 방지용

async function searchSymbols(query) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    showSymbolsLoading();

    // 현재 요청 ID 저장
    const thisRequestId = ++searchSymbolsRequestId;

    try {
        const exchange = currentSymbolExchange === 'all' ? null : currentSymbolExchange;
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: exchange
        });

        // 이 요청이 최신 요청이 아니면 무시
        if (thisRequestId !== searchSymbolsRequestId) {
            console.log('[SearchSymbols] 오래된 요청 무시:', query);
            return;
        }

        // result.symbols 또는 result 자체가 배열인 경우 처리
        const symbols = result.symbols || result || [];
        symbolsData = symbols;
        renderSymbolsTable(symbols);
    } catch (error) {
        if (thisRequestId !== searchSymbolsRequestId) return;
        console.error('Failed to search symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 실패</td></tr>';
    } finally {
        if (thisRequestId === searchSymbolsRequestId) {
            isSymbolsLoading = false;
        }
    }
}

// 디바운스된 검색 함수 (300ms)
const debouncedSearch = debounce((query) => {
    if (query) {
        searchSymbols(query);
    } else {
        loadPopularSymbols();
    }
}, 300);

function renderSymbolsTable(symbols) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    if (!symbols || symbols.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 결과 없음</td></tr>';
        return;
    }

    tbody.innerHTML = symbols.map(s => {
        // exchange badge 클래스 결정 (kis_kr, kis_us 처리)
        const exchangeLower = (s.exchange || '').toLowerCase().replace('_', '-');
        const exchangeDisplay = s.exchange.replace('_', ' ').toUpperCase();

        return `
            <tr data-symbol="${s.symbol}" data-exchange="${s.exchange}" style="cursor: pointer;">
                <td><strong>${s.symbol}</strong></td>
                <td>${s.name || s.symbol}</td>
                <td><span class="exchange-badge ${exchangeLower}">${exchangeDisplay}</span></td>
                <td>${s.price_formatted || 'N/A'}</td>
                <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change_formatted || '0.00%'}</td>
                <td>${s.volume_formatted || '0'}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('tr[data-symbol]').forEach(row => {
        row.addEventListener('click', () => showSymbolDetail(row.dataset.symbol, row.dataset.exchange));
    });
}

let currentSymbolData = null;

async function showSymbolDetail(symbol, exchange) {
    const panel = document.getElementById('symbol-detail-panel');
    if (!panel) return;

    // 현재 심볼 정보 저장 (AI/관심종목 버튼용)
    currentDetailSymbol = symbol;
    currentDetailExchange = exchange;

    const isKIS = exchange.toLowerCase().startsWith('kis');

    // 기본 정보 초기화
    document.getElementById('detail-symbol-name').textContent = symbol;
    const exchangeDisplay = exchange.replace('_', ' ').toUpperCase();
    document.getElementById('detail-exchange').textContent = exchangeDisplay;
    document.getElementById('detail-exchange').className = `exchange-badge ${exchange.toLowerCase().replace('_', '-')}`;
    document.getElementById('detail-market').style.display = 'none';
    document.getElementById('detail-etf-badge').style.display = 'none';

    // 탭 초기화 (시세 탭 활성화)
    document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.detail-tab[data-tab="price"]')?.classList.add('active');
    document.querySelectorAll('.detail-tab-content').forEach(c => c.style.display = 'none');
    document.getElementById('detail-tab-price').style.display = 'block';

    // KIS 탭 표시/숨김
    const finTab = document.querySelector('.detail-tab[data-tab="financial"]');
    const opTab = document.querySelector('.detail-tab[data-tab="opinion"]');
    if (finTab) finTab.style.display = isKIS ? 'inline-block' : 'none';
    if (opTab) opTab.style.display = isKIS ? 'inline-block' : 'none';

    panel.style.display = 'block';

    // 로딩 상태 표시
    document.getElementById('detail-price').textContent = '로딩...';
    document.getElementById('detail-change').textContent = '-';
    document.getElementById('detail-high').textContent = '-';
    document.getElementById('detail-low').textContent = '-';
    document.getElementById('detail-volume').textContent = '-';
    document.getElementById('detail-market-cap').textContent = '-';
    const sourceEl = document.getElementById('detail-source');
    if (sourceEl) sourceEl.style.display = 'none';

    try {
        const detail = await invoke('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol,
            exchange: exchange
        });

        currentSymbolData = detail;

        // 기본 정보
        if (detail.basic) {
            document.getElementById('detail-symbol-name').textContent = detail.basic.name || symbol;
            if (detail.basic.market) {
                document.getElementById('detail-market').textContent = detail.basic.market;
                document.getElementById('detail-market').style.display = 'inline-block';
            }
            if (detail.basic.is_etf) {
                document.getElementById('detail-etf-badge').style.display = 'inline-block';
            }
        }

        // 가격 정보
        if (detail.price) {
            document.getElementById('detail-price').textContent = detail.price.current_formatted || 'N/A';
            const changeEl = document.getElementById('detail-change');
            changeEl.textContent = detail.price.change_formatted || 'N/A';
            changeEl.className = `price-change ${(detail.price.change || 0) >= 0 ? 'profit' : 'loss'}`;
            document.getElementById('detail-high').textContent = detail.price.high_formatted || '-';
            document.getElementById('detail-low').textContent = detail.price.low_formatted || '-';
            document.getElementById('detail-volume').textContent = detail.price.volume_formatted || '-';
            document.getElementById('detail-market-cap').textContent = detail.price.market_cap_formatted || '-';

            // 데이터 출처 표시
            const sourceEl = document.getElementById('detail-source');
            if (sourceEl) {
                const source = detail.price.source || (detail.has_kis_account ? 'kis' : '');
                if (source === 'naver') {
                    sourceEl.textContent = '네이버 금융';
                    sourceEl.className = 'data-source naver';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'yahoo') {
                    sourceEl.textContent = 'Yahoo Finance';
                    sourceEl.className = 'data-source yahoo';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'kis' || detail.has_kis_account) {
                    sourceEl.textContent = 'KIS API';
                    sourceEl.className = 'data-source kis';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'krx') {
                    sourceEl.textContent = 'KRX';
                    sourceEl.className = 'data-source naver';
                    sourceEl.style.display = 'inline-block';
                } else {
                    sourceEl.style.display = 'none';
                }
            }
        }

        // 일봉 차트 그리기
        if (detail.daily_prices && detail.daily_prices.length > 0) {
            drawDailyChart(detail.daily_prices, detail.price?.change || 0);
        } else if (detail.price?.current) {
            drawSimulatedChart(detail.price.current, detail.price?.change || 0);
        }

        // 투자자 동향 (국내주식만)
        if (detail.investor && detail.investor.length > 0) {
            document.getElementById('investor-trend-section').style.display = 'block';
            drawInvestorChart(detail.investor);
        } else {
            document.getElementById('investor-trend-section').style.display = 'none';
        }

        // 재무 탭 (국내주식만)
        if (isKIS) {
            if (detail.has_kis_account && detail.financial) {
                document.getElementById('financial-notice').style.display = 'none';
                document.getElementById('financial-content').style.display = 'block';
                document.getElementById('fin-per').textContent = detail.financial.per?.toFixed(2) || '-';
                document.getElementById('fin-pbr').textContent = detail.financial.pbr?.toFixed(2) || '-';
                document.getElementById('fin-roe').textContent = (detail.financial.roe?.toFixed(2) || '-') + '%';
                document.getElementById('fin-debt').textContent = (detail.financial.debt_ratio?.toFixed(1) || '-') + '%';

                if (detail.financial.income_statement) {
                    drawIncomeChart(detail.financial.income_statement);
                }
            } else {
                document.getElementById('financial-notice').style.display = 'block';
                document.getElementById('financial-content').style.display = 'none';
            }

            // 투자의견 탭
            if (detail.has_kis_account && detail.opinion) {
                document.getElementById('opinion-notice').style.display = 'none';
                document.getElementById('opinion-content').style.display = 'block';
                document.getElementById('consensus-badge').textContent = detail.opinion.consensus || '-';
                document.getElementById('consensus-badge').className = `consensus-badge ${detail.opinion.consensus === '매수' ? 'buy' : (detail.opinion.consensus === '매도' ? 'sell' : 'hold')}`;
                document.getElementById('target-price').textContent = detail.opinion.target_price_formatted || '-';
                document.getElementById('analyst-count').textContent = detail.opinion.analyst_count || 0;
                document.getElementById('buy-count').textContent = detail.opinion.buy_count || 0;
                document.getElementById('hold-count').textContent = detail.opinion.hold_count || 0;
                document.getElementById('sell-count').textContent = detail.opinion.sell_count || 0;

                drawOpinionChart(detail.opinion);
            } else {
                document.getElementById('opinion-notice').style.display = 'block';
                document.getElementById('opinion-content').style.display = 'none';
            }
        }

    } catch (error) {
        console.error('Failed to load symbol detail:', error);
        document.getElementById('detail-price').textContent = '조회 실패';
    }
}

// 상세 탭 전환
document.querySelectorAll('.detail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        document.querySelectorAll('.detail-tab-content').forEach(c => c.style.display = 'none');
        document.getElementById(`detail-tab-${tabName}`).style.display = 'block';
    });
});

function drawDailyChart(dailyPrices, change) {
    const canvas = document.getElementById('mini-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const prices = dailyPrices.map(d => d.close).reverse();
    if (prices.length === 0) return;

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;

    // 배경 그라데이션
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, change >= 0 ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, height);

    prices.forEach((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height * 0.8 - height * 0.1;
        ctx.lineTo(x, y);
    });
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fill();

    // 라인 그리기
    ctx.strokeStyle = change >= 0 ? '#22C55E' : '#EF4444';
    ctx.lineWidth = 2;
    ctx.beginPath();
    prices.forEach((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height * 0.8 - height * 0.1;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
}

function drawSimulatedChart(price, change) {
    const canvas = document.getElementById('mini-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    // 시뮬레이션 데이터
    const data = [];
    let value = price * 0.97;
    for (let i = 0; i < 60; i++) {
        value += (Math.random() - 0.45) * price * 0.005;
        data.push(value);
    }
    data.push(price);

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    ctx.strokeStyle = change >= 0 ? '#22C55E' : '#EF4444';
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((v, i) => {
        const x = (i / (data.length - 1)) * width;
        const y = height - ((v - min) / range) * height * 0.8 - height * 0.1;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
}

function drawInvestorChart(investorData) {
    const canvas = document.getElementById('investor-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const barWidth = width / (investorData.length * 4);
    const maxVal = Math.max(...investorData.flatMap(d => [Math.abs(d.foreign_net), Math.abs(d.institution_net), Math.abs(d.individual_net)])) || 1;

    investorData.reverse().forEach((d, i) => {
        const baseX = i * (barWidth * 4) + barWidth / 2;

        // 외국인
        const fH = (d.foreign_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#3B82F6';
        ctx.fillRect(baseX, height / 2 - (fH > 0 ? fH : 0), barWidth * 0.8, Math.abs(fH) || 2);

        // 기관
        const iH = (d.institution_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#F59E0B';
        ctx.fillRect(baseX + barWidth, height / 2 - (iH > 0 ? iH : 0), barWidth * 0.8, Math.abs(iH) || 2);

        // 개인
        const pH = (d.individual_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#EF4444';
        ctx.fillRect(baseX + barWidth * 2, height / 2 - (pH > 0 ? pH : 0), barWidth * 0.8, Math.abs(pH) || 2);
    });

    // 중앙선
    ctx.strokeStyle = '#4B5563';
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
}

function drawIncomeChart(incomeData) {
    const canvas = document.getElementById('income-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const data = incomeData.reverse();
    const barWidth = width / (data.length * 4);
    const maxVal = Math.max(...data.flatMap(d => [d.revenue, d.operating_profit, d.net_income])) || 1;

    data.forEach((d, i) => {
        const baseX = i * (barWidth * 4) + barWidth / 2;
        const bH = (d.revenue / maxVal) * (height - 30);
        const oH = (d.operating_profit / maxVal) * (height - 30);
        const nH = (d.net_income / maxVal) * (height - 30);

        ctx.fillStyle = '#3B82F6';
        ctx.fillRect(baseX, height - 20 - bH, barWidth * 0.8, bH);

        ctx.fillStyle = '#22C55E';
        ctx.fillRect(baseX + barWidth, height - 20 - oH, barWidth * 0.8, oH);

        ctx.fillStyle = '#F59E0B';
        ctx.fillRect(baseX + barWidth * 2, height - 20 - nH, barWidth * 0.8, nH);

        // 기간 라벨
        ctx.fillStyle = '#9CA3AF';
        ctx.font = '10px sans-serif';
        ctx.fillText(d.period, baseX, height - 5);
    });
}

function drawOpinionChart(opinion) {
    const canvas = document.getElementById('opinion-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 10;

    ctx.clearRect(0, 0, width, height);

    const total = (opinion.buy_count || 0) + (opinion.hold_count || 0) + (opinion.sell_count || 0);
    if (total === 0) return;

    const slices = [
        { value: opinion.buy_count || 0, color: '#22C55E' },
        { value: opinion.hold_count || 0, color: '#F59E0B' },
        { value: opinion.sell_count || 0, color: '#EF4444' },
    ];

    let startAngle = -Math.PI / 2;
    slices.forEach(slice => {
        const sliceAngle = (slice.value / total) * 2 * Math.PI;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.fill();
        startAngle += sliceAngle;
    });

    // 중앙 원 (도넛 효과)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 0.5, 0, 2 * Math.PI);
    ctx.fillStyle = '#1F2937';
    ctx.fill();
}

document.getElementById('btn-close-detail')?.addEventListener('click', () => {
    document.getElementById('symbol-detail-panel').style.display = 'none';
});

document.getElementById('btn-set-strategy-symbol')?.addEventListener('click', () => {
    const symbol = document.getElementById('detail-symbol-name')?.textContent;
    selectedSymbol = symbol;
    navigateTo('premium-strategy');
    showToast(`${symbol}으로 전략 설정 페이지로 이동`, 'info');
});

// Symbol search input with debounce
document.getElementById('symbol-search')?.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    debouncedSearch(query);
});

document.getElementById('symbol-search')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        // Enter 시 즉시 검색
        clearTimeout(symbolSearchTimeout);
        const query = e.target.value.trim();
        if (query) searchSymbols(query);
        else loadPopularSymbols();
    }
});

document.getElementById('btn-symbol-search')?.addEventListener('click', () => {
    const query = document.getElementById('symbol-search')?.value?.trim() || '';
    if (query) searchSymbols(query);
    else loadPopularSymbols();
});

document.querySelectorAll('.symbol-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        const symbol = tag.dataset.symbol;
        document.getElementById('symbol-search').value = symbol;
        searchSymbols(symbol);
    });
});

document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentSymbolExchange = tab.dataset.exchange;

        // 탭 전환 시 해당 거래소 심볼 로드
        const query = document.getElementById('symbol-search')?.value?.trim() || '';
        if (query) {
            searchSymbols(query);
        } else {
            loadPopularSymbols();
        }
    });
});

// =====================================================
// Premium Strategy Page (PHASE 6)
// =====================================================
let backtestChart = null;

async function loadPremiumStrategyPage() {
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';

    if (plan !== 'premium' && role !== 'admin') {
        document.getElementById('premium-restriction').style.display = 'flex';
        return;
    }

    document.getElementById('premium-restriction').style.display = 'none';
    loadStrategies();
    // [BUG FIX 3] 자동완성 초기화
    initPremiumStrategyAutocomplete();
    loadExchangeDropdowns();
}

async function loadStrategies() {
    const list = document.getElementById('strategies-list');
    if (!list) return;

    list.innerHTML = '<p class="loading">전략 로딩 중...</p>';

    try {
        let strategies = [];
        if (auth.accessToken) {
            strategies = await invoke('get_strategies', { accessToken: auth.accessToken });
        }

        if (!strategies || strategies.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <p>설정된 전략이 없습니다.</p>
                    <p>커스텀/역추세/추세 탭에서 전략을 추가하세요.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = strategies.map(s => `
            <div class="strategy-card" data-id="${s.id}">
                <div class="strategy-card-header">
                    <h4>${s.name}</h4>
                    <span class="strategy-type-badge ${s.strategy_type}">${s.strategy_type}</span>
                </div>
                <div class="strategy-card-body">
                    <div class="strategy-info">
                        <span>종목:</span>
                        <strong>${s.symbol}</strong>
                    </div>
                    <div class="strategy-info">
                        <span>거래소:</span>
                        <strong>${s.exchange}</strong>
                    </div>
                </div>
                <div class="strategy-card-actions">
                    <button class="btn btn-sm ${s.is_active ? 'btn-success' : 'btn-secondary'} btn-toggle-strategy" data-id="${s.id}">
                        ${s.is_active ? '실행중' : '비활성'}
                    </button>
                    <button class="btn btn-sm btn-danger btn-delete-strategy" data-id="${s.id}">삭제</button>
                </div>
            </div>
        `).join('');

        // 이벤트 바인딩
        list.querySelectorAll('.btn-toggle-strategy').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = parseInt(btn.dataset.id);
                try {
                    const result = await invoke('toggle_strategy', { accessToken: auth.accessToken, strategyId: id });
                    showToast(result.is_active ? '전략 활성화됨' : '전략 비활성화됨', 'success');
                    loadStrategies();
                } catch (e) {
                    showToast('전략 토글 실패', 'error');
                }
            });
        });

        list.querySelectorAll('.btn-delete-strategy').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm('이 전략을 삭제하시겠습니까?')) return;
                const id = parseInt(btn.dataset.id);
                try {
                    await invoke('delete_strategy', { accessToken: auth.accessToken, strategyId: id });
                    showToast('전략이 삭제되었습니다', 'success');
                    loadStrategies();
                } catch (e) {
                    showToast('전략 삭제 실패', 'error');
                }
            });
        });

    } catch (error) {
        console.error('Failed to load strategies:', error);
        list.innerHTML = '<p class="empty">전략 로딩 실패</p>';
    }
}

async function loadExchangeDropdowns() {
    const selects = ['custom-exchange', 'reversal-exchange', 'trend-exchange'];

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                select.innerHTML = '<option value="">선택하세요</option>';
                accounts.forEach(acc => {
                    select.innerHTML += `<option value="${acc.exchange}">${acc.name} (${acc.exchange})</option>`;
                });
                // KIS 거래소 선택 시 설정 모달 표시
                select.addEventListener('change', handleExchangeChange);
            }
        });
    } catch (e) {
        console.error('Failed to load exchanges:', e);
    }
}

// =====================================================
// KIS 주문 설정 모달 핸들러
// =====================================================
const kisOrderSettings = {
    KIS_KR: {
        orderMethod: 'regular_close',
        timingSeconds: 30
    },
    KIS_US: {
        signalMinutes: 2,
        slippageTicks: 3
    }
};

function handleExchangeChange(e) {
    const exchange = e.target.value?.toUpperCase();
    if (exchange === 'KIS_KR') {
        showKisKrModal();
    } else if (exchange === 'KIS_US') {
        showKisUsModal();
    }
}

function showKisKrModal() {
    const modal = document.getElementById('kis-kr-order-modal');
    if (!modal) return;

    // 저장된 설정값 로드
    const methodSelect = document.getElementById('kis-kr-order-method');
    const timingInput = document.getElementById('kis-kr-timing-seconds');
    const timingGroup = document.getElementById('kis-kr-timing-group');

    if (methodSelect) methodSelect.value = kisOrderSettings.KIS_KR.orderMethod;
    if (timingInput) timingInput.value = kisOrderSettings.KIS_KR.timingSeconds;

    // 다음날 시가는 타이밍 입력 불필요
    if (timingGroup) {
        timingGroup.style.display = kisOrderSettings.KIS_KR.orderMethod === 'next_day_open' ? 'none' : 'block';
    }

    modal.style.display = 'flex';
}

function showKisUsModal() {
    const modal = document.getElementById('kis-us-order-modal');
    if (!modal) return;

    // 저장된 설정값 로드
    const signalInput = document.getElementById('kis-us-signal-minutes');
    const slippageInput = document.getElementById('kis-us-slippage-ticks');

    if (signalInput) signalInput.value = kisOrderSettings.KIS_US.signalMinutes;
    if (slippageInput) slippageInput.value = kisOrderSettings.KIS_US.slippageTicks;

    modal.style.display = 'flex';
}

function hideKisKrModal() {
    const modal = document.getElementById('kis-kr-order-modal');
    if (modal) modal.style.display = 'none';
}

function hideKisUsModal() {
    const modal = document.getElementById('kis-us-order-modal');
    if (modal) modal.style.display = 'none';
}

async function saveKisKrSettings() {
    const methodSelect = document.getElementById('kis-kr-order-method');
    const timingInput = document.getElementById('kis-kr-timing-seconds');

    const orderMethod = methodSelect?.value || 'regular_close';
    const timingSeconds = parseInt(timingInput?.value || 30);

    // 로컬 상태 업데이트
    kisOrderSettings.KIS_KR.orderMethod = orderMethod;
    kisOrderSettings.KIS_KR.timingSeconds = timingSeconds;

    // API 호출하여 DB에 저장 (계정 ID가 있는 경우)
    const accountId = kisOrderSettings.KIS_KR.accountId;
    if (accountId && auth.accessToken) {
        try {
            await invoke('save_kis_order_settings', {
                accessToken: auth.accessToken,
                payload: {
                    account_id: accountId,
                    exchange_type: 'KIS_KR',
                    kr_order_method: orderMethod,
                    kr_timing_seconds: timingSeconds
                }
            });
        } catch (e) {
            console.error('KIS_KR 설정 저장 실패:', e);
        }
    }

    hideKisKrModal();
    showToast('KIS_KR 주문 설정이 저장되었습니다.', 'success');
}

async function saveKisUsSettings() {
    const signalInput = document.getElementById('kis-us-signal-minutes');
    const slippageInput = document.getElementById('kis-us-slippage-ticks');

    const signalMinutes = parseInt(signalInput?.value || 2);
    const slippageTicks = parseInt(slippageInput?.value || 3);

    // 로컬 상태 업데이트
    kisOrderSettings.KIS_US.signalMinutes = signalMinutes;
    kisOrderSettings.KIS_US.slippageTicks = slippageTicks;

    // API 호출하여 DB에 저장 (계정 ID가 있는 경우)
    const accountId = kisOrderSettings.KIS_US.accountId;
    if (accountId && auth.accessToken) {
        try {
            await invoke('save_kis_order_settings', {
                accessToken: auth.accessToken,
                payload: {
                    account_id: accountId,
                    exchange_type: 'KIS_US',
                    us_signal_minutes: signalMinutes,
                    us_slippage_ticks: slippageTicks
                }
            });
        } catch (e) {
            console.error('KIS_US 설정 저장 실패:', e);
        }
    }

    hideKisUsModal();
    showToast('KIS_US 주문 설정이 저장되었습니다.', 'success');
}

// KIS_KR 모달 이벤트 바인딩
document.getElementById('kis-kr-modal-close')?.addEventListener('click', hideKisKrModal);
document.getElementById('kis-kr-modal-cancel')?.addEventListener('click', hideKisKrModal);
document.getElementById('kis-kr-modal-confirm')?.addEventListener('click', saveKisKrSettings);

// KIS_KR 주문 방식 변경 시 타이밍 입력 표시/숨김
document.getElementById('kis-kr-order-method')?.addEventListener('change', (e) => {
    const timingGroup = document.getElementById('kis-kr-timing-group');
    if (timingGroup) {
        timingGroup.style.display = e.target.value === 'next_day_open' ? 'none' : 'block';
    }
});

// KIS_US 모달 이벤트 바인딩
document.getElementById('kis-us-modal-close')?.addEventListener('click', hideKisUsModal);
document.getElementById('kis-us-modal-cancel')?.addEventListener('click', hideKisUsModal);
document.getElementById('kis-us-modal-confirm')?.addEventListener('click', saveKisUsSettings);

// 모달 오버레이 클릭 시 닫기
document.getElementById('kis-kr-order-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'kis-kr-order-modal') hideKisKrModal();
});
document.getElementById('kis-us-order-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'kis-us-order-modal') hideKisUsModal();
});

// =============================================
// 수익률 기간 선택 모달
// =============================================
let profitPeriodState = {
    startDate: null,
    endDate: null,
    firstSnapshotDate: null
};

function showProfitPeriodModal() {
    const modal = document.getElementById('profit-period-modal');
    if (modal) {
        modal.style.display = 'flex';
        // 기본값 설정
        const startInput = document.getElementById('profit-start-date');
        const endInput = document.getElementById('profit-end-date');
        if (startInput && profitPeriodState.firstSnapshotDate) {
            startInput.value = profitPeriodState.firstSnapshotDate;
        }
        if (endInput) {
            endInput.value = new Date().toISOString().split('T')[0];
        }
        document.getElementById('profit-result').style.display = 'none';
    }
}

function hideProfitPeriodModal() {
    const modal = document.getElementById('profit-period-modal');
    if (modal) modal.style.display = 'none';
}

async function calculateProfitRate() {
    const startDate = document.getElementById('profit-start-date')?.value;
    const endDate = document.getElementById('profit-end-date')?.value;

    if (!auth.accessToken) {
        showToast('로그인이 필요합니다.', 'error');
        return;
    }

    try {
        const result = await invoke('get_portfolio_profit_rate', {
            accessToken: auth.accessToken,
            startDate: startDate || null,
            endDate: endDate || null
        });

        const resultDiv = document.getElementById('profit-result');
        if (resultDiv) {
            resultDiv.style.display = 'block';
            document.getElementById('profit-start-assets').textContent = result.start_assets_formatted || '₩0';
            document.getElementById('profit-end-assets').textContent = result.end_assets_formatted || '₩0';

            const rateEl = document.getElementById('profit-rate-result');
            const rate = result.profit_rate || 0;
            rateEl.textContent = (rate >= 0 ? '+' : '') + rate.toFixed(2) + '%';
            rateEl.style.color = rate >= 0 ? 'var(--success)' : 'var(--danger)';
        }

        profitPeriodState.startDate = result.start_date;
        profitPeriodState.endDate = result.end_date;

    } catch (e) {
        console.error('Failed to calculate profit rate:', e);
        showToast('수익률 계산 실패: ' + e, 'error');
    }
}

function applyProfitPeriod() {
    const totalProfit = document.getElementById('total-profit');
    const periodInfo = document.getElementById('profit-period-info');

    if (totalProfit && profitPeriodState.startDate && profitPeriodState.endDate) {
        // 이미 계산된 결과가 있으면 적용
        const rateEl = document.getElementById('profit-rate-result');
        if (rateEl) {
            totalProfit.textContent = rateEl.textContent;
            totalProfit.className = 'summary-value ' + (rateEl.textContent.startsWith('+') ? 'profit' : 'loss');
        }

        if (periodInfo) {
            periodInfo.textContent = `${profitPeriodState.startDate} ~ ${profitPeriodState.endDate}`;
        }
    }

    hideProfitPeriodModal();
}

function resetProfitPeriod() {
    profitPeriodState.startDate = null;
    profitPeriodState.endDate = null;

    const periodInfo = document.getElementById('profit-period-info');
    if (periodInfo) periodInfo.textContent = '';

    // 전체 기간으로 리셋하고 summary 다시 로드
    loadPortfolioSummary();
    hideProfitPeriodModal();
}

// 수익률 기간 모달 이벤트 바인딩
document.getElementById('btn-profit-period')?.addEventListener('click', showProfitPeriodModal);
document.getElementById('profit-modal-close')?.addEventListener('click', hideProfitPeriodModal);
document.getElementById('profit-modal-reset')?.addEventListener('click', resetProfitPeriod);
document.getElementById('profit-modal-apply')?.addEventListener('click', applyProfitPeriod);
document.getElementById('profit-period-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'profit-period-modal') hideProfitPeriodModal();
});

// 날짜 변경 시 자동 계산
document.getElementById('profit-start-date')?.addEventListener('change', calculateProfitRate);
document.getElementById('profit-end-date')?.addEventListener('change', calculateProfitRate);

// Strategy tabs
document.querySelectorAll('.strategy-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.strategy-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        document.querySelectorAll('.strategy-content').forEach(c => c.style.display = 'none');
        document.getElementById(`strategy-tab-${tab.dataset.tab}`).style.display = 'block';

        // 역추세매매 탭 클릭 시 MR 엔진 로드
        if (tab.dataset.tab === 'reversal') {
            loadMrEngineTab();
        }
        // 추세매매 탭 클릭 시 Trend 초기화
        if (tab.dataset.tab === 'trend') {
            loadTrendExchangeDropdown();
            initTrendDynamicUI();
        }
        // 커스텀 전략 탭 클릭 시 초기화
        if (tab.dataset.tab === 'custom') {
            loadCustomExchangeDropdown();
            initCustomConditionBuilder();
        }
    });
});

// Backtest buttons (커스텀 탭 전용)
document.getElementById('btn-run-backtest')?.addEventListener('click', runBacktest);

async function runBacktest() {
    showToast('백테스팅 실행 중...', 'info');

    // 현재 활성 탭에서 설정 수집
    const activeTab = document.querySelector('.strategy-tab.active')?.dataset.tab || 'custom';
    let strategyType = activeTab;
    let exchange = '';
    let symbol = '';
    let params = {};
    let orderSettings = {};

    // 헬퍼: 자동완성 선택값 우선, 없으면 input.value 사용
    const getSymbolCode = (inputId) => {
        const input = document.getElementById(inputId);
        return input?.dataset?.selectedCode || input?.value || 'BTC-USDT';
    };

    if (activeTab === 'reversal') {
        exchange = document.getElementById('reversal-exchange')?.value || 'OKX';
        symbol = getSymbolCode('reversal-symbol');
        params = {
            rsi_period: parseInt(document.getElementById('reversal-rsi-period')?.value || 14),
            overbought: parseInt(document.getElementById('reversal-overbought')?.value || 70),
            oversold: parseInt(document.getElementById('reversal-oversold')?.value || 30)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('reversal-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('reversal-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('reversal-tp')?.value) || null
        };
    } else if (activeTab === 'trend') {
        exchange = document.getElementById('trend-exchange')?.value || 'OKX';
        symbol = getSymbolCode('trend-symbol');
        params = {
            short_ma: parseInt(document.getElementById('trend-short-ma')?.value || 20),
            long_ma: parseInt(document.getElementById('trend-long-ma')?.value || 60)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('trend-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('trend-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('trend-tp')?.value) || null
        };
    } else {
        exchange = document.getElementById('custom-exchange')?.value || 'OKX';
        symbol = getSymbolCode('custom-symbol');
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('custom-qty')?.value || 100),
            leverage: parseInt(document.getElementById('custom-leverage')?.value || 1),
            stop_loss: parseFloat(document.getElementById('custom-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('custom-tp')?.value) || null
        };
    }

    const startDate = document.getElementById('backtest-start')?.value || '2024-01-01';
    const endDate = document.getElementById('backtest-end')?.value || '2025-12-31';
    const initialCapital = parseFloat(document.getElementById('backtest-capital')?.value || 10000000);

    try {
        const result = await invoke('run_backtest', {
            accessToken: auth.accessToken || '',
            strategyType: strategyType,
            exchange: exchange,
            symbol: symbol,
            startDate: startDate,
            endDate: endDate,
            initialCapital: initialCapital,
            params: params,
            orderSettings: orderSettings
        });

        displayBacktestResult(result);
        showToast('백테스팅 완료', 'success');
    } catch (error) {
        console.error('Backtest failed:', error);
        showToast('백테스팅 실패: ' + error, 'error');
    }
}

function displayBacktestResult(result) {
    const resultDiv = document.getElementById('backtest-result');
    if (!resultDiv) return;

    resultDiv.style.display = 'block';

    const summary = result.summary || {};
    document.getElementById('bt-total-return').textContent = `${summary.total_return >= 0 ? '+' : ''}${summary.total_return || 0}%`;
    document.getElementById('bt-cagr').textContent = `${summary.cagr >= 0 ? '+' : ''}${summary.cagr || 0}%`;
    document.getElementById('bt-mdd').textContent = `${summary.max_drawdown || 0}%`;
    document.getElementById('bt-sharpe').textContent = (summary.sharpe_ratio || 0).toFixed(2);
    document.getElementById('bt-winrate').textContent = `${summary.win_rate || 0}%`;
    document.getElementById('bt-trades').textContent = `${summary.total_trades || 0}회`;

    // 차트 업데이트
    if (result.equity_curve && result.equity_curve.length > 0) {
        initBacktestChartWithData(result.equity_curve);
    }
}

function initBacktestChartWithData(equityCurve) {
    const ctx = document.getElementById('backtest-chart');
    if (!ctx) return;

    if (backtestChart) backtestChart.destroy();

    const labels = equityCurve.map(p => p.date);
    const data = equityCurve.map(p => p.equity);

    backtestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '자산',
                data: data,
                borderColor: data[data.length - 1] >= data[0] ? '#22C55E' : '#EF4444',
                fill: false,
                tension: 0.1,
                pointRadius: data.length > 100 ? 0 : 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: '#9CA3AF', callback: (v) => `₩${(v/1000000).toFixed(0)}M` }
                },
                x: { display: false }
            }
        }
    });
}

function initBacktestChart() {
    const ctx = document.getElementById('backtest-chart');
    if (!ctx) return;

    if (backtestChart) backtestChart.destroy();

    const labels = [];
    const data = [];
    let equity = 10000000;

    for (let i = 0; i < 100; i++) {
        labels.push(`Day ${i}`);
        equity *= (1 + (Math.random() - 0.45) * 0.02);
        data.push(equity);
    }

    backtestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '자산',
                data: data,
                borderColor: '#22C55E',
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#9CA3AF' } },
                x: { display: false }
            }
        }
    });
}

document.getElementById('btn-activate-strategy')?.addEventListener('click', async () => {
    const activeTab = document.querySelector('.strategy-tab.active')?.dataset.tab || 'custom';
    let exchange = '';
    let symbol = '';
    let params = {};
    let orderSettings = {};

    // 헬퍼: 자동완성 선택값 우선, 없으면 input.value 사용
    const getSymbolCode = (inputId) => {
        const input = document.getElementById(inputId);
        return input?.dataset?.selectedCode || input?.value || 'BTC-USDT';
    };

    if (activeTab === 'reversal') {
        exchange = document.getElementById('reversal-exchange')?.value || 'OKX';
        symbol = getSymbolCode('reversal-symbol');
        params = {
            rsi_period: parseInt(document.getElementById('reversal-rsi-period')?.value || 14),
            overbought: parseInt(document.getElementById('reversal-overbought')?.value || 70),
            oversold: parseInt(document.getElementById('reversal-oversold')?.value || 30)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('reversal-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('reversal-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('reversal-tp')?.value) || null
        };
    } else if (activeTab === 'trend') {
        exchange = document.getElementById('trend-exchange')?.value || 'OKX';
        symbol = getSymbolCode('trend-symbol');
        params = {
            short_ma: parseInt(document.getElementById('trend-short-ma')?.value || 20),
            long_ma: parseInt(document.getElementById('trend-long-ma')?.value || 60)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('trend-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('trend-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('trend-tp')?.value) || null
        };
    } else {
        exchange = document.getElementById('custom-exchange')?.value || 'OKX';
        symbol = getSymbolCode('custom-symbol');
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('custom-qty')?.value || 100),
            leverage: parseInt(document.getElementById('custom-leverage')?.value || 1),
            stop_loss: parseFloat(document.getElementById('custom-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('custom-tp')?.value) || null
        };
    }

    const strategyName = `${activeTab} - ${symbol}`;

    try {
        await invoke('save_strategy', {
            accessToken: auth.accessToken || '',
            name: strategyName,
            strategyType: activeTab,
            exchange: exchange,
            symbol: symbol,
            params: params,
            orderSettings: orderSettings,
            isActive: true
        });
        showToast('전략이 저장되고 활성화되었습니다', 'success');
        document.querySelectorAll('.strategy-tab')[0].click();
        loadStrategies();
    } catch (error) {
        showToast('전략 저장 실패: ' + error, 'error');
    }
});

// =====================================================
// Accounts Page (PHASE 7)
// =====================================================
let accountVerified = false;
let verifyTimer = null;

async function loadAccountsPage() {
    if (!auth.isHubMode && !accountVerified) {
        // Show password verification modal
        document.getElementById('password-verify-modal').style.display = 'flex';
        return;
    }

    loadAccountsList();
}

document.getElementById('btn-verify-password')?.addEventListener('click', async () => {
    const password = document.getElementById('verify-password')?.value;
    if (!password) {
        document.getElementById('verify-error').textContent = '비밀번호를 입력하세요';
        return;
    }

    try {
        // Verify password via backend
        await invoke('verify_password', { accessToken: auth.accessToken, password });
        accountVerified = true;
        document.getElementById('password-verify-modal').style.display = 'none';
        loadAccountsList();

        // Set 5 minute timer
        const timerEl = document.getElementById('verify-timer');
        let seconds = 300;
        verifyTimer = setInterval(() => {
            seconds--;
            if (timerEl) timerEl.textContent = `접근 만료까지: ${Math.floor(seconds/60)}:${(seconds%60).toString().padStart(2,'0')}`;
            if (seconds <= 0) {
                clearInterval(verifyTimer);
                accountVerified = false;
            }
        }, 1000);

    } catch (error) {
        document.getElementById('verify-error').textContent = '비밀번호가 올바르지 않습니다';
    }
});

async function loadAccountsList() {
    const list = document.getElementById('accounts-list');
    if (!list) return;

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        if (accounts.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <p>등록된 계정이 없습니다.</p>
                    <p>계정 추가 버튼을 클릭하여 거래소를 연결하세요.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = accounts.map(acc => `
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-info">
                        <h3>${acc.name}</h3>
                        <span class="exchange-badge ${acc.exchange.toLowerCase()}">${acc.exchange}</span>
                    </div>
                    <span class="account-status ${acc.is_active ? 'active' : 'inactive'}">
                        ${acc.is_active ? '● 연결됨' : '○ 미연결'}
                    </span>
                </div>
                <div class="account-card-body">
                    <div class="account-detail">
                        <span>API Key</span>
                        <span>****${acc.has_keys ? '(저장됨)' : '(미설정)'}</span>
                    </div>
                </div>
                <div class="account-card-actions">
                    <button class="btn btn-secondary btn-test" data-name="${acc.name}" data-exchange="${acc.exchange}">연결 테스트</button>
                    <button class="btn btn-danger btn-delete" data-id="${acc.id}" data-name="${acc.name}" data-exchange="${acc.exchange}">삭제</button>
                </div>
            </div>
        `).join('');

        list.querySelectorAll('.btn-test').forEach(btn => {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = '테스트 중...';
                try {
                    await invoke('test_account_connection', { exchange: btn.dataset.exchange, accountName: btn.dataset.name });
                    showToast('연결 성공', 'success');
                } catch (e) {
                    showToast('연결 실패: ' + e, 'error');
                }
                btn.disabled = false;
                btn.textContent = '연결 테스트';
            });
        });

        list.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`${btn.dataset.name} 계정을 삭제하시겠습니까?`)) return;
                try {
                    await invoke('delete_api_key', { accessToken: auth.accessToken, accountId: parseInt(btn.dataset.id), accountName: btn.dataset.name, exchange: btn.dataset.exchange });
                    showToast('계정이 삭제되었습니다', 'success');
                    loadAccountsList();
                } catch (e) {
                    showToast('삭제 실패: ' + e, 'error');
                }
            });
        });

    } catch (error) {
        list.innerHTML = '<p class="empty">계정 로딩 실패</p>';
    }
}

// Account form
document.getElementById('btn-add-account')?.addEventListener('click', () => {
    document.getElementById('account-form-section').style.display = 'block';
});

document.getElementById('btn-cancel-account')?.addEventListener('click', () => {
    document.getElementById('account-form-section').style.display = 'none';
});

document.getElementById('account-exchange')?.addEventListener('change', (e) => {
    const exchange = e.target.value;
    // 모든 거래소 폼 숨김
    document.querySelectorAll('.exchange-form').forEach(form => form.style.display = 'none');
    // 선택된 거래소 폼만 표시
    const formMap = {
        'OKX': 'okx-form',
        'BINANCE': 'binance-form',
        'BYBIT': 'bybit-form',
        'UPBIT': 'upbit-form',
        'KIS_KR': 'kis-kr-form',
        'KIS_US': 'kis-us-form'
    };
    const formId = formMap[exchange];
    if (formId) {
        document.getElementById(formId).style.display = 'block';
    }
});

document.getElementById('btn-save-account')?.addEventListener('click', async () => {
    const exchange = document.getElementById('account-exchange').value;

    if (!exchange) {
        showToast('거래소를 선택하세요', 'error');
        return;
    }

    let name, apiKey, apiSecret, passphrase, accountNumber, accountType;

    if (exchange === 'OKX') {
        name = document.getElementById('okx-alias').value;
        apiKey = document.getElementById('okx-api-key').value;
        apiSecret = document.getElementById('okx-secret').value;
        passphrase = document.getElementById('okx-passphrase').value;
        if (!name || !apiKey || !apiSecret || !passphrase) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'BINANCE') {
        name = document.getElementById('binance-alias').value;
        apiKey = document.getElementById('binance-api-key').value;
        apiSecret = document.getElementById('binance-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'BYBIT') {
        name = document.getElementById('bybit-alias').value;
        apiKey = document.getElementById('bybit-api-key').value;
        apiSecret = document.getElementById('bybit-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'UPBIT') {
        name = document.getElementById('upbit-alias').value;
        apiKey = document.getElementById('upbit-access-key').value;
        apiSecret = document.getElementById('upbit-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'KIS_KR') {
        name = document.getElementById('kis-kr-alias').value;
        apiKey = document.getElementById('kis-kr-app-key').value;
        apiSecret = document.getElementById('kis-kr-app-secret').value;
        accountNumber = document.getElementById('kis-kr-account-number').value;
        if (!name || !apiKey || !apiSecret || !accountNumber) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'KIS_US') {
        name = document.getElementById('kis-us-alias').value;
        apiKey = document.getElementById('kis-us-app-key').value;
        apiSecret = document.getElementById('kis-us-app-secret').value;
        accountNumber = document.getElementById('kis-us-account-number').value;
        if (!name || !apiKey || !apiSecret || !accountNumber) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    }

    try {
        await invoke('register_api_key', {
            accessToken: auth.accessToken,
            name: name,
            exchange: exchange,
            apiKey: apiKey,
            apiSecret: apiSecret,
            apiPassphrase: passphrase || null,
            accountNumber: accountNumber || null
        });

        showToast('계정이 등록되었습니다', 'success');
        document.getElementById('account-form-section').style.display = 'none';
        // 폼 초기화
        document.querySelectorAll('.exchange-form input').forEach(input => input.value = '');
        document.getElementById('account-exchange').value = '';
        loadAccountsList();
    } catch (error) {
        showToast('등록 실패: ' + error, 'error');
    }
});

// =====================================================
// App Info Page (PHASE 7)
// =====================================================
async function loadAppInfoPage() {
    try {
        const result = await invoke('check_server_health');
        document.getElementById('app-server-status').textContent = result.ok ? '정상 연결' : '연결 오류';
        document.getElementById('app-last-connection').textContent = new Date().toLocaleString('ko-KR');
    } catch (e) {
        document.getElementById('app-server-status').textContent = '연결 실패';
    }

    // Update current plan
    const plan = auth.user?.plan || 'free';
    const planInfo = document.getElementById('current-plan-info');
    if (planInfo) {
        const badge = planInfo.querySelector('.plan-badge');
        const desc = planInfo.querySelector('.plan-description');
        if (badge) {
            badge.className = `plan-badge ${plan}`;
            badge.textContent = plan === 'premium' ? '프리미엄' : plan === 'hub' ? '허브' : '무료';
        }
        if (desc) {
            desc.textContent = plan === 'premium' ? '모든 기능을 이용할 수 있습니다.' :
                              plan === 'hub' ? '허브 기능을 이용할 수 있습니다.' :
                              '기본 기능을 무료로 이용하세요.';
        }
    }
}

document.getElementById('btn-open-terms')?.addEventListener('click', () => open('http://76.13.180.30/terms'));
document.getElementById('btn-open-privacy')?.addEventListener('click', () => open('http://76.13.180.30/privacy'));
document.getElementById('btn-export-logs')?.addEventListener('click', async () => {
    try {
        const path = await invoke('export_diagnostic');
        showToast('로그가 내보내졌습니다', 'success');
    } catch (e) {
        showToast('내보내기 실패', 'error');
    }
});

document.getElementById('btn-upgrade-hub')?.addEventListener('click', () => showToast('결제 시스템 준비 중입니다', 'info'));
document.getElementById('btn-upgrade-premium')?.addEventListener('click', () => showToast('결제 시스템 준비 중입니다', 'info'));

// =====================================================
// Admin Pages (PHASE 7)
// =====================================================
let adminPlanChart = null;

async function loadAdminUsersPage() {
    // 대시보드 통계 로드
    await loadAdminStats();
    // 최근 가입자 로드
    await loadRecentUsers();
    // AI 사용량 로드
    await loadAiUsageStats();
    // 사용자 목록 로드
    await loadUsersList();
}

async function loadAdminStats() {
    try {
        const stats = await invoke('admin_get_stats', { accessToken: auth.accessToken || '' });

        // 상단 카드 업데이트
        document.getElementById('admin-total-users').textContent = stats.total_users || 0;
        document.getElementById('admin-active-users').textContent = stats.active_users || 0;
        document.getElementById('admin-today-signups').textContent = stats.today_signups || 0;
        document.getElementById('admin-today-ai').textContent = stats.today_ai || 0;

        // 요금제별 테이블 업데이트
        const planCounts = stats.plan_counts || {};
        const planPrices = stats.plan_prices || {};
        const total = (planCounts.starter || 0) + (planCounts.standard || 0) + (planCounts.pro || 0) + (planCounts.premium || 0);

        // Starter
        const starterCount = planCounts.starter || planCounts.free || 0;
        document.getElementById('plan-starter-count').textContent = starterCount;
        document.getElementById('plan-starter-pct').textContent = total > 0 ? Math.round(starterCount / total * 100) + '%' : '0%';
        document.getElementById('plan-starter-revenue').textContent = '₩' + (starterCount * 19900).toLocaleString();

        // Standard
        const standardCount = planCounts.standard || planCounts.hub || 0;
        document.getElementById('plan-standard-count').textContent = standardCount;
        document.getElementById('plan-standard-pct').textContent = total > 0 ? Math.round(standardCount / total * 100) + '%' : '0%';
        document.getElementById('plan-standard-revenue').textContent = '₩' + (standardCount * 49000).toLocaleString();

        // Pro
        const proCount = planCounts.pro || 0;
        document.getElementById('plan-pro-count').textContent = proCount;
        document.getElementById('plan-pro-pct').textContent = total > 0 ? Math.round(proCount / total * 100) + '%' : '0%';
        document.getElementById('plan-pro-revenue').textContent = '₩' + (proCount * 99000).toLocaleString();

        // Premium
        const premiumCount = planCounts.premium || 0;
        document.getElementById('plan-premium-count').textContent = premiumCount;
        document.getElementById('plan-premium-pct').textContent = total > 0 ? Math.round(premiumCount / total * 100) + '%' : '0%';
        document.getElementById('plan-premium-revenue').textContent = '₩' + (premiumCount * 249000).toLocaleString();

        // 합계
        const totalRevenue = (starterCount * 19900) + (standardCount * 49000) + (proCount * 99000) + (premiumCount * 249000);
        document.getElementById('plan-total-count').innerHTML = '<strong>' + total + '</strong>';
        document.getElementById('plan-total-revenue').innerHTML = '<strong>₩' + totalRevenue.toLocaleString() + '</strong>';

        // 원형 차트 그리기
        drawAdminPlanChart([starterCount, standardCount, proCount, premiumCount]);

    } catch (e) {
        console.error('Failed to load admin stats:', e);
    }
}

function drawAdminPlanChart(data) {
    const canvas = document.getElementById('admin-plan-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (adminPlanChart) adminPlanChart.destroy();

    adminPlanChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Starter', 'Standard', 'Pro', 'Premium'],
            datasets: [{
                data: data,
                backgroundColor: ['#3B82F6', '#22C55E', '#F59E0B', '#EF4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '60%',
            plugins: { legend: { display: false } }
        }
    });
}

async function loadRecentUsers() {
    const tbody = document.getElementById('recent-users-tbody');
    if (!tbody) return;

    try {
        const result = await invoke('admin_get_recent_users', { accessToken: auth.accessToken || '' });
        const users = result.users || [];

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">최근 가입자 없음</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            const planText = getPlanDisplayName(user.plan);
            const createdAt = user.created_at ? user.created_at.split('T')[0] : '-';
            return `
                <tr>
                    <td><strong>${user.name || '-'}</strong><br><small>${user.email}</small></td>
                    <td>${createdAt}</td>
                    <td><span class="plan-badge ${user.plan}">${planText}</span></td>
                    <td><span class="status-badge ${user.is_active ? 'success' : 'error'}">${user.is_active ? '활성' : '비활성'}</span></td>
                </tr>
            `;
        }).join('');

    } catch (e) {
        console.error('Failed to load recent users:', e);
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">로딩 실패</td></tr>';
    }
}

function getPlanDisplayName(plan) {
    const names = {
        'starter': 'Starter',
        'standard': 'Standard',
        'pro': 'Pro',
        'premium': 'Premium',
        'free': 'Starter',
        'hub': 'Standard'
    };
    return names[plan] || plan;
}

async function loadAiUsageStats() {
    const tbody = document.getElementById('ai-usage-tbody');
    if (!tbody) return;

    try {
        const stats = await invoke('admin_get_stats', { accessToken: auth.accessToken || '' });
        const aiData = stats.ai_usage_7days || [];

        if (aiData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-cell">데이터 없음</td></tr>';
            return;
        }

        tbody.innerHTML = aiData.map(d => `
            <tr>
                <td>${d.date}</td>
                <td>${d.count}회</td>
                <td>~${d.tokens.toLocaleString()} 토큰</td>
            </tr>
        `).join('');

    } catch (e) {
        console.error('Failed to load AI usage stats:', e);
        tbody.innerHTML = '<tr><td colspan="3" class="empty-cell">로딩 실패</td></tr>';
    }
}

async function loadUsersList() {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">로딩 중...</td></tr>';

    try {
        const users = await invoke('admin_get_users', {
            accessToken: auth.accessToken || '',
            search: null,
            planFilter: null
        });

        if (!users || users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">사용자 없음</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            const planText = getPlanDisplayName(user.plan);
            const createdAt = user.created_at ? user.created_at.split('T')[0] : '-';
            const lastLogin = user.last_login_at ? user.last_login_at.split('T')[0] : '-';

            return `
                <tr data-user-id="${user.id}">
                    <td>${user.id}</td>
                    <td>${user.name || '-'}</td>
                    <td>${user.email}</td>
                    <td>
                        <select class="plan-select" data-user-id="${user.id}">
                            <option value="starter" ${user.plan === 'starter' || user.plan === 'free' ? 'selected' : ''}>Starter</option>
                            <option value="standard" ${user.plan === 'standard' || user.plan === 'hub' ? 'selected' : ''}>Standard</option>
                            <option value="pro" ${user.plan === 'pro' ? 'selected' : ''}>Pro</option>
                            <option value="premium" ${user.plan === 'premium' ? 'selected' : ''}>Premium</option>
                        </select>
                    </td>
                    <td>${createdAt}</td>
                    <td>${lastLogin}</td>
                    <td><span class="status-badge ${user.is_active ? 'success' : 'error'}">${user.is_active ? '활성' : '비활성'}</span></td>
                    <td>${user.role === 'admin' ? '<span class="role-badge">관리자</span>' : ''}</td>
                </tr>
            `;
        }).join('');

        // 요금제 변경 이벤트
        tbody.querySelectorAll('.plan-select').forEach(select => {
            select.addEventListener('change', async (e) => {
                const userId = parseInt(e.target.dataset.userId);
                const newPlan = e.target.value;
                try {
                    await invoke('admin_update_user_plan', {
                        accessToken: auth.accessToken || '',
                        userId: userId,
                        plan: newPlan
                    });
                    showToast('요금제가 변경되었습니다', 'success');
                } catch (error) {
                    showToast('요금제 변경 실패', 'error');
                    loadUsersList(); // 롤백
                }
            });
        });

    } catch (e) {
        console.error('Failed to load admin users:', e);
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">로딩 실패 (권한 확인)</td></tr>';
    }
}

async function loadAdminSystemPage() {
    try {
        const status = await invoke('admin_get_system_status', { accessToken: auth.accessToken || '' });

        document.getElementById('sys-status').textContent = status.status === 'ok' ? '정상' : '오류';
        document.getElementById('sys-status').className = `system-value ${status.status === 'ok' ? '' : 'error'}`;

        document.getElementById('sys-memory').textContent = `${status.memory_percent.toFixed(1)}%`;
        document.getElementById('sys-db').textContent = status.db_connected ? '정상' : '오류';
        document.getElementById('sys-db').className = `system-value ${status.db_connected ? '' : 'error'}`;

        // 웹훅 통계
        document.getElementById('webhook-total').textContent = status.webhook_total;
        document.getElementById('webhook-success').textContent = status.webhook_success;
        document.getElementById('webhook-failed').textContent = status.webhook_failed;

    } catch (e) {
        console.error('Failed to load system status:', e);
        document.getElementById('sys-status').textContent = '확인 불가';
    }
}

document.getElementById('btn-export-users')?.addEventListener('click', () => showToast('CSV 내보내기 준비 중', 'info'));

// =====================================================
// 시장분석 기능 (STEP 2)
// =====================================================

let currentRankingType = 'volume';
let currentEventType = 'all';

async function loadMarketOverview() {
    const restrictionEl = document.getElementById('market-restriction');
    const contentEl = document.getElementById('market-overview-content');
    if (!restrictionEl || !contentEl) return;

    try {
        const data = await invoke('get_market_overview', { accessToken: auth.accessToken || '' });

        restrictionEl.style.display = 'none';
        contentEl.style.display = 'block';

        // 지수 표시 (API 응답: data.kospi, data.kosdaq 직접 접근)
        updateIndexCard('index-kospi', data.kospi);
        updateIndexCard('index-kosdaq', data.kosdaq);
        updateIndexCard('index-nasdaq', data.nasdaq);
        updateIndexCard('index-sp500', data.sp500);
        updateIndexCard('index-dow', data.dow);

        // 시황 요약
        const summary = data.summary || {};
        document.getElementById('market-status-emoji').textContent = summary.emoji || '🟡';
        document.getElementById('market-status-text').textContent = summary.status || '-';

        const kospiChange = summary.kospi_change || 0;
        const kosdaqChange = summary.kosdaq_change || 0;
        document.getElementById('market-summary-text').textContent =
            `코스피 ${kospiChange >= 0 ? '+' : ''}${kospiChange.toFixed(2)}%, ` +
            `코스닥 ${kosdaqChange >= 0 ? '+' : ''}${kosdaqChange.toFixed(2)}%`;

        // 투자자 동향 (API 응답: data.investors)
        if (data.investors) {
            updateInvestorBars(data.investors);
            document.getElementById('investor-kis-hint').style.display = 'none';
        } else {
            document.getElementById('investor-kis-hint').style.display = data.has_kis_account ? 'none' : 'block';
        }

    } catch (error) {
        console.error('Market overview error:', error);
        if (error.toString().includes('Pro')) {
            restrictionEl.style.display = 'flex';
            contentEl.style.display = 'none';
        }
    }
}

function updateIndexCard(cardId, data) {
    const card = document.getElementById(cardId);
    if (!card || !data) return;

    const valueEl = card.querySelector('.index-value');
    const changeEl = card.querySelector('.index-change');

    // current 또는 price 필드 지원 (KR: current, US: price)
    const currentValue = data.current ?? data.price ?? 0;
    valueEl.textContent = currentValue?.toLocaleString() || '-';
    const change = data.change_percent || 0;
    changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
    changeEl.className = `index-change ${change >= 0 ? 'profit' : 'loss'}`;
}

function updateInvestorBars(investor) {
    // API 응답: foreign, institution, individual (without _net suffix)
    const maxVal = Math.max(
        Math.abs(investor.foreign || 0),
        Math.abs(investor.institution || 0),
        Math.abs(investor.individual || 0)
    ) || 1;

    updateInvestorBar('foreign', investor.foreign || 0, maxVal);
    updateInvestorBar('institution', investor.institution || 0, maxVal);
    updateInvestorBar('individual', investor.individual || 0, maxVal);
}

function updateInvestorBar(type, value, maxVal) {
    const bar = document.getElementById(`bar-${type}`);
    const valueEl = document.getElementById(`investor-${type}`);
    if (!bar || !valueEl) return;

    const pct = Math.min(Math.abs(value) / maxVal * 100, 100);
    bar.style.width = `${pct}%`;
    bar.classList.toggle('negative', value < 0);

    const formatted = formatKoreanNumber(Math.abs(value));
    valueEl.textContent = `${value >= 0 ? '+' : '-'}${formatted}`;
    valueEl.className = `value ${value >= 0 ? 'profit' : 'loss'}`;
}

function formatKoreanNumber(num) {
    if (num >= 100000000) return (num / 100000000).toFixed(1) + '억';
    if (num >= 10000) return (num / 10000).toFixed(1) + '만';
    return num.toLocaleString();
}

async function loadSectorAnalysis() {
    const restrictionEl = document.getElementById('sector-restriction');
    const leadingEl = document.getElementById('leading-sectors');
    const laggingEl = document.getElementById('lagging-sectors');
    const tbody = document.getElementById('sector-tbody');
    if (!tbody) return;

    try {
        const data = await invoke('get_market_sectors', { accessToken: auth.accessToken || '' });

        if (restrictionEl) restrictionEl.style.display = 'none';

        // 주도/부진 업종
        if (leadingEl && data.leading) {
            leadingEl.innerHTML = data.leading.map(s =>
                `<span class="sector-tag positive">${s.name} +${s.change?.toFixed(2)}%</span>`
            ).join('');
        }
        if (laggingEl && data.lagging) {
            laggingEl.innerHTML = data.lagging.map(s =>
                `<span class="sector-tag negative">${s.name} ${s.change?.toFixed(2)}%</span>`
            ).join('');
        }

        // 테이블
        const sectors = data.sectors || [];
        tbody.innerHTML = sectors.map(s => `
            <tr>
                <td>${s.name || '-'}</td>
                <td>${s.current?.toLocaleString() || '-'}</td>
                <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2) || 0}%</td>
            </tr>
        `).join('') || '<tr><td colspan="3" class="empty-cell">데이터 없음</td></tr>';

    } catch (error) {
        console.error('Sector analysis error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
    }
}

async function loadStockRanking(rankingType = 'volume', market = 'all') {
    const restrictionEl = document.getElementById('ranking-restriction');
    const tbody = document.getElementById('ranking-tbody');
    const headerEl = document.getElementById('ranking-extra-header');
    if (!tbody) return;

    currentRankingType = rankingType;

    // 헤더 업데이트
    const headers = {
        volume: '거래량', rise: '등락률', fall: '등락률',
        market_cap: '시가총액', foreign_buy: '외인순매수', foreign_sell: '외인순매도',
        institution_buy: '기관순매수', institution_sell: '기관순매도'
    };
    if (headerEl) headerEl.textContent = headers[rankingType] || '거래량';

    tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">로딩 중...</td></tr>';

    try {
        const data = await invoke('get_stock_ranking', {
            accessToken: auth.accessToken || '',
            rankingType: rankingType,
            market: market
        });

        if (restrictionEl) restrictionEl.style.display = 'none';

        const stocks = data.stocks || [];
        tbody.innerHTML = stocks.map(s => {
            let extraValue = '';
            if (rankingType === 'volume') extraValue = formatKoreanNumber(s.volume || 0);
            else if (rankingType === 'market_cap') extraValue = formatKoreanNumber((s.market_cap || 0) * 100000000);
            else if (rankingType.includes('foreign')) extraValue = formatKoreanNumber(Math.abs(s.foreign_net_qty || 0));
            else if (rankingType.includes('institution')) extraValue = formatKoreanNumber(Math.abs(s.institution_net_qty || 0));
            else extraValue = `${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%`;

            return `
                <tr onclick="showSymbolDetail('${s.code}', 'kis_kr')">
                    <td>${s.rank || '-'}</td>
                    <td>${s.name || '-'}</td>
                    <td>₩${(s.current || 0).toLocaleString()}</td>
                    <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2) || 0}%</td>
                    <td>${extraValue}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="5" class="empty-cell">데이터 없음</td></tr>';

    } catch (error) {
        console.error('Stock ranking error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
    }
}

async function loadFeaturedStocks() {
    const restrictionEl = document.getElementById('featured-restriction');

    try {
        const data = await invoke('get_featured_stocks', { accessToken: auth.accessToken || '' });

        if (restrictionEl) restrictionEl.style.display = 'none';

        // 상한가/하한가/급등/급락
        updateFeaturedList('upper-limit-list', data.upper_limit || []);
        updateFeaturedList('lower-limit-list', data.lower_limit || []);
        updateFeaturedList('surge-list', data.surge || []);
        updateFeaturedList('plunge-list', data.plunge || []);

        // 상승/하락 TOP 10
        updateFeaturedTable('rise-top-tbody', data.rise_top || []);
        updateFeaturedTable('fall-top-tbody', data.fall_top || []);

    } catch (error) {
        console.error('Featured stocks error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
    }
}

function updateFeaturedList(containerId, stocks) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (stocks.length === 0) {
        container.innerHTML = '<div class="featured-item"><span class="name">-</span></div>';
        return;
    }

    container.innerHTML = stocks.slice(0, 5).map(s => `
        <div class="featured-item" onclick="showSymbolDetail('${s.code}', 'kis_kr')">
            <span class="name">${s.name || '-'}</span>
            <span class="change ${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%</span>
        </div>
    `).join('');
}

function updateFeaturedTable(tbodyId, stocks) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    tbody.innerHTML = stocks.map(s => `
        <tr onclick="showSymbolDetail('${s.code}', 'kis_kr')">
            <td>${s.rank || '-'}</td>
            <td>${s.name || '-'}</td>
            <td>₩${(s.current || 0).toLocaleString()}</td>
            <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%</td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="empty-cell">-</td></tr>';
}

async function loadMarketEvents(eventType = 'all') {
    const restrictionEl = document.getElementById('events-restriction');
    const kisNotice = document.getElementById('events-kis-notice');
    const tbody = document.getElementById('events-tbody');
    if (!tbody) return;

    currentEventType = eventType;
    tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">로딩 중...</td></tr>';

    try {
        const data = await invoke('get_market_events', {
            accessToken: auth.accessToken || '',
            eventType: eventType,
            month: null
        });

        if (restrictionEl) restrictionEl.style.display = 'none';

        if (!data.has_kis_account && kisNotice) {
            kisNotice.style.display = 'block';
            tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">KIS 계정 등록 필요</td></tr>';
            return;
        }

        if (kisNotice) kisNotice.style.display = 'none';

        const events = data.events || [];
        const typeLabels = { dividend: '배당', ipo: '공모주', rights: '유상증자', bonus: '무상증자' };

        tbody.innerHTML = events.map(e => {
            let detail = '';
            if (e.type === 'dividend') detail = `${e.amount?.toLocaleString()}원 (${e.yield}%)`;
            else if (e.type === 'ipo') detail = `공모가 ${e.price?.toLocaleString()}원`;
            else detail = '-';

            return `
                <tr>
                    <td>${typeLabels[e.type] || e.type}</td>
                    <td>${e.stock_name || '-'}</td>
                    <td>${e.date || e.date_start || '-'}</td>
                    <td>${detail}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="4" class="empty-cell">예정된 이벤트 없음</td></tr>';

    } catch (error) {
        console.error('Market events error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
    }
}

// 시장분석 탭 이벤트
document.querySelectorAll('.ranking-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.ranking-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const marketSelect = document.getElementById('ranking-market-filter');
        loadStockRanking(tab.dataset.type, marketSelect?.value || 'all');
    });
});

document.getElementById('ranking-market-filter')?.addEventListener('change', (e) => {
    loadStockRanking(currentRankingType, e.target.value);
});

document.querySelectorAll('.event-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.event-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        loadMarketEvents(tab.dataset.type);
    });
});

// =====================================================
// AI 분석 + 관심종목 (STEP 3)
// =====================================================

let currentDetailSymbol = null;
let currentDetailExchange = null;

// AI 분석 버튼 클릭
document.getElementById('btn-ai-analysis')?.addEventListener('click', async () => {
    if (!currentSymbolData) {
        showToast('종목을 먼저 선택하세요', 'error');
        return;
    }

    const modal = document.getElementById('ai-modal');
    const loadingEl = document.getElementById('ai-loading');
    const reportEl = document.getElementById('ai-report');
    const errorEl = document.getElementById('ai-error');
    const usageEl = document.getElementById('ai-usage');

    modal.style.display = 'flex';
    loadingEl.style.display = 'block';
    reportEl.style.display = 'none';
    errorEl.style.display = 'none';

    try {
        const result = await invoke('request_ai_analysis', {
            accessToken: auth.accessToken || '',
            symbol: currentSymbolData.basic?.symbol || currentDetailSymbol,
            exchange: currentSymbolData.basic?.exchange || currentDetailExchange
        });

        loadingEl.style.display = 'none';

        if (result.success) {
            reportEl.innerHTML = markdownToHtml(result.report || '');
            reportEl.style.display = 'block';
            // 일일/월간 사용량 표시
            const dailyRemain = (result.daily_max || 0) - (result.daily_used || 0);
            const monthlyRemain = (result.monthly_max || 0) - (result.monthly_used || 0);
            usageEl.textContent = `오늘 ${result.daily_used}/${result.daily_max}회 | 이번 달 ${result.monthly_used}/${result.monthly_max}회`;
        } else {
            errorEl.textContent = result.error || 'AI 분석에 실패했습니다';
            errorEl.style.display = 'block';
            // 제한 초과 시에도 사용량 표시
            if (result.daily_max !== undefined) {
                usageEl.textContent = `오늘 ${result.daily_used}/${result.daily_max}회 | 이번 달 ${result.monthly_used}/${result.monthly_max}회`;
            }
        }
    } catch (error) {
        loadingEl.style.display = 'none';
        errorEl.textContent = error.toString();
        errorEl.style.display = 'block';
    }
});

// 간단한 마크다운 변환
function markdownToHtml(md) {
    return md
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        .replace(/^---$/gim, '<hr>')
        .replace(/\n/g, '<br>');
}

// AI 모달 닫기
document.getElementById('ai-modal-close')?.addEventListener('click', () => {
    document.getElementById('ai-modal').style.display = 'none';
});

document.getElementById('ai-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'ai-modal') {
        document.getElementById('ai-modal').style.display = 'none';
    }
});

// 관심종목 추가 버튼 클릭
document.getElementById('btn-add-watchlist')?.addEventListener('click', async () => {
    if (!currentSymbolData) {
        showToast('종목을 먼저 선택하세요', 'error');
        return;
    }

    const modal = document.getElementById('watchlist-modal');
    const groupsList = document.getElementById('watchlist-groups-list');

    modal.style.display = 'flex';
    groupsList.innerHTML = '<div class="loading">로딩 중...</div>';

    try {
        const data = await invoke('get_watchlist_groups', { accessToken: auth.accessToken || '' });
        const groups = data.groups || [];

        groupsList.innerHTML = groups.map(g => `
            <div class="watchlist-group-item" data-group-id="${g.id}">
                <span class="group-name">${g.name}</span>
            </div>
        `).join('') || '<div class="empty">그룹이 없습니다</div>';

        // 그룹 클릭 이벤트
        groupsList.querySelectorAll('.watchlist-group-item').forEach(item => {
            item.addEventListener('click', async () => {
                const groupId = parseInt(item.dataset.groupId);
                await addToWatchlist(groupId);
            });
        });
    } catch (error) {
        groupsList.innerHTML = '<div class="error">그룹 로딩 실패</div>';
    }
});

async function addToWatchlist(groupId) {
    try {
        await invoke('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupId: groupId,
            symbol: currentSymbolData.basic?.symbol || currentDetailSymbol,
            exchange: currentSymbolData.basic?.exchange || currentDetailExchange
        });
        showToast('관심종목에 추가되었습니다', 'success');
        document.getElementById('watchlist-modal').style.display = 'none';
    } catch (error) {
        showToast(error.toString(), 'error');
    }
}

// 새 그룹 생성
document.getElementById('btn-create-group')?.addEventListener('click', async () => {
    const nameInput = document.getElementById('new-group-name');
    const name = nameInput.value.trim();
    if (!name) {
        showToast('그룹 이름을 입력하세요', 'error');
        return;
    }

    try {
        await invoke('create_watchlist_group', {
            accessToken: auth.accessToken || '',
            name: name
        });
        nameInput.value = '';
        showToast('그룹이 생성되었습니다', 'success');
        // 목록 새로고침
        document.getElementById('btn-add-watchlist').click();
    } catch (error) {
        showToast(error.toString(), 'error');
    }
});

// 관심종목 모달 닫기
document.getElementById('watchlist-modal-close')?.addEventListener('click', () => {
    document.getElementById('watchlist-modal').style.display = 'none';
});

document.getElementById('watchlist-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'watchlist-modal') {
        document.getElementById('watchlist-modal').style.display = 'none';
    }
});

// =====================================================
// 시장분석 새 페이지 로드 (STEP A)
// =====================================================

// 국내시장 로드 (Phase 4: StockEasy 스타일 시장신호)
async function loadMarketKr() {
    const restrictionEl = document.getElementById('market-kr-restriction');
    const contentEl = document.getElementById('market-kr-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // 시장 개요 + 시장신호 API 병렬 호출
        const [overviewData, signalData] = await Promise.all([
            invokeWithTimeout('get_market_overview', { accessToken: auth.accessToken || '' }, 10000),
            invokeWithTimeout('get_market_signal', { accessToken: auth.accessToken || '' }, 10000)
        ]);

        console.log('[loadMarketKr] overview:', overviewData);
        console.log('[loadMarketKr] signal:', signalData);

        // signal 또는 overview 중 하나라도 있으면 진행
        if (!overviewData && !signalData) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketKr()">다시 시도</button></div>';
            return;
        }

        // 신호 데이터 추출 (signal API 우선, overview 폴백)
        const kospiSig = signalData?.kospi || {};
        const kosdaqSig = signalData?.kosdaq || {};
        // overview 또는 signal 데이터 병합
        // 상승 = 상한가 + 상승, 하락 = 하한가 + 하락 (스탁이지 동일)
        const kospi = {
            value: overviewData?.kospi?.value || kospiSig.index_value || 0,
            change_percent: overviewData?.kospi?.change_percent ?? kospiSig.change_percent ?? 0,
            change_amount: overviewData?.kospi?.change_amount ?? kospiSig.change_amount ?? 0,
            rising_stocks: (overviewData?.kospi?.rising_stocks || kospiSig.rising_stocks || 0) + (kospiSig.upper_limit_stocks || 0),
            falling_stocks: (overviewData?.kospi?.falling_stocks || kospiSig.falling_stocks || 0) + (kospiSig.lower_limit_stocks || 0),
            unchanged_stocks: overviewData?.kospi?.unchanged_stocks || kospiSig.unchanged_stocks || 0,
            trading_value: overviewData?.kospi?.trading_value || kospiSig.trading_value || 0,
            trading_value_prev: kospiSig.trading_value_prev || 0,
            upper_limit_stocks: kospiSig.upper_limit_stocks || 0,
            lower_limit_stocks: kospiSig.lower_limit_stocks || 0,
            foreign_net: kospiSig.foreign_net || 0,
            institution_net: kospiSig.institution_net || 0,
            individual_net: kospiSig.individual_net || 0
        };
        const kosdaq = {
            value: overviewData?.kosdaq?.value || kosdaqSig.index_value || 0,
            change_percent: overviewData?.kosdaq?.change_percent ?? kosdaqSig.change_percent ?? 0,
            change_amount: overviewData?.kosdaq?.change_amount ?? kosdaqSig.change_amount ?? 0,
            rising_stocks: (overviewData?.kosdaq?.rising_stocks || kosdaqSig.rising_stocks || 0) + (kosdaqSig.upper_limit_stocks || 0),
            falling_stocks: (overviewData?.kosdaq?.falling_stocks || kosdaqSig.falling_stocks || 0) + (kosdaqSig.lower_limit_stocks || 0),
            unchanged_stocks: overviewData?.kosdaq?.unchanged_stocks || kosdaqSig.unchanged_stocks || 0,
            trading_value: overviewData?.kosdaq?.trading_value || kosdaqSig.trading_value || 0,
            trading_value_prev: kosdaqSig.trading_value_prev || 0,
            upper_limit_stocks: kosdaqSig.upper_limit_stocks || 0,
            lower_limit_stocks: kosdaqSig.lower_limit_stocks || 0,
            status: kosdaqSig.status || 'confirmed_uptrend',
            status_label: kosdaqSig.status_label || '',
            active_dd_count: kosdaqSig.active_dd_count || 0
        };

        // UI 렌더링 (StockEasy 스타일 - 1줄 통합)
        contentEl.innerHTML = `
            <!-- 시장신호 헤더 (1줄 통합) -->
            <div class="se-header-unified">
                <!-- 좌측: 시장신호 + 신호등 -->
                <div class="se-header-left">
                    <div class="se-signal-title" id="signal-toggle">
                        <span>시장신호</span>
                        <span class="toggle-arrow" id="signal-arrow">∧</span>
                    </div>
                    <div class="se-signal-lights">
                        <div class="se-signal-group">
                            <span class="se-signal-label">단기</span>
                            <div class="se-capsule" id="short-term-capsule">
                                <span class="se-dot" data-color="green"></span>
                                <span class="se-dot" data-color="yellow"></span>
                                <span class="se-dot" data-color="red"></span>
                            </div>
                        </div>
                        <div class="se-signal-group">
                            <span class="se-signal-label">장기</span>
                            <div class="se-capsule" id="long-term-capsule">
                                <span class="se-dot" data-color="green"></span>
                                <span class="se-dot" data-color="yellow"></span>
                                <span class="se-dot" data-color="red"></span>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- 우측: KOSPI + KOSDAQ 블록 -->
                <div class="se-header-right">
                    <div class="se-index-block">
                        <div class="se-block-row1">
                            <span class="se-block-name">KOSPI</span>
                            <span class="se-block-pct ${(kospi.change_percent || 0) >= 0 ? 'up' : 'down'}">
                                ${(kospi.change_percent || 0) >= 0 ? '+' : ''}${(kospi.change_percent || 0).toFixed(2)}%
                            </span>
                        </div>
                        <div class="se-block-row2">
                            <span class="se-block-value">${kospi.value?.toLocaleString() || '-'}</span>
                            <span class="se-block-amt ${(kospi.change_amount || 0) >= 0 ? 'up' : 'down'}">
                                ${(kospi.change_amount || 0) >= 0 ? '▲' : '▼'}${Math.abs(kospi.change_amount || 0).toFixed(2)}
                            </span>
                        </div>
                        <div class="se-block-gauge">
                            <div class="up-bar" style="width: ${getGaugePercent(kospi, 'up')}%"></div>
                            <div class="neutral-bar" style="width: ${getGaugePercent(kospi, 'neutral')}%"></div>
                            <div class="down-bar" style="width: ${getGaugePercent(kospi, 'down')}%"></div>
                        </div>
                        <div class="se-block-stocks">
                            <span class="up">▲${kospi.rising_stocks || 0}</span>
                            <span class="neutral">${kospi.unchanged_stocks || 0}</span>
                            <span class="down">▼${kospi.falling_stocks || 0}</span>
                        </div>
                    </div>
                    <div class="se-index-block">
                        <div class="se-block-row1">
                            <span class="se-block-name">KOSDAQ</span>
                            <span class="se-block-pct ${(kosdaq.change_percent || 0) >= 0 ? 'up' : 'down'}">
                                ${(kosdaq.change_percent || 0) >= 0 ? '+' : ''}${(kosdaq.change_percent || 0).toFixed(2)}%
                            </span>
                        </div>
                        <div class="se-block-row2">
                            <span class="se-block-value">${kosdaq.value?.toLocaleString() || '-'}</span>
                            <span class="se-block-amt ${(kosdaq.change_amount || 0) >= 0 ? 'up' : 'down'}">
                                ${(kosdaq.change_amount || 0) >= 0 ? '▲' : '▼'}${Math.abs(kosdaq.change_amount || 0).toFixed(2)}
                            </span>
                        </div>
                        <div class="se-block-gauge">
                            <div class="up-bar" style="width: ${getGaugePercent(kosdaq, 'up')}%"></div>
                            <div class="neutral-bar" style="width: ${getGaugePercent(kosdaq, 'neutral')}%"></div>
                            <div class="down-bar" style="width: ${getGaugePercent(kosdaq, 'down')}%"></div>
                        </div>
                        <div class="se-block-stocks">
                            <span class="up">▲${kosdaq.rising_stocks || 0}</span>
                            <span class="neutral">${kosdaq.unchanged_stocks || 0}</span>
                            <span class="down">▼${kosdaq.falling_stocks || 0}</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 2행: 투자자별 순매수 (시장신호 바로 아래) -->
            <div class="se-investor-section card">
                <h3>투자자별 순매수</h3>
                <div class="se-investor-grid">
                    <div class="se-investor-item">
                        <span class="label">외국인</span>
                        <span class="value" id="kr-investor-foreign">-</span>
                    </div>
                    <div class="se-investor-item">
                        <span class="label">기관</span>
                        <span class="value" id="kr-investor-institution">-</span>
                    </div>
                    <div class="se-investor-item">
                        <span class="label">개인</span>
                        <span class="value" id="kr-investor-individual">-</span>
                    </div>
                </div>
            </div>

            <!-- 3행: 거래대금 (전일대비 포함) -->
            <div class="se-trading-value card">
                <h3>거래대금</h3>
                <div class="se-trading-grid">
                    <div class="se-trading-item">
                        <span class="label">KOSPI</span>
                        <span class="value">${formatTradingValue(kospi.trading_value)}</span>
                        <span class="change">${formatTradingValueChange(kospi.trading_value, kospi.trading_value_prev)}</span>
                    </div>
                    <div class="se-trading-item">
                        <span class="label">KOSDAQ</span>
                        <span class="value">${formatTradingValue(kosdaq.trading_value)}</span>
                        <span class="change">${formatTradingValueChange(kosdaq.trading_value, kosdaq.trading_value_prev)}</span>
                    </div>
                </div>
            </div>

            <!-- 4행: 신호 설명 (접기 가능) -->
            <div class="se-signal-desc" id="signal-desc">
                <p>시장 신호는 신호등 색상으로 현재 시장의 상태를 나타냅니다: (🟢 양호, 🟡 주의, 🔴 매우주의).</p>
                <p>단기/장기 신호는 각각 단기적, 장기적 관점에서의 시장 흐름을 보여주는 지표입니다.</p>
            </div>

            <!-- 5행: 서브탭 (시장지표 | 섹터 | 추세유지 | 신용잔고) -->
            <div class="se-subtabs">
                <button class="se-subtab active" data-tab="market-indicators">시장지표</button>
                <button class="se-subtab" data-tab="sector">섹터</button>
                <button class="se-subtab" data-tab="trend-maintain">추세유지</button>
                <button class="se-subtab" data-tab="credit-balance">신용잔고</button>
            </div>

            <!-- 시장지표 탭 -->
            <div class="se-tab-content" id="tab-market-indicators">
                <!-- Big Picture 컴팩트 -->
                <div class="se-bigpicture-row card">
                    <div class="se-bp-item">
                        <span class="se-bp-market">KOSPI</span>
                        <span class="se-bp-dot" id="bp-kospi-dot">●</span>
                        <span class="se-bp-status" id="bp-kospi-status">${kospiSig.status_label || '확인된 상승세'}</span>
                        <span class="se-bp-exposure">(${kospiSig.exposure || '80-100%'})</span>
                        <span class="se-bp-dd">DD:${kospiSig.active_dd_count || 0}</span>
                        ${(kospiSig.active_dd_count || 0) >= 3 ? '<span class="se-bp-warn">⚠️</span>' : ''}
                    </div>
                    <div class="se-bp-divider">|</div>
                    <div class="se-bp-item">
                        <span class="se-bp-market">KOSDAQ</span>
                        <span class="se-bp-dot" id="bp-kosdaq-dot">●</span>
                        <span class="se-bp-status" id="bp-kosdaq-status">${kosdaqSig.status_label || '확인된 상승세'}</span>
                        <span class="se-bp-exposure">(${kosdaqSig.exposure || '80-100%'})</span>
                        <span class="se-bp-dd">DD:${kosdaqSig.active_dd_count || 0}</span>
                        ${(kosdaqSig.active_dd_count || 0) >= 3 ? '<span class="se-bp-warn">⚠️</span>' : ''}
                    </div>
                </div>

                <!-- 20/200일선 하락비율 차트 -->
                <div class="se-ma-chart card">
                    <h3>20일/200일선 하락비율</h3>
                    <div class="se-ma-chart-area">
                        <canvas id="ma-ratio-chart"></canvas>
                    </div>
                </div>

                <!-- ADR 차트 -->
                <div class="se-ma-chart card">
                    <h3>ADR (등락비율)</h3>
                    <div class="se-ma-chart-area">
                        <canvas id="adr-chart"></canvas>
                    </div>
                </div>

            </div>

            <!-- 섹터 탭 -->
            <div class="se-tab-content" id="tab-sector" style="display:none;">
                <div class="se-sector-grid">
                    <div class="card">
                        <h3>🔥 주도 섹터 TOP 10</h3>
                        <div class="sector-list" id="kr-leading-sectors"></div>
                    </div>
                    <div class="card">
                        <h3>📉 약세 섹터 TOP 10</h3>
                        <div class="sector-list" id="kr-weak-sectors"></div>
                    </div>
                </div>
            </div>

            <!-- 추세유지 탭 -->
            <div class="se-tab-content" id="tab-trend-maintain" style="display:none;">
                <div class="card">
                    <h3>섹터별 추세유지 (20MA 기준)</h3>
                    <p class="trend-maintain-desc">
                        • <b>포지션</b>: 현재가가 20일 이동평균선 위에 며칠째 유지 또는 이탈 중인지<br>
                        • <b>신호등</b>: 섹터의 현재 상태 (<span style="color:#22c55e">●</span>양호, <span style="color:#fde047">●</span>주의, <span style="color:#ef4444">●</span>매우주의)<br>
                        • <b>대표종목(RS)</b>: RS 점수가 <b>90 이상</b>인 종목은 <b>굵게</b> 표시
                    </p>
                    <div class="trend-maintain-table-wrap">
                        <table class="trend-maintain-table" id="trend-maintain-table">
                            <thead>
                                <tr>
                                    <th class="sortable" data-sort="sector">섹터</th>
                                    <th>ETF</th>
                                    <th class="sortable" data-sort="change">등락률</th>
                                    <th class="sortable" data-sort="days">포지션</th>
                                    <th>신호</th>
                                    <th class="sortable" data-sort="gap">이격률</th>
                                    <th>대표종목(RS)</th>
                                </tr>
                            </thead>
                            <tbody id="trend-maintain-body">
                                <tr><td colspan="7" class="loading-cell">데이터 로딩 중...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- 신용잔고 탭 -->
            <div class="se-tab-content" id="tab-credit-balance" style="display:none;">
                <div class="card">
                    <h3>신용잔고</h3>
                    <p class="empty-state">추후 업데이트 예정</p>
                </div>
            </div>
        `;

        // 신호등 업데이트
        updateSignalCapsule('short-term-capsule', kospiSig.short_term_signal || 'green');
        updateSignalCapsule('long-term-capsule', kospiSig.long_term_signal || 'green');

        // Big Picture 색상 업데이트
        updateBigPictureDot('bp-kospi-dot', kospiSig.status);
        updateBigPictureDot('bp-kosdaq-dot', kosdaqSig.status);

        // 서브탭 이벤트
        document.querySelectorAll('.se-subtab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('.se-subtab').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                const tabId = e.target.dataset.tab;
                document.querySelectorAll('.se-tab-content').forEach(c => c.style.display = 'none');
                document.getElementById('tab-' + tabId).style.display = 'block';
                // 탭 클릭 시 데이터 로드
                if (tabId === 'trend-maintain') {
                    loadTrendMaintainData();
                } else if (tabId === 'sector') {
                    loadSectorData();
                }
            });
        });

        // 신호 접기/펴기
        document.getElementById('signal-toggle')?.addEventListener('click', () => {
            const desc = document.getElementById('signal-desc');
            const arrow = document.getElementById('signal-arrow');
            if (desc.style.display === 'none') {
                desc.style.display = 'block';
                arrow.textContent = '∧';
            } else {
                desc.style.display = 'none';
                arrow.textContent = '∨';
            }
        });

        // 투자자 동향 (signal API 데이터 우선 사용)
        const investors = {
            foreign: kospiSig.foreign_net ?? overviewData?.investors?.foreign ?? 0,
            institution: kospiSig.institution_net ?? overviewData?.investors?.institution ?? 0,
            individual: kospiSig.individual_net ?? overviewData?.investors?.individual ?? 0
        };
        const formatInvestor = (v) => {
            if (v == null) return '-';
            if (v === 0) return '0억';
            const sign = v > 0 ? '+' : '-';
            return `${sign}${Math.abs(v).toLocaleString()}억`;
        };
        const foreignEl = document.getElementById('kr-investor-foreign');
        const instEl = document.getElementById('kr-investor-institution');
        const indivEl = document.getElementById('kr-investor-individual');
        if (foreignEl) {
            foreignEl.textContent = formatInvestor(investors.foreign);
            foreignEl.className = `value ${(investors.foreign || 0) >= 0 ? 'up' : 'down'}`;
        }
        if (instEl) {
            instEl.textContent = formatInvestor(investors.institution);
            instEl.className = `value ${(investors.institution || 0) >= 0 ? 'up' : 'down'}`;
        }
        if (indivEl) {
            indivEl.textContent = formatInvestor(investors.individual);
            indivEl.className = `value ${(investors.individual || 0) >= 0 ? 'up' : 'down'}`;
        }

        // 섹터 리스트
        const sectors = overviewData.sectors || [];
        const sectorListEl = document.getElementById('kr-sector-list');
        if (sectorListEl) {
            if (sectors.length > 0) {
                sectorListEl.innerHTML = sectors.slice(0, 5).map(s => `
                    <div class="sector-item">
                        <span class="sector-name">${s.name}</span>
                        <span class="sector-change ${(s.change_percent || 0) >= 0 ? 'profit' : 'loss'}">
                            ${(s.change_percent || 0) >= 0 ? '+' : ''}${(s.change_percent || 0).toFixed(2)}%
                        </span>
                    </div>
                `).join('');
            } else {
                sectorListEl.innerHTML = '<div class="empty-state">섹터 데이터 없음</div>';
            }
        }

        // 차트 로드
        loadMaRatioChart();
        loadAdrChart();

    } catch (error) {
        console.error('Market KR error:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        contentEl.innerHTML = `<div class="error-state"><p>${errMsg}</p><button class="btn btn-sm btn-primary" onclick="loadMarketKr()">다시 시도</button></div>`;
    }
}

// 게이지 퍼센트 계산
function getGaugePercent(data, type) {
    const rising = data.rising_stocks || 0;
    const falling = data.falling_stocks || 0;
    const unchanged = data.unchanged_stocks || 0;
    const total = rising + falling + unchanged;
    if (total === 0) return 0;

    let percent = 0;
    if (type === 'up') percent = (rising / total * 100);
    else if (type === 'neutral') percent = (unchanged / total * 100);
    else if (type === 'down') percent = (falling / total * 100);

    console.log(`[Gauge] ${type}: ${percent.toFixed(1)}% (rising=${rising}, falling=${falling}, unchanged=${unchanged})`);
    return percent.toFixed(1);
}

// 거래대금 포맷
function formatTradingValue(value) {
    if (!value) return '-';
    const billion = value / 100000000; // 억 단위
    if (billion >= 10000) {
        return (billion / 10000).toFixed(1) + '조';
    }
    return billion.toFixed(0) + '억';
}

// 거래대금 전일대비 포맷
function formatTradingValueChange(current, prev) {
    if (!current || !prev) return '';
    const diff = current - prev;
    const pct = ((diff / prev) * 100).toFixed(1);
    const diffBillion = diff / 100000000;

    let diffStr;
    if (Math.abs(diffBillion) >= 10000) {
        diffStr = (diffBillion / 10000).toFixed(1) + '조';
    } else {
        diffStr = Math.abs(diffBillion).toFixed(0) + '억';
    }

    if (diff > 0) {
        return `<span class="positive">+${diffStr} (+${pct}%)</span>`;
    } else if (diff < 0) {
        return `<span class="negative">-${diffStr} (${pct}%)</span>`;
    }
    return '';
}

// 신호등 캡슐 업데이트 (G/Y/R 중 하나 활성화)
function updateSignalCapsule(capsuleId, signal) {
    const capsule = document.getElementById(capsuleId);
    if (!capsule) return;

    const dots = capsule.querySelectorAll('.se-dot');
    dots.forEach(dot => {
        const color = dot.dataset.color;
        if (color === signal) {
            dot.classList.add('active');
        } else {
            dot.classList.remove('active');
        }
    });
}

// Big Picture 상태별 색상
function updateBigPictureDot(dotId, status) {
    const dot = document.getElementById(dotId);
    if (!dot) return;

    const colors = {
        'confirmed_uptrend': '#22c55e',
        'uptrend_under_pressure': '#fde047',
        'market_in_correction': '#ef4444',
        'rally_attempt': '#3b82f6'
    };
    dot.style.color = colors[status] || '#6b7280';
}

// MA 비율 차트 (쌍축 - KOSPI 지수 + 하락비율)
async function loadMaRatioChart() {
    const canvas = document.getElementById('ma-ratio-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // 기존 차트 제거
    if (window.maRatioChartInstance) {
        window.maRatioChartInstance.destroy();
    }

    // 로딩 표시
    const container = canvas.parentElement;
    if (container) {
        container.style.position = 'relative';
    }

    try {
        // API에서 데이터 가져오기
        const data = await invokeWithTimeout('get_market_breadth_with_index', {
            accessToken: auth.accessToken || '',
            days: 250,
            market: 'KOSPI'
        }, 30000);

        console.log('[loadMaRatioChart] API 응답:', data);

        // 데이터 검증
        if (data.error || !data.dates || data.dates.length === 0) {
            console.warn('[loadMaRatioChart] 데이터 없음, 초기화 필요');
            // 초기화 시도
            await initBreadthData();
            return;
        }

        // X축 레이블 (날짜)
        const labels = data.dates.map(d => {
            const date = new Date(d);
            return `${date.getMonth() + 1}/${date.getDate()}`;
        });

        // 하락비율을 % 단위로 변환 (0~1 → 0~100)
        const belowMa20 = data.below_ma20.map(v => v != null ? (v * 100).toFixed(1) : null);
        const belowMa200 = data.below_ma200.map(v => v != null ? (v * 100).toFixed(1) : null);

        window.maRatioChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'KOSPI',
                        data: data.index_values,
                        borderColor: '#3b82f6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.1,
                        fill: false,
                        yAxisID: 'y-index',
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: '200일선 하락비율',
                        data: belowMa200,
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249,115,22,0.1)',
                        borderWidth: 1.5,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y-ratio',
                        pointRadius: 0,
                        pointHoverRadius: 3
                    },
                    {
                        label: '20일선 하락비율',
                        data: belowMa20,
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34,197,94,0.1)',
                        borderWidth: 1.5,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y-ratio',
                        pointRadius: 0,
                        pointHoverRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#9ca3af',
                            usePointStyle: true,
                            pointStyle: 'line',
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(30,41,59,0.95)',
                        titleColor: '#fff',
                        bodyColor: '#d1d5db',
                        borderColor: '#475569',
                        borderWidth: 1,
                        callbacks: {
                            title: function(items) {
                                if (items.length > 0) {
                                    const idx = items[0].dataIndex;
                                    return data.dates[idx];
                                }
                                return '';
                            },
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                if (label === 'KOSPI') {
                                    return `${label}: ${value?.toLocaleString() || '-'}`;
                                } else {
                                    return `${label}: ${value}%`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#6b7280',
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 12,
                            font: { size: 10 }
                        },
                        grid: { color: 'rgba(75,85,99,0.3)' }
                    },
                    'y-index': {
                        type: 'linear',
                        position: 'left',
                        title: {
                            display: true,
                            text: 'KOSPI',
                            color: '#3b82f6',
                            font: { size: 11 }
                        },
                        ticks: {
                            color: '#3b82f6',
                            font: { size: 10 },
                            callback: v => v.toLocaleString()
                        },
                        grid: { color: 'rgba(75,85,99,0.2)' }
                    },
                    'y-ratio': {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        max: 100,
                        title: {
                            display: true,
                            text: '하락비율(%)',
                            color: '#9ca3af',
                            font: { size: 11 }
                        },
                        ticks: {
                            color: '#9ca3af',
                            font: { size: 10 },
                            callback: v => v + '%'
                        },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });

        console.log('[loadMaRatioChart] 차트 생성 완료:', data.dates.length, '일치');

    } catch (error) {
        console.error('[loadMaRatioChart] 오류:', error);
        // 에러 시 빈 차트 표시
        ctx.fillStyle = '#6b7280';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('차트 데이터 로드 실패', canvas.width / 2, canvas.height / 2);
    }
}

// Breadth 데이터 초기화 (서버에서 수동 초기화 필요)
async function initBreadthData() {
    console.warn('[initBreadthData] Breadth 데이터가 없습니다. 서버에서 POST /api/market/breadth/init 를 실행해주세요.');
    // 데이터가 이미 VPS에 초기화되어 있으므로 재시도
    setTimeout(() => loadMaRatioChart(), 3000);
}

// ADR 차트 (쌍축 - KOSPI 지수 + ADR)
async function loadAdrChart() {
    const canvas = document.getElementById('adr-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // 기존 차트 제거
    if (window.adrChartInstance) {
        window.adrChartInstance.destroy();
    }

    try {
        // API에서 데이터 가져오기 (breadth-with-index에 ADR 포함)
        const data = await invokeWithTimeout('get_market_breadth_with_index', {
            accessToken: auth.accessToken || '',
            days: 250,
            market: 'KOSPI'
        }, 30000);

        console.log('[loadAdrChart] API 응답:', data);

        // 데이터 검증
        if (data.error || !data.dates || data.dates.length === 0 || !data.adr) {
            console.warn('[loadAdrChart] 데이터 없음');
            return;
        }

        // X축 레이블 (날짜)
        const labels = data.dates.map(d => {
            const date = new Date(d);
            return `${date.getMonth() + 1}/${date.getDate()}`;
        });

        // ADR 데이터 (null 제거)
        const adrData = data.adr.map(v => v != null ? v.toFixed(1) : null);

        window.adrChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'KOSPI',
                        data: data.index_values,
                        borderColor: '#3b82f6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.1,
                        fill: false,
                        yAxisID: 'y-index',
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: 'ADR',
                        data: adrData,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239,68,68,0.1)',
                        borderWidth: 1.5,
                        tension: 0.3,
                        fill: false,
                        yAxisID: 'y-adr',
                        pointRadius: 0,
                        pointHoverRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#9ca3af',
                            usePointStyle: true,
                            pointStyle: 'line',
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(30,41,59,0.95)',
                        titleColor: '#fff',
                        bodyColor: '#d1d5db',
                        borderColor: '#475569',
                        borderWidth: 1,
                        callbacks: {
                            title: function(items) {
                                if (items.length > 0) {
                                    const idx = items[0].dataIndex;
                                    return data.dates[idx];
                                }
                                return '';
                            },
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                if (label === 'KOSPI') {
                                    return `${label}: ${value?.toLocaleString() || '-'}`;
                                } else {
                                    return `${label}: ${value} (${value >= 100 ? '상승우세' : '하락우세'})`;
                                }
                            }
                        }
                    },
                    annotation: {
                        annotations: {
                            line100: {
                                type: 'line',
                                yMin: 100,
                                yMax: 100,
                                yScaleID: 'y-adr',
                                borderColor: '#6b7280',
                                borderWidth: 1,
                                borderDash: [5, 5],
                                label: {
                                    display: true,
                                    content: '100 기준',
                                    position: 'end'
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: '#6b7280',
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 12,
                            font: { size: 10 }
                        },
                        grid: { color: 'rgba(75,85,99,0.3)' }
                    },
                    'y-index': {
                        type: 'linear',
                        position: 'left',
                        title: {
                            display: true,
                            text: 'KOSPI',
                            color: '#3b82f6',
                            font: { size: 11 }
                        },
                        ticks: {
                            color: '#3b82f6',
                            font: { size: 10 },
                            callback: v => v.toLocaleString()
                        },
                        grid: { color: 'rgba(75,85,99,0.2)' }
                    },
                    'y-adr': {
                        type: 'linear',
                        position: 'right',
                        min: 40,
                        max: 200,
                        title: {
                            display: true,
                            text: 'ADR',
                            color: '#ef4444',
                            font: { size: 11 }
                        },
                        ticks: {
                            color: '#ef4444',
                            font: { size: 10 }
                        },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });

        console.log('[loadAdrChart] 차트 생성 완료');

    } catch (error) {
        console.error('[loadAdrChart] 오류:', error);
    }
}

// 추세유지 데이터 정렬 상태
let trendMaintainSortColumn = 'change';
let trendMaintainSortDir = 'desc';
let trendMaintainData = [];

// 추세유지 데이터 로드
async function loadTrendMaintainData() {
    const tbody = document.getElementById('trend-maintain-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="7" class="loading-cell">데이터 로딩 중...</td></tr>';

    try {
        // 추세유지 API 호출 (대표종목 RS는 DB 연동 후 추가)
        const response = await invokeWithTimeout('get_market_trend_maintain', { accessToken: auth.accessToken || '' }, 30000);
        console.log('[loadTrendMaintainData] response:', response);

        // API returns { success: true, data: [...] }
        const sectors = response?.data || [];
        if (!sectors || sectors.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">추세유지 데이터 없음</td></tr>';
            return;
        }

        // 데이터 필드명 매핑 (trend-maintain API -> sector-analysis 형식)
        trendMaintainData = sectors.map(s => ({
            sector: s.sector || '',
            etf_name: s.name || '',  // API returns 'name' as ETF name
            change_percent: s.change_percent || 0,
            position: s.position || '',
            position_days: s.days || 0,
            gap_percent: s.gap_percent || 0,
            signal: s.signal || 'green',
            top_holdings: s.top_holdings || [],  // 대표종목 + RS
        }));
        renderTrendMaintainTable();

        // 컬럼 헤더 정렬 이벤트
        document.querySelectorAll('#trend-maintain-table th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const sortKey = th.dataset.sort;
                if (trendMaintainSortColumn === sortKey) {
                    trendMaintainSortDir = trendMaintainSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    trendMaintainSortColumn = sortKey;
                    trendMaintainSortDir = 'desc';
                }
                renderTrendMaintainTable();
            });
        });
    } catch (error) {
        console.error('[loadTrendMaintainData] error:', error);
        tbody.innerHTML = `<tr><td colspan="7" class="error-cell">데이터 로드 실패: ${error?.message || error}</td></tr>`;
    }
}

// 추세유지 테이블 렌더링
function renderTrendMaintainTable() {
    const tbody = document.getElementById('trend-maintain-body');
    if (!tbody || !trendMaintainData.length) return;

    // 정렬
    const sorted = [...trendMaintainData].sort((a, b) => {
        let va, vb;
        switch (trendMaintainSortColumn) {
            case 'sector': va = a.sector || ''; vb = b.sector || ''; break;
            case 'change': va = a.change_percent || 0; vb = b.change_percent || 0; break;
            case 'days': va = (a.position === '유지' ? 1000 : 0) + (a.position_days || 0); vb = (b.position === '유지' ? 1000 : 0) + (b.position_days || 0); break;
            case 'gap': va = a.gap_percent || 0; vb = b.gap_percent || 0; break;
            default: va = 0; vb = 0;
        }
        if (typeof va === 'string') {
            return trendMaintainSortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        return trendMaintainSortDir === 'asc' ? va - vb : vb - va;
    });

    tbody.innerHTML = sorted.map(s => {
        const signalColor = {
            'green': '#22c55e',
            'yellow': '#fde047',
            'red': '#ef4444'
        }[s.signal] || '#6b7280';

        const positionClass = s.position === '유지' ? 'maintain' : 'depart';
        const gapClass = (s.gap_percent || 0) >= 0 ? 'positive' : 'negative';
        const changeClass = (s.change_percent || 0) >= 0 ? 'profit' : 'loss';

        // 대표종목(RS) 표시 - RS 90 이상 굵게 (최대 5개)
        const topHoldingsHtml = (s.top_holdings || []).slice(0, 5).map(stock => {
            const rs = stock.rs || 0;
            const rsClass = rs >= 90 ? 'rs-strong' : 'rs-normal';
            return `<span class="${rsClass}">${stock.name}(${rs})</span>`;
        }).join(', ');

        return `
            <tr>
                <td class="sector-name">${s.sector || ''}</td>
                <td class="etf-name">${s.etf_name || '-'}</td>
                <td class="change-cell ${changeClass}">${(s.change_percent || 0) >= 0 ? '+' : ''}${(s.change_percent || 0).toFixed(2)}%</td>
                <td class="position-cell ${positionClass}">${s.position || ''} ${s.position_days || 0}일</td>
                <td class="signal-cell"><span class="signal-dot" style="background:${signalColor}"></span></td>
                <td class="gap-cell ${gapClass}">${(s.gap_percent || 0) >= 0 ? '+' : ''}${(s.gap_percent || 0).toFixed(1)}%</td>
                <td class="top-stocks-cell">${topHoldingsHtml || '-'}</td>
            </tr>
        `;
    }).join('');
}

// 섹터 데이터 저장 (클릭 이벤트용)
let sectorDataCache = [];

// 섹터 데이터 로드
async function loadSectorData() {
    const leadingEl = document.getElementById('kr-leading-sectors');
    const weakEl = document.getElementById('kr-weak-sectors');
    if (!leadingEl || !weakEl) return;

    leadingEl.innerHTML = '<div class="loading-state">로딩 중...</div>';
    weakEl.innerHTML = '<div class="loading-state">로딩 중...</div>';

    try {
        const data = await invokeWithTimeout('get_market_sectors', { accessToken: auth.accessToken || '' }, 10000);
        console.log('[loadSectorData] data:', data);

        const sectors = data?.sectors || data || [];
        if (!sectors.length) {
            leadingEl.innerHTML = '<div class="empty-state">섹터 데이터 없음</div>';
            weakEl.innerHTML = '<div class="empty-state">섹터 데이터 없음</div>';
            return;
        }

        sectorDataCache = sectors;

        // 주도 섹터: 상승(양수)만 필터링 → 상승폭 큰 순
        const bullishSectors = sectors
            .filter(s => (s.change_percent || 0) > 0)
            .sort((a, b) => (b.change_percent || 0) - (a.change_percent || 0))
            .slice(0, 10);

        // 약세 섹터: 하락(음수)만 필터링 → 하락폭 큰 순
        const bearishSectors = sectors
            .filter(s => (s.change_percent || 0) < 0)
            .sort((a, b) => (a.change_percent || 0) - (b.change_percent || 0))
            .slice(0, 10);

        // 주도 섹터 렌더링
        if (bullishSectors.length === 0) {
            leadingEl.innerHTML = '<div class="empty-state all-down">오늘은 모든 섹터가 하락했습니다</div>';
        } else {
            leadingEl.innerHTML = bullishSectors.map((s, idx) => renderSectorItem(s, 'bullish', idx)).join('');
        }

        // 약세 섹터 렌더링
        if (bearishSectors.length === 0) {
            weakEl.innerHTML = '<div class="empty-state all-up">오늘은 모든 섹터가 상승했습니다</div>';
        } else {
            weakEl.innerHTML = bearishSectors.map((s, idx) => renderSectorItem(s, 'bearish', idx)).join('');
        }

        // 섹터 클릭 이벤트 추가
        attachSectorClickEvents();
    } catch (error) {
        console.error('[loadSectorData] error:', error);
        leadingEl.innerHTML = `<div class="error-state">${error?.message || error}</div>`;
        weakEl.innerHTML = '';
    }
}

// 섹터 항목 렌더링 (클릭 가능) - 이름 좌측, 등락률+화살표 우측
function renderSectorItem(s, type, idx) {
    const changeClass = (s.change_percent || 0) >= 0 ? 'profit' : 'loss';
    const sign = (s.change_percent || 0) >= 0 ? '+' : '';
    return `
        <div class="sector-item clickable" data-sector="${s.name}" data-type="${type}" data-idx="${idx}">
            <div class="sector-header">
                <span class="sector-name">${s.name}</span>
                <span class="sector-right">
                    <span class="sector-change ${changeClass}">${sign}${(s.change_percent || 0).toFixed(2)}%</span>
                    <span class="sector-arrow">▼</span>
                </span>
            </div>
            <div class="sector-detail" id="sector-detail-${type}-${idx}" style="display:none;"></div>
        </div>
    `;
}

// 섹터 거래대금 포맷 (백만원 → 억원)
function formatSectorTradingValue(val) {
    if (!val) return '-';
    const billions = val / 100;  // 백만원 → 억원
    if (billions >= 10000) {
        return (billions / 10000).toFixed(1) + '조';
    }
    return Math.round(billions).toLocaleString() + '억';
}

// 섹터 클릭 이벤트 연결
function attachSectorClickEvents() {
    document.querySelectorAll('.sector-item.clickable').forEach(el => {
        el.querySelector('.sector-header')?.addEventListener('click', async (e) => {
            const sectorName = el.dataset.sector;
            const type = el.dataset.type;
            const idx = el.dataset.idx;
            const detailEl = document.getElementById(`sector-detail-${type}-${idx}`);
            const arrow = el.querySelector('.sector-arrow');

            // 이미 열려있으면 닫기
            if (detailEl.style.display === 'block') {
                detailEl.style.display = 'none';
                arrow.textContent = '▼';
                el.classList.remove('expanded');
                return;
            }

            // 다른 열린 것들 닫기
            document.querySelectorAll('.sector-detail').forEach(d => d.style.display = 'none');
            document.querySelectorAll('.sector-arrow').forEach(a => a.textContent = '▼');
            document.querySelectorAll('.sector-item.clickable').forEach(i => i.classList.remove('expanded'));

            // 로딩 표시
            detailEl.innerHTML = '<div class="sector-detail-loading">로딩 중...</div>';
            detailEl.style.display = 'block';
            arrow.textContent = '▲';
            el.classList.add('expanded');

            // API 호출
            try {
                const resp = await invokeWithTimeout('get_market_sector_stocks', {
                    accessToken: auth.accessToken || '',
                    sectorName: sectorName
                }, 10000);

                if (resp?.success) {
                    detailEl.innerHTML = renderSectorDetail(resp, type);
                } else {
                    detailEl.innerHTML = '<div class="sector-detail-error">데이터 조회 실패</div>';
                }
            } catch (err) {
                console.error('[SectorDetail]', err);
                detailEl.innerHTML = `<div class="sector-detail-error">${err?.message || '오류 발생'}</div>`;
            }
        });
    });
}

// 섹터 상세 렌더링
function renderSectorDetail(data, type) {
    let html = '<div class="sector-detail-content">';

    if (type === 'bullish') {
        // 주도 섹터: 등락률 TOP + 거래대금 TOP
        if (data.top_gainers?.length) {
            html += '<div class="detail-section"><div class="detail-title">📈 등락률 TOP</div>';
            data.top_gainers.slice(0, 3).forEach((s, i) => {
                html += `<div class="detail-row"><span class="rank">${i+1}.</span> <span class="name">${s.name}</span> <span class="value profit">+${(s.change_percent || 0).toFixed(1)}%</span></div>`;
            });
            html += '</div>';
        }
        if (data.top_volume?.length) {
            html += '<div class="detail-section"><div class="detail-title">💰 거래대금 TOP</div>';
            data.top_volume.slice(0, 3).forEach((s, i) => {
                const vol = formatSectorTradingValue(s.trading_value || 0);
                html += `<div class="detail-row"><span class="rank">${i+1}.</span> <span class="name">${s.name}</span> <span class="value">${vol}</span></div>`;
            });
            html += '</div>';
        }
    } else {
        // 약세 섹터: 하락률 TOP
        if (data.top_losers?.length) {
            html += '<div class="detail-section"><div class="detail-title">📉 하락률 TOP</div>';
            data.top_losers.slice(0, 3).forEach((s, i) => {
                html += `<div class="detail-row"><span class="rank">${i+1}.</span> <span class="name">${s.name}</span> <span class="value loss">${(s.change_percent || 0).toFixed(1)}%</span></div>`;
            });
            html += '</div>';
        }
    }

    if (html === '<div class="sector-detail-content">') {
        html += '<div class="detail-empty">상세 데이터 없음</div>';
    }

    html += '</div>';
    return html;
}

// 해외시장 로드 (Phase 5: 국내시장과 동일 구조)
async function loadMarketUs() {
    const restrictionEl = document.getElementById('market-us-restriction');
    const contentEl = document.getElementById('market-us-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // Phase 5: Full US market data API
        const data = await invokeWithTimeout('get_market_us_full', {
            accessToken: auth.accessToken || ''
        }, 30000);

        console.log('[loadMarketUs] data:', data);

        if (!data || !data.success) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketUs()">다시 시도</button></div>';
            return;
        }

        // 데이터 추출
        const indices = data.indices || {};
        const sp500 = indices.sp500 || {};
        const nasdaq = indices.nasdaq || {};
        const dow = indices.dow || {};
        const russell = indices.russell || {};
        const vix = indices.vix || {};
        const fearGreed = data.fear_greed || {};
        const breadth = data.breadth || {};
        const heatmap = data.heatmap || [];
        const sectors = data.sectors || [];
        const signal = data.signal || {};
        const sp500Sig = signal.sp500 || {};
        const nasdaqSig = signal.nasdaq || {};

        // UI 렌더링 (StockEasy 스타일 - 국내시장과 동일)
        contentEl.innerHTML = `
            <!-- 시장신호 헤더 (1줄 통합) -->
            <div class="se-header-unified">
                <!-- 좌측: 시장신호 + 신호등 -->
                <div class="se-header-left">
                    <div class="se-signal-title" id="us-signal-toggle">
                        <span>시장신호</span>
                        <span class="toggle-arrow" id="us-signal-arrow">∧</span>
                    </div>
                    <div class="se-signal-lights">
                        <div class="se-signal-group">
                            <span class="se-signal-label">단기</span>
                            <div class="se-capsule" id="us-short-term-capsule">
                                <span class="se-dot" data-color="green"></span>
                                <span class="se-dot" data-color="yellow"></span>
                                <span class="se-dot" data-color="red"></span>
                            </div>
                        </div>
                        <div class="se-signal-group">
                            <span class="se-signal-label">장기</span>
                            <div class="se-capsule" id="us-long-term-capsule">
                                <span class="se-dot" data-color="green"></span>
                                <span class="se-dot" data-color="yellow"></span>
                                <span class="se-dot" data-color="red"></span>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- 중앙: 전체시장 상승/하락 -->
                <div style="text-align:center">
                    <div style="font-size:0.7em;color:#6b7280;margin-bottom:2px">전체 시장</div>
                    <div style="font-size:0.85em">
                        <span style="color:#22c55e">▲${data.rising_stocks || 0}</span>
                        <span style="color:#6b7280;margin:0 2px">·</span>
                        <span style="color:#ef4444">▼${data.falling_stocks || 0}</span>
                    </div>
                    <div style="display:flex;height:4px;margin-top:4px;border-radius:2px;overflow:hidden;width:100px">
                        <div style="flex:${data.rising_stocks || 0};background:#22c55e"></div>
                        <div style="flex:${data.falling_stocks || 0};background:#ef4444"></div>
                    </div>
                </div>
                <!-- 우측: S&P500 + NASDAQ 블록 -->
                <div class="se-header-right">
                    <!-- S&P 500: 게이지 포함 -->
                    <div class="se-index-block">
                        <div class="se-block-row1">
                            <span class="se-block-name">S&P 500</span>
                            <span class="se-block-pct ${(sp500.change_pct || 0) >= 0 ? 'up' : 'down'}">
                                ${(sp500.change_pct || 0) >= 0 ? '+' : ''}${(sp500.change_pct || 0).toFixed(2)}%
                            </span>
                        </div>
                        <div class="se-block-row2">
                            <span class="se-block-value">${sp500.value?.toLocaleString(undefined, {maximumFractionDigits: 2}) || '-'}</span>
                            <span class="se-block-amt ${(sp500.change || 0) >= 0 ? 'up' : 'down'}">
                                ${(sp500.change || 0) >= 0 ? '▲' : '▼'}${Math.abs(sp500.change || 0).toFixed(2)}
                            </span>
                        </div>
                    </div>
                    <!-- NASDAQ: 게이지 없이 가격 정보만 -->
                    <div class="se-index-block se-index-block-compact">
                        <div class="se-block-row1">
                            <span class="se-block-name">NASDAQ</span>
                            <span class="se-block-pct ${(nasdaq.change_pct || 0) >= 0 ? 'up' : 'down'}">
                                ${(nasdaq.change_pct || 0) >= 0 ? '+' : ''}${(nasdaq.change_pct || 0).toFixed(2)}%
                            </span>
                        </div>
                        <div class="se-block-row2">
                            <span class="se-block-value">${nasdaq.value?.toLocaleString(undefined, {maximumFractionDigits: 2}) || '-'}</span>
                            <span class="se-block-amt ${(nasdaq.change || 0) >= 0 ? 'up' : 'down'}">
                                ${(nasdaq.change || 0) >= 0 ? '▲' : '▼'}${Math.abs(nasdaq.change || 0).toFixed(2)}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 2행: S&P 500 히트맵 (줌 가능) -->
            <div class="card us-heatmap-card">
                <h3>S&P 500 히트맵</h3>
                <div class="us-heatmap-wrap" id="us-heatmap-wrap">
                    <div class="us-heatmap-grid" id="us-heatmap-grid"></div>
                    <div class="hm-zoom-controls">
                        <button class="hm-zoom-btn" id="hm-zoom-in" title="확대">+</button>
                        <button class="hm-zoom-btn" id="hm-zoom-out" title="축소">−</button>
                        <button class="hm-zoom-btn" id="hm-zoom-reset" title="초기화">⟲</button>
                    </div>
                </div>
            </div>

            <!-- 3행: Fear & Greed + VIX -->
            <div class="se-fgvix-section">
                <div class="se-fg-card card">
                    <h3>탐욕/공포 지수</h3>
                    <div class="se-fg-content">
                        <div class="se-fg-value" style="color: ${getFgColor(fearGreed.value)}">${fearGreed.value || 50}</div>
                        <div class="se-fg-label">${fearGreed.label || '중립'}</div>
                        <div class="se-fg-gauge">
                            <div class="se-fg-gauge-track">
                                <div class="se-fg-gauge-fill" style="width: ${fearGreed.value || 50}%; background: linear-gradient(90deg, #ef4444 0%, #fde047 50%, #22c55e 100%);"></div>
                                <div class="se-fg-gauge-pointer" style="left: ${fearGreed.value || 50}%"></div>
                            </div>
                            <div class="se-fg-gauge-labels">
                                <span>극심한 공포</span>
                                <span>중립</span>
                                <span>극심한 탐욕</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="se-vix-card card">
                    <h3>VIX (변동성 지수)</h3>
                    <div class="se-vix-content">
                        <div class="se-vix-value" style="color: ${getVixColor(vix.value)}">${(vix.value || 0).toFixed(2)}</div>
                        <div class="se-vix-change ${(vix.change_pct || 0) >= 0 ? 'up' : 'down'}">
                            ${(vix.change_pct || 0) >= 0 ? '+' : ''}${(vix.change_pct || 0).toFixed(2)}%
                        </div>
                        <div class="se-vix-status" style="background: ${getVixColor(vix.value)}20; color: ${getVixColor(vix.value)}; padding: 2px 8px; border-radius: 4px; font-size: 0.8em;">
                            ${getVixLabel(vix.value)}
                        </div>
                    </div>
                </div>
            </div>

            <!-- 4행: 다우존스 + 러셀2000 -->
            <div class="se-extra-indices card">
                <div class="se-extra-index">
                    <span class="se-extra-name">다우존스</span>
                    <span class="se-extra-value">${dow.value?.toLocaleString(undefined, {maximumFractionDigits: 2}) || '-'}</span>
                    <span class="se-extra-pct ${(dow.change_pct || 0) >= 0 ? 'up' : 'down'}">
                        ${(dow.change_pct || 0) >= 0 ? '+' : ''}${(dow.change_pct || 0).toFixed(2)}%
                    </span>
                </div>
                <div class="se-extra-divider">|</div>
                <div class="se-extra-index">
                    <span class="se-extra-name">러셀2000</span>
                    <span class="se-extra-value">${russell.value?.toLocaleString(undefined, {maximumFractionDigits: 2}) || '-'}</span>
                    <span class="se-extra-pct ${(russell.change_pct || 0) >= 0 ? 'up' : 'down'}">
                        ${(russell.change_pct || 0) >= 0 ? '+' : ''}${(russell.change_pct || 0).toFixed(2)}%
                    </span>
                </div>
            </div>

            <!-- 5행: 신호 설명 (접기 가능) -->
            <div class="se-signal-desc" id="us-signal-desc">
                <p>시장 신호는 신호등 색상으로 현재 시장의 상태를 나타냅니다: (🟢 양호, 🟡 주의, 🔴 매우주의).</p>
                <p>단기/장기 신호는 각각 단기적, 장기적 관점에서의 시장 흐름을 보여주는 지표입니다.</p>
            </div>

            <!-- 6행: 서브탭 (시장지표 | 섹터) -->
            <div class="se-subtabs" id="us-subtabs">
                <button class="se-subtab active" data-tab="us-market-indicators">시장지표</button>
                <button class="se-subtab" data-tab="us-sector">섹터</button>
            </div>

            <!-- 시장지표 탭 -->
            <div class="se-tab-content" id="tab-us-market-indicators">
                <!-- Big Picture 컴팩트 -->
                <div class="se-bigpicture-row card">
                    <div class="se-bp-item">
                        <span class="se-bp-market">S&P500</span>
                        <span class="se-bp-dot" id="bp-sp500-dot">●</span>
                        <span class="se-bp-status" id="bp-sp500-status">${sp500Sig.status_label || '확인된 상승세'}</span>
                        <span class="se-bp-exposure">(${sp500Sig.exposure || '80-100%'})</span>
                        <span class="se-bp-dd">DD:${sp500Sig.active_dd_count || 0}</span>
                        ${(sp500Sig.active_dd_count || 0) >= 3 ? '<span class="se-bp-warn">⚠️</span>' : ''}
                    </div>
                    <div class="se-bp-divider">|</div>
                    <div class="se-bp-item">
                        <span class="se-bp-market">NASDAQ</span>
                        <span class="se-bp-dot" id="bp-nasdaq-dot">●</span>
                        <span class="se-bp-status" id="bp-nasdaq-status">${nasdaqSig.status_label || '확인된 상승세'}</span>
                        <span class="se-bp-exposure">(${nasdaqSig.exposure || '80-100%'})</span>
                        <span class="se-bp-dd">DD:${nasdaqSig.active_dd_count || 0}</span>
                        ${(nasdaqSig.active_dd_count || 0) >= 3 ? '<span class="se-bp-warn">⚠️</span>' : ''}
                    </div>
                </div>

                <!-- 시장 브레드스 (Breadth) - Finviz 전체 시장 기준 -->
                <div class="se-breadth-card card">
                    <h3>시장 브레드스 (전체 시장)</h3>
                    <div class="se-breadth-grid">
                        <div class="se-breadth-item">
                            <span class="se-breadth-label">상승 / 하락</span>
                            <div class="se-breadth-bar">
                                <span class="up">${breadth.advancing || 0}</span>
                                <div class="se-breadth-bar-track">
                                    <div class="se-breadth-bar-up" style="width: ${getBreadthBarPercent(breadth.advancing, breadth.declining, 'up')}%"></div>
                                    <div class="se-breadth-bar-down" style="width: ${getBreadthBarPercent(breadth.advancing, breadth.declining, 'down')}%"></div>
                                </div>
                                <span class="down">${breadth.declining || 0}</span>
                            </div>
                        </div>
                        <div class="se-breadth-item">
                            <span class="se-breadth-label">신고가 / 신저가</span>
                            <div class="se-breadth-bar">
                                <span class="up">${breadth.new_high || 0}</span>
                                <div class="se-breadth-bar-track">
                                    <div class="se-breadth-bar-up" style="width: ${getBreadthBarPercent(breadth.new_high, breadth.new_low, 'up')}%"></div>
                                    <div class="se-breadth-bar-down" style="width: ${getBreadthBarPercent(breadth.new_high, breadth.new_low, 'down')}%"></div>
                                </div>
                                <span class="down">${breadth.new_low || 0}</span>
                            </div>
                        </div>
                        <div class="se-breadth-item">
                            <span class="se-breadth-label">SMA50 위 / 아래</span>
                            <div class="se-breadth-bar">
                                <span class="up">${breadth.above_sma50 || 0}</span>
                                <div class="se-breadth-bar-track">
                                    <div class="se-breadth-bar-up" style="width: ${getBreadthBarPercent(breadth.above_sma50, breadth.below_sma50, 'up')}%"></div>
                                    <div class="se-breadth-bar-down" style="width: ${getBreadthBarPercent(breadth.above_sma50, breadth.below_sma50, 'down')}%"></div>
                                </div>
                                <span class="down">${breadth.below_sma50 || 0}</span>
                            </div>
                        </div>
                        <div class="se-breadth-item">
                            <span class="se-breadth-label">SMA200 위 / 아래</span>
                            <div class="se-breadth-bar">
                                <span class="up">${breadth.above_sma200 || 0}</span>
                                <div class="se-breadth-bar-track">
                                    <div class="se-breadth-bar-up" style="width: ${getBreadthBarPercent(breadth.above_sma200, breadth.below_sma200, 'up')}%"></div>
                                    <div class="se-breadth-bar-down" style="width: ${getBreadthBarPercent(breadth.above_sma200, breadth.below_sma200, 'down')}%"></div>
                                </div>
                                <span class="down">${breadth.below_sma200 || 0}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 섹터 탭 -->
            <div class="se-tab-content" id="tab-us-sector" style="display:none;">
                <div class="card">
                    <h3>S&P 500 GICS 섹터 (11개)</h3>
                    <div class="us-sector-bars" id="us-sector-bars">
                        <!-- JS에서 렌더링 -->
                    </div>
                </div>
            </div>

        `;

        // 신호등 업데이트
        updateSignalCapsule('us-short-term-capsule', sp500Sig.short_term_signal || 'green');
        updateSignalCapsule('us-long-term-capsule', sp500Sig.long_term_signal || 'green');

        // Big Picture 색상 업데이트
        updateBigPictureDot('bp-sp500-dot', sp500Sig.status);
        updateBigPictureDot('bp-nasdaq-dot', nasdaqSig.status);

        // 히트맵 렌더링
        renderUsHeatmap(heatmap);

        // 섹터 바 차트 렌더링
        renderUsSectorBars(sectors);

        // 서브탭 이벤트
        document.querySelectorAll('#us-subtabs .se-subtab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('#us-subtabs .se-subtab').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                const tabId = e.target.dataset.tab;
                document.querySelectorAll('#market-us-content .se-tab-content').forEach(c => c.style.display = 'none');
                document.getElementById('tab-' + tabId).style.display = 'block';
            });
        });

        // 신호 접기/펴기
        document.getElementById('us-signal-toggle')?.addEventListener('click', () => {
            const desc = document.getElementById('us-signal-desc');
            const arrow = document.getElementById('us-signal-arrow');
            if (desc.style.display === 'none') {
                desc.style.display = 'block';
                arrow.textContent = '∧';
            } else {
                desc.style.display = 'none';
                arrow.textContent = '∨';
            }
        });

    } catch (error) {
        console.error('Market US error:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        contentEl.innerHTML = `<div class="error-state"><p>${errMsg}</p><button class="btn btn-sm btn-primary" onclick="loadMarketUs()">다시 시도</button></div>`;
    }
}

// 해외시장 게이지 퍼센트 계산
function getUsGaugePercent(data, type) {
    const rising = data.rising_stocks || 0;
    const falling = data.falling_stocks || 0;
    const unchanged = data.unchanged_stocks || 0;
    const total = rising + falling + unchanged;
    if (total === 0) return type === 'neutral' ? 100 : 0;
    if (type === 'up') return (rising / total * 100).toFixed(1);
    if (type === 'down') return (falling / total * 100).toFixed(1);
    return (unchanged / total * 100).toFixed(1);
}

// 히트맵 색상 (선명한 트레이딩뷰 스타일)
function getHeatmapColor(pct) {
    if (pct >= 3)    return '#1b5e20';
    if (pct >= 2)    return '#2e7d32';
    if (pct >= 1)    return '#388e3c';
    if (pct >= 0.5)  return '#2e7d32';
    if (pct >= 0.1)  return '#1b5e20';
    if (pct > -0.1)  return '#373d4e';
    if (pct > -0.5)  return '#5e2020';
    if (pct > -1)    return '#952020';
    if (pct > -2)    return '#b71c1c';
    if (pct > -3)    return '#c62828';
    return '#8b0000';
}

// 히트맵 텍스트 색상
function getHeatmapTextColor(pct) {
    if (Math.abs(pct) >= 2) return '#ffffff';
    return '#1f2937';
}

// ===== Squarified Treemap 알고리즘 =====

function squarify(data, x, y, w, h) {
    /**
     * Squarified Treemap 레이아웃 계산
     * data: [{value, ...}, ...] (value 내림차순 정렬 필수)
     * x, y, w, h: 배치 영역
     * returns: 각 data 요소에 x, y, w, h 속성 추가
     */
    if (!data.length) return;
    if (data.length === 1) {
        data[0].x = x;
        data[0].y = y;
        data[0].w = w;
        data[0].h = h;
        return;
    }

    const total = data.reduce((s, d) => s + d.value, 0);
    if (total <= 0) {
        data.forEach(d => { d.x = x; d.y = y; d.w = 0; d.h = 0; });
        return;
    }

    // 면적 정규화
    const area = w * h;
    data.forEach(d => d._area = (d.value / total) * area);

    _layoutRow(data, x, y, w, h);
}

function _layoutRow(data, x, y, w, h) {
    if (!data.length) return;
    if (data.length === 1) {
        data[0].x = x; data[0].y = y; data[0].w = w; data[0].h = h;
        return;
    }

    const isWide = w >= h;
    const side = isWide ? h : w;

    let row = [data[0]];
    let rowArea = data[0]._area;
    let worst = _worstRatio(row, side, rowArea);

    for (let i = 1; i < data.length; i++) {
        const newRow = [...row, data[i]];
        const newArea = rowArea + data[i]._area;
        const newWorst = _worstRatio(newRow, side, newArea);

        if (newWorst <= worst) {
            row = newRow;
            rowArea = newArea;
            worst = newWorst;
        } else {
            break;
        }
    }

    // row 배치
    const rowFraction = rowArea / (w * h) || 0;
    let rx, ry, rw, rh;
    if (isWide) {
        rw = w * rowFraction;
        rh = h;
        rx = x; ry = y;
    } else {
        rw = w;
        rh = h * rowFraction;
        rx = x; ry = y;
    }

    let offset = 0;
    row.forEach(d => {
        const frac = d._area / rowArea || 0;
        if (isWide) {
            d.x = rx;
            d.y = ry + offset;
            d.w = rw;
            d.h = rh * frac;
            offset += d.h;
        } else {
            d.x = rx + offset;
            d.y = ry;
            d.w = rw * frac;
            d.h = rh;
            offset += d.w;
        }
    });

    // 나머지 재귀
    const remaining = data.slice(row.length);
    if (remaining.length > 0) {
        if (isWide) {
            _layoutRow(remaining, x + rw, y, w - rw, h);
        } else {
            _layoutRow(remaining, x, y + rh, w, h - rh);
        }
    }
}

function _worstRatio(row, side, totalArea) {
    if (!row.length || totalArea <= 0 || side <= 0) return Infinity;
    const rowLen = totalArea / side;
    let worst = 0;
    for (const d of row) {
        const nodeLen = d._area / rowLen || 0;
        if (nodeLen <= 0) continue;
        const ratio = Math.max(rowLen / nodeLen, nodeLen / rowLen);
        if (ratio > worst) worst = ratio;
    }
    return worst;
}


// ===== 히트맵 렌더링 (Squarified Treemap) =====

function renderUsHeatmap(heatmap) {
    const grid = document.getElementById('us-heatmap-grid');
    const wrap = document.getElementById('us-heatmap-wrap');
    if (!grid || !wrap || !heatmap.length) return;

    const W = wrap.clientWidth || 800;
    const H = 410;

    // 섹터별 그룹핑 + squarify
    const sectorMap = {};
    heatmap.forEach(s => {
        const sec = s.sector || '기타';
        if (!sectorMap[sec]) sectorMap[sec] = { name: sec, stocks: [], totalCap: 0 };
        sectorMap[sec].stocks.push(s);
        sectorMap[sec].totalCap += (s.market_cap || 1);
    });

    const sectors = Object.values(sectorMap)
        .map(s => ({ ...s, value: s.totalCap }))
        .sort((a, b) => b.value - a.value);

    squarify(sectors, 0, 0, W, H);

    sectors.forEach(sector => {
        const stocks = sector.stocks
            .map(s => ({ ...s, value: s.market_cap || 1 }))
            .sort((a, b) => b.value - a.value);
        const labelH = 12;
        squarify(stocks, sector.x, sector.y + labelH, sector.w, Math.max(sector.h - labelH, 0));
        sector._layoutStocks = stocks;
    });

    // 초기 렌더링 (한 번만)
    let html = '';
    sectors.forEach(sector => {
        html += `<div class="hm-sector-box" style="left:${sector.x}px;top:${sector.y}px;width:${sector.w}px;height:${sector.h}px">`;
        if (sector.w > 40 && sector.h > 20) {
            const lblSize = Math.max(Math.min(Math.round(sector.w * 0.06), 16), 9);
            html += `<div class="hm-sector-lbl" style="font-size:${lblSize}px">${sector.name}</div>`;
        }
        html += '</div>';

        (sector._layoutStocks || []).forEach(s => {
            if (!s.w || !s.h || s.w < 1 || s.h < 1) return;
            const pct = s.change_pct || 0;
            const bg = getHeatmapColor(pct);
            const tooltip = `${s.name || s.symbol} (${s.symbol})\n${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
            const minDim = Math.min(s.w, s.h);
            const symPx = Math.max(Math.min(Math.round(minDim * 0.28), 36), 3);
            const pctPx = Math.max(Math.round(symPx * 0.72), 3);

            html += `<div class="hm-cell" style="left:${s.x.toFixed(1)}px;top:${s.y.toFixed(1)}px;width:${s.w.toFixed(1)}px;height:${s.h.toFixed(1)}px;background:${bg}" title="${tooltip}" data-minw="${s.w}" data-minh="${s.h}">`;
            html += `<span class="hm-sym" style="font-size:${symPx}px">${s.symbol}</span>`;
            html += `<span class="hm-pct" style="font-size:${pctPx}px">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span>`;
            html += '</div>';
        });
    });

    grid.style.width = W + 'px';
    grid.style.height = H + 'px';
    grid.innerHTML = html;

    // === 줌 & 패닝 ===
    const newWrap = wrap.cloneNode(false);
    while (wrap.firstChild) newWrap.appendChild(wrap.firstChild);
    wrap.parentNode.replaceChild(newWrap, wrap);
    newWrap.id = 'us-heatmap-wrap';

    let scale = 1, panX = 0, panY = 0;
    let isPanning = false, startX, startY;
    let updatePending = false;

    function applyTransform() {
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    }

    // 폰트만 업데이트 (innerHTML 재생성 없음)
    function updateFonts(sc) {
        const g = document.getElementById('us-heatmap-grid');
        if (!g) return;
        const cells = g.querySelectorAll('.hm-cell');
        cells.forEach(cell => {
            const minW = parseFloat(cell.dataset.minw) || 10;
            const minH = parseFloat(cell.dataset.minh) || 10;
            const visMin = Math.min(minW, minH) * sc;
            const symVisPx = Math.max(Math.min(Math.round(visMin * 0.28), 36), 3);
            const pctVisPx = Math.max(Math.round(symVisPx * 0.72), 3);
            const symEl = cell.querySelector('.hm-sym');
            const pctEl = cell.querySelector('.hm-pct');
            if (symEl) {
                symEl.style.fontSize = (symVisPx / sc) + 'px';
                symEl.style.display = visMin >= 14 ? '' : 'none';
            }
            if (pctEl) {
                pctEl.style.fontSize = (pctVisPx / sc) + 'px';
                pctEl.style.display = visMin >= 28 ? '' : 'none';
            }
        });
    }

    function scheduleUpdate() {
        if (updatePending) return;
        updatePending = true;
        requestAnimationFrame(() => {
            updateFonts(scale);
            updatePending = false;
        });
    }

    newWrap.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.2 : 0.2;
        const newScale = Math.min(Math.max(scale + delta, 1), 5);
        const rect = newWrap.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const ratio = newScale / scale;
        panX = mouseX - ratio * (mouseX - panX);
        panY = mouseY - ratio * (mouseY - panY);
        scale = newScale;
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transition = 'none';
        applyTransform();
        scheduleUpdate();
    }, { passive: false });

    newWrap.addEventListener('mousedown', (e) => {
        if (scale <= 1) return;
        isPanning = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
        newWrap.style.cursor = 'grabbing';
        e.preventDefault();
    });
    newWrap.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transition = 'none';
        applyTransform();
    });
    newWrap.addEventListener('mouseup', () => {
        isPanning = false;
        newWrap.style.cursor = scale > 1 ? 'grab' : 'default';
    });
    newWrap.addEventListener('mouseleave', () => { isPanning = false; });

    document.getElementById('hm-zoom-in')?.addEventListener('click', (e) => {
        e.stopPropagation();
        scale = Math.min(scale + 0.4, 5);
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transition = 'transform 0.15s';
        applyTransform();
        scheduleUpdate();
    });
    document.getElementById('hm-zoom-out')?.addEventListener('click', (e) => {
        e.stopPropagation();
        scale = Math.max(scale - 0.4, 1);
        if (scale === 1) { panX = 0; panY = 0; }
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transition = 'transform 0.15s';
        applyTransform();
        scheduleUpdate();
    });
    document.getElementById('hm-zoom-reset')?.addEventListener('click', (e) => {
        e.stopPropagation();
        scale = 1; panX = 0; panY = 0;
        const g = document.getElementById('us-heatmap-grid');
        if (g) g.style.transition = 'transform 0.2s';
        applyTransform();
        scheduleUpdate();
    });
}

// Fear & Greed 색상
function getFgColor(val) {
    if (val >= 75) return '#22c55e';     // 극심한 탐욕 - 초록
    if (val >= 55) return '#86efac';     // 탐욕 - 연초록
    if (val >= 45) return '#fde047';     // 중립 - 노랑
    if (val >= 25) return '#fb923c';     // 공포 - 주황
    return '#ef4444';                     // 극심한 공포 - 빨강
}

// VIX 색상
function getVixColor(val) {
    if (val < 15) return '#22c55e';      // 매우 낮음 - 초록
    if (val < 20) return '#86efac';      // 낮음 - 연초록
    if (val < 25) return '#fde047';      // 보통 - 노랑
    if (val < 30) return '#fb923c';      // 높음 - 주황
    return '#ef4444';                     // 매우 높음 - 빨강
}

// VIX 라벨
function getVixLabel(val) {
    if (val < 15) return '매우 안정';
    if (val < 20) return '안정';
    if (val < 25) return '보통';
    if (val < 30) return '불안';
    return '극도 불안';
}

// 브레드스 바 퍼센트 (신고가/신저가 비율)
function getBreadthBarPercent(high, low, type) {
    const total = (high || 0) + (low || 0);
    if (total === 0) return 50;
    if (type === 'up') return ((high || 0) / total * 100).toFixed(1);
    return ((low || 0) / total * 100).toFixed(1);
}

// 섹터 바 차트 렌더링
function renderUsSectorBars(sectors) {
    const container = document.getElementById('us-sector-bars');
    if (!container) return;

    if (!sectors || sectors.length === 0) {
        container.innerHTML = '<div class="empty-state">섹터 데이터 없음</div>';
        return;
    }

    // 등락률 기준 정렬 (내림차순)
    const sorted = [...sectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
    const maxAbs = Math.max(...sorted.map(s => Math.abs(s.change_pct || 0)), 1);

    container.innerHTML = sorted.map(sector => {
        const pct = sector.change_pct || 0;
        const barWidth = Math.abs(pct) / maxAbs * 100;
        const barColor = pct >= 0 ? '#22c55e' : '#ef4444';
        const direction = pct >= 0 ? 'right' : 'left';

        return `
            <div class="us-sector-bar-item">
                <div class="us-sector-bar-name">${sector.name} (${sector.symbol})</div>
                <div class="us-sector-bar-track">
                    <div class="us-sector-bar-fill ${direction}" style="width: ${barWidth}%; background: ${barColor};"></div>
                </div>
                <div class="us-sector-bar-pct ${pct >= 0 ? 'up' : 'down'}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</div>
            </div>
        `;
    }).join('');
}

// 해외 추세유지 데이터 로드
async function loadUsTrendMaintainData() {
    const tbody = document.getElementById('us-trend-maintain-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">데이터 로딩 중...</td></tr>';

    try {
        const data = await invokeWithTimeout('get_market_us_trend_maintain', {
            accessToken: auth.accessToken || ''
        }, 30000);

        console.log('[loadUsTrendMaintainData] data:', data);

        if (!data || !data.success || !data.data) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
            return;
        }

        const items = data.data || [];
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">추세유지 데이터 없음</td></tr>';
            return;
        }

        tbody.innerHTML = items.map(item => {
            const changeClass = (item.change_pct || 0) >= 0 ? 'profit' : 'loss';
            const positionClass = item.position === '유지' ? 'position-maintain' : 'position-break';
            const gapClass = (item.gap_percent || 0) >= 0 ? 'profit' : 'loss';
            const signalDot = item.signal === 'green' ? '🟢' : (item.signal === 'yellow' ? '🟡' : '🔴');

            return `
                <tr>
                    <td class="sector-name">${item.sector || '-'}</td>
                    <td class="etf-name">${item.etf || '-'}</td>
                    <td class="change-cell ${changeClass}">${(item.change_pct || 0) >= 0 ? '+' : ''}${(item.change_pct || 0).toFixed(2)}%</td>
                    <td class="position-cell ${positionClass}">${item.position || '-'} ${item.days || 0}일</td>
                    <td class="signal-cell">${signalDot}</td>
                    <td class="gap-cell ${gapClass}">${(item.gap_percent || 0) >= 0 ? '+' : ''}${(item.gap_percent || 0).toFixed(1)}%</td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error('US Trend Maintain error:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">데이터 로드 실패</td></tr>';
    }
}

// [BUG FIX 6] ETF 로드 - 스탁이지 수준 개선
// ===== Phase 6: 시장분석 ETF — ETFCheck 수준 =====
async function loadMarketEtf() {
    const restrictionEl = document.getElementById('market-etf-restriction');
    const contentEl = document.getElementById('market-etf-content');
    if (!restrictionEl || !contentEl) return;

    if (!auth.user && auth.accessToken) await loadUserInfo();
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">ETF 데이터 로딩 중...</div>';

    try {
        const data = await invokeWithTimeout('get_market_etf', {
            accessToken: auth.accessToken || ''
        }, 15000);

        if (!data || !data.success) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketEtf()">다시 시도</button></div>';
            return;
        }

        renderEtfDashboard(data, contentEl);

    } catch (error) {
        console.error('Market ETF error:', error);
        contentEl.innerHTML = `<div class="error-state"><p>${error.message || '알 수 없는 오류'}</p><button class="btn btn-sm btn-primary" onclick="loadMarketEtf()">다시 시도</button></div>`;
    }
}

function renderEtfDashboard(data, container) {
    const totalUp = data.total_up || 0;
    const totalDown = data.total_down || 0;
    const totalCount = data.total_count || 0;
    const unchanged = totalCount - totalUp - totalDown;

    container.innerHTML = `
        <!-- 시장 개요 -->
        <div class="etf-overview-header card">
            <div class="etf-overview-row">
                <div class="etf-stat">
                    <span class="etf-stat-label">전체 종목</span>
                    <span class="etf-stat-value">${totalCount.toLocaleString()}</span>
                </div>
                <div class="etf-stat">
                    <span class="etf-stat-label">상승</span>
                    <span class="etf-stat-value" style="color:#ef4444">▲${totalUp}</span>
                </div>
                <div class="etf-stat">
                    <span class="etf-stat-label">하락</span>
                    <span class="etf-stat-value" style="color:#3b82f6">▼${totalDown}</span>
                </div>
                <div class="etf-stat">
                    <span class="etf-stat-label">보합</span>
                    <span class="etf-stat-value" style="color:#6b7280">${unchanged}</span>
                </div>
            </div>
        </div>

        <!-- 1. HOT 테마 (국내) -->
        <div class="card" id="etf-hot-section">
            <div class="etf-section-header">
                <h3>HOT 테마</h3>
                <div class="etf-toggle-btns" id="etf-theme-toggle">
                    <button class="etf-toggle-btn active" data-mode="up">상승</button>
                    <button class="etf-toggle-btn" data-mode="down">하락</button>
                </div>
            </div>
            <div class="etf-theme-scroll" id="etf-theme-cards"></div>
        </div>

        <!-- 2. 상승하락 (ETFCheck: 상승하락 | TOP3거래량) -->
        <div class="card">
            <div class="etf-main-tabs" id="etf-dist-main-tabs">
                <button class="etf-main-tab active" data-tab="dist">상승하락</button>
                <button class="etf-main-tab" data-tab="top3vol">TOP3거래량</button>
            </div>
            <div class="etf-sub-tabs" id="etf-dist-sub-tabs">
                <button class="etf-sub-tab active" data-asset="전체">전체</button>
                <button class="etf-sub-tab" data-asset="주식">주식</button>
                <button class="etf-sub-tab" data-asset="채권">채권</button>
                <button class="etf-sub-tab" data-asset="원자재">원자재</button>
            </div>
            <div id="etf-dist-content"></div>
        </div>

        <!-- 3. 랭킹 TOP 10 (ETFCheck: 수익률 | 거래량 | 순자산총액) -->
        <div class="card">
            <h3>랭킹 TOP 10</h3>
            <div class="etf-main-tabs" id="etf-rank-main-tabs">
                <button class="etf-main-tab active" data-tab="return">수익률</button>
                <button class="etf-main-tab" data-tab="volume">거래량</button>
                <button class="etf-main-tab" data-tab="asset-total">순자산총액</button>
            </div>
            <div class="etf-sub-tabs" id="etf-rank-sub-tabs">
                <button class="etf-sub-tab active" data-asset="전체">전체</button>
                <button class="etf-sub-tab" data-asset="주식">주식</button>
                <button class="etf-sub-tab" data-asset="채권">채권</button>
                <button class="etf-sub-tab" data-asset="원자재">원자재</button>
            </div>
            <div class="etf-toggle-btns" id="etf-rank-toggle" style="margin:8px 0">
                <button class="etf-toggle-btn active" data-mode="up">상승</button>
                <button class="etf-toggle-btn" data-mode="down">하락</button>
            </div>
            <div id="etf-rank-list"></div>
        </div>

        <!-- 4. 주요 종목현황 (ETFCheck: 전체|주식|채권|원자재 + 현재가|시세|거래량|자금유입) -->
        <div class="card">
            <h3>주요 종목현황</h3>
            <div class="etf-sub-tabs" id="etf-major-asset-tabs">
                <button class="etf-sub-tab active" data-asset="전체">전체</button>
                <button class="etf-sub-tab" data-asset="주식">주식</button>
                <button class="etf-sub-tab" data-asset="채권">채권</button>
                <button class="etf-sub-tab" data-asset="원자재">원자재</button>
            </div>
            <div class="etf-main-tabs" id="etf-major-sort-tabs" style="margin-top:8px">
                <button class="etf-main-tab active" data-sort="price">현재가</button>
                <button class="etf-main-tab" data-sort="change">시세</button>
                <button class="etf-main-tab" data-sort="volume">거래량</button>
            </div>
            <div id="etf-major-list"></div>
        </div>
    `;

    // ========== 1. HOT 테마 ==========
    function renderThemeCards(mode) {
        const el = document.getElementById('etf-theme-cards');
        const themes = mode === 'up' ? (data.themes_up || []) : (data.themes_down || []);
        if (!el) return;
        if (!themes.length) { el.innerHTML = '<div class="empty-cell">테마 데이터 없음</div>'; return; }

        el.innerHTML = themes.slice(0, 15).map((t, i) => {
            const isUp = t.avg_change >= 0;
            const color = isUp ? '#ef4444' : '#3b82f6';  // 상승=빨강, 하락=파랑
            const rankColors = ['#ef4444', '#f59e0b', '#22c55e', '#06b6d4', '#8b5cf6', '#ec4899', '#f97316', '#14b8a6'];
            return `
                <div class="etf-theme-card">
                    <div class="etf-theme-card-header">
                        <span class="etf-theme-name">${t.name}</span>
                        <span class="etf-theme-rank" style="background:${rankColors[i % rankColors.length]}">${i + 1}</span>
                    </div>
                    <div class="etf-theme-change" style="color:${color}">${isUp ? '+' : ''}${t.avg_change.toFixed(2)}%</div>
                    <div class="etf-theme-top">
                        <span class="etf-theme-top-name">${t.top_etf_name || '-'}</span>
                        <span style="color:${color}">${(t.top_etf_change || 0) >= 0 ? '+' : ''}${(t.top_etf_change || 0).toFixed(2)}%</span>
                    </div>
                    <div class="etf-theme-bar">
                        <div style="flex:${t.down || 1};background:#3b82f6;height:100%"></div>
                        <div style="flex:${t.up || 1};background:#ef4444;height:100%"></div>
                    </div>
                    <div class="etf-theme-counts">
                        <span style="color:#3b82f6">하락/${t.down || 0}</span>
                        <span style="color:#ef4444">${t.up || 0}/상승</span>
                    </div>
                </div>
            `;
        }).join('');
    }
    renderThemeCards('up');

    document.querySelectorAll('#etf-theme-toggle .etf-toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#etf-theme-toggle .etf-toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderThemeCards(btn.dataset.mode);
        });
    });

    // ========== 2. 상승하락 분포 ==========
    let distMainTab = 'dist';
    let distAsset = '전체';

    function renderDistribution() {
        const contentEl = document.getElementById('etf-dist-content');
        if (!contentEl) return;

        if (distMainTab === 'dist') {
            // 히스토그램 (ETFCheck 11개 빈)
            const bins = (data.dist_by_asset || {})[distAsset] || [0,0,0,0,0,0,0,0,0,0,0];
            const labels = ['-10%~', '-10~-5%', '-5~-3%', '-3~-1%', '-1~0%', '0', '0~1%', '1~3%', '3~5%', '5~10%', '10%~'];
            const maxVal = Math.max(...bins, 1);
            const totalInAsset = bins.reduce((a, b) => a + b, 0);
            // 하락: 0~4 (5개), 보합: 5 (1개), 상승: 6~10 (5개)
            const downCount = bins[0] + bins[1] + bins[2] + bins[3] + bins[4];
            const unchCount = bins[5];
            const upCount = bins[6] + bins[7] + bins[8] + bins[9] + bins[10];

            contentEl.innerHTML = `
                <div class="etf-total-label">전체 종목수 : <strong>${totalInAsset}</strong></div>
                <div class="etf-distribution">
                    ${bins.map((count, i) => {
                        const heightPx = Math.max(Math.round((count / maxVal) * 200), 4);
                        let color = '#6b7280';
                        if (i <= 4) color = '#3b82f6';
                        else if (i === 5) color = '#9ca3af';
                        else color = '#ef4444';
                        return `
                            <div class="etf-dist-bar-wrap">
                                <span class="etf-dist-count" style="color:${color}">${count}</span>
                                <div class="etf-dist-bar" style="height:${heightPx}px;background:${color}"></div>
                                <span class="etf-dist-label">${labels[i]}</span>
                            </div>
                        `;
                    }).join('')}
                </div>
                <div class="etf-dist-ratio-bar">
                    <div style="flex:${downCount || 1};background:#3b82f6;height:100%;border-radius:3px 0 0 3px"></div>
                    <div style="flex:${unchCount || 1};background:#fbbf24;height:100%"></div>
                    <div style="flex:${upCount || 1};background:#ef4444;height:100%;border-radius:0 3px 3px 0"></div>
                </div>
                <div class="etf-dist-summary">
                    <span style="color:#3b82f6">하락종목 / ${downCount}</span>
                    <span style="color:#fbbf24">${unchCount}</span>
                    <span style="color:#ef4444">${upCount} / 상승종목</span>
                </div>
            `;
        } else if (distMainTab === 'top3vol') {
            const top3 = data.top3_volume || [];
            const colors = ['#4ade80', '#60a5fa', '#fbbf24'];
            contentEl.innerHTML = `
                <div style="font-size:0.82em;color:#6b7280;margin-bottom:12px">
                    거래량 증가 TOP3 종목의 현황입니다.
                </div>
                <div class="etf-top3-list">
                    ${top3.map((e, i) => {
                        const isUp = (e.change_pct || 0) >= 0;
                        return `
                            <div class="etf-top3-item" style="border-left:3px solid ${colors[i]}">
                                <div style="display:flex;align-items:center;gap:8px">
                                    <span style="color:${colors[i]};font-size:0.8em">●</span>
                                    <strong>${e.name}</strong>
                                </div>
                                <div style="display:flex;gap:16px;margin-top:6px;font-size:0.88em">
                                    <span style="color:#9ca3af">현재가 ${(e.price||0).toLocaleString()}</span>
                                    <span class="${isUp?'profit':'loss'}">${isUp?'+':''}${(e.change_pct||0).toFixed(2)}%</span>
                                    <span style="color:#9ca3af">거래량 ${(e.volume||0).toLocaleString()}</span>
                                </div>
                            </div>
                        `;
                    }).join('') || '<div class="empty-cell">데이터 없음</div>'}
                </div>
            `;
        }
    }
    renderDistribution();

    document.querySelectorAll('#etf-dist-main-tabs .etf-main-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-dist-main-tabs .etf-main-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            distMainTab = tab.dataset.tab;
            renderDistribution();
        });
    });
    document.querySelectorAll('#etf-dist-sub-tabs .etf-sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-dist-sub-tabs .etf-sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            distAsset = tab.dataset.asset;
            renderDistribution();
        });
    });

    // ========== 3. 랭킹 TOP 10 ==========
    let rankMainTab = 'return';
    let rankAsset = '전체';
    let rankMode = 'up';

    function rankItemHtml(e, i, tab) {
        const isUp = (e.change_pct || 0) >= 0;
        const cls = isUp ? 'profit' : 'loss';
        const navStr = e.nav ? e.nav.toLocaleString() : '';

        let rightContent = '';
        if (tab === 'asset-total') {
            // 순자산총액 탭: 시총 표시
            const marketStr = e.market_sum ? (e.market_sum >= 100000000
                ? (e.market_sum / 100000000).toFixed(0) + '억'
                : e.market_sum.toLocaleString()) : '-';
            rightContent = `<span style="font-weight:700">${marketStr}</span>`;
        } else if (tab === 'volume') {
            // 거래량 탭: 거래량 표시
            rightContent = `<span style="font-weight:700">${(e.volume || 0).toLocaleString()}</span>`;
        } else {
            // 수익률 탭: 등락률 표시
            rightContent = `<span class="${cls}" style="font-weight:700">${isUp ? '+' : ''}${(e.change_pct || 0).toFixed(2)}%</span>`;
        }
        return `
            <div class="etf-rank-item">
                <span class="etf-rank-num">${i + 1}</span>
                <div class="etf-rank-info">
                    <strong>${e.name || '-'}</strong>
                    <span style="color:#6b7280;font-size:0.82em">현재가 ${(e.price || 0).toLocaleString()}</span>
                </div>
                ${navStr ? `<div style="color:#6b7280;font-size:0.82em;min-width:90px;text-align:center">iNAV ${navStr}</div>` : ''}
                <div class="etf-rank-change">${rightContent}</div>
            </div>
        `;
    }

    function renderRankList() {
        const el = document.getElementById('etf-rank-list');
        const toggleEl = document.getElementById('etf-rank-toggle');
        if (!el) return;

        // 상승/하락 토글은 수익률 탭에서만
        if (toggleEl) toggleEl.style.display = rankMainTab === 'return' ? 'flex' : 'none';

        let items = [];
        if (rankMainTab === 'return') {
            const src = rankMode === 'up' ? (data.top_return_by_asset || {}) : (data.bottom_return_by_asset || {});
            items = src[rankAsset] || [];
        } else if (rankMainTab === 'volume') {
            items = (data.top_volume_by_asset || {})[rankAsset] || [];
        } else if (rankMainTab === 'asset-total') {
            items = (data.top_market_by_asset || {})[rankAsset] || [];
        }

        const first5 = items.slice(0, 5);
        const rest5 = items.slice(5, 10);

        el.innerHTML = first5.map((e, i) => rankItemHtml(e, i, rankMainTab)).join('')
            + (rest5.length > 0 ? `
                <div id="etf-rank-more" style="display:none">
                    ${rest5.map((e, i) => rankItemHtml(e, i + 5, rankMainTab)).join('')}
                </div>
                <div class="etf-more-btn-wrap">
                    <button class="etf-more-btn" id="etf-rank-more-btn">더보기 ∨</button>
                </div>
            ` : '')
            || '<div class="empty-cell">데이터 없음</div>';

        // 더보기 버튼 이벤트
        const moreBtn = document.getElementById('etf-rank-more-btn');
        if (moreBtn) {
            moreBtn.addEventListener('click', () => {
                const moreEl = document.getElementById('etf-rank-more');
                if (moreEl) {
                    const isHidden = moreEl.style.display === 'none';
                    moreEl.style.display = isHidden ? 'block' : 'none';
                    moreBtn.textContent = isHidden ? '접기 ∧' : '더보기 ∨';
                }
            });
        }
    }
    renderRankList();

    document.querySelectorAll('#etf-rank-main-tabs .etf-main-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-rank-main-tabs .etf-main-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            rankMainTab = tab.dataset.tab;
            renderRankList();
        });
    });
    document.querySelectorAll('#etf-rank-sub-tabs .etf-sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-rank-sub-tabs .etf-sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            rankAsset = tab.dataset.asset;
            renderRankList();
        });
    });
    document.querySelectorAll('#etf-rank-toggle .etf-toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#etf-rank-toggle .etf-toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            rankMode = btn.dataset.mode;
            renderRankList();
        });
    });

    // ========== 4. 주요 종목현황 ==========
    let majorAsset = '전체';
    let majorSort = 'price';

    function majorItemHtml(e) {
        const isUp = (e.change_pct || 0) >= 0;
        const cls = isUp ? 'profit' : 'loss';
        const lineColor = isUp ? '#ef4444' : '#3b82f6';
        const fillColor = isUp ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.15)';

        let chartHtml = '';
        const prices = e.sparkline || [];
        if (prices.length >= 2) {
            const w = 160, h = 36;
            const min = Math.min(...prices);
            const max = Math.max(...prices);
            const range = max - min || 1;

            const points = prices.map((p, i) => {
                const x = (i / (prices.length - 1)) * w;
                const y = h - ((p - min) / range) * (h - 4) - 2;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            });

            const polyline = points.join(' ');
            const fillPoints = `0,${h} ${polyline} ${w},${h}`;

            chartHtml = `
                <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
                    <polygon points="${fillPoints}" fill="${fillColor}" />
                    <polyline points="${polyline}" fill="none" stroke="${lineColor}" stroke-width="1.5" />
                </svg>
            `;
        }

        return `
            <div class="etf-major-item">
                <div class="etf-major-name">${e.name || '-'}</div>
                <div class="etf-major-chart">${chartHtml}</div>
                <div class="etf-major-right">
                    <span class="etf-major-price">${(e.price || 0).toLocaleString()}</span>
                    <span class="etf-major-change ${cls}">${isUp ? '+' : ''}${(e.change_pct || 0).toFixed(2)}%</span>
                </div>
            </div>
        `;
    }

    function renderMajorList() {
        const el = document.getElementById('etf-major-list');
        if (!el) return;

        let items = [];
        if (data.major_by_asset && data.major_by_asset[majorAsset]) {
            items = data.major_by_asset[majorAsset];
        } else if (majorAsset === '전체') {
            items = data.major_etfs || [];
        } else {
            items = (data.major_etfs || []).filter(e => e.asset_type === majorAsset);
        }

        // 중복 제거
        const seen = new Set();
        items = items.filter(e => {
            if (seen.has(e.code)) return false;
            seen.add(e.code);
            return true;
        });

        // 정렬 (원본 변경 방지)
        if (majorSort === 'volume') {
            items = [...items].sort((a, b) => (b.volume || 0) - (a.volume || 0));
        } else if (majorSort === 'change') {
            items = [...items].sort((a, b) => Math.abs(b.change_pct || 0) - Math.abs(a.change_pct || 0));
        } else {
            items = [...items];
        }

        const first5 = items.slice(0, 5);
        const rest = items.slice(5, 15);

        el.innerHTML = `
            <div class="etf-major-header">
                <span>종목</span>
                <span>현재가</span>
            </div>
        ` + first5.map(e => majorItemHtml(e)).join('')
        + (rest.length > 0 ? `
            <div id="etf-major-more" style="display:none">
                ${rest.map(e => majorItemHtml(e)).join('')}
            </div>
            <div class="etf-more-btn-wrap">
                <button class="etf-more-btn" id="etf-major-more-btn">더보기 ∨</button>
            </div>
        ` : '')
        || '<div class="empty-cell">데이터 없음</div>';

        const majorMoreBtn = document.getElementById('etf-major-more-btn');
        if (majorMoreBtn) {
            majorMoreBtn.addEventListener('click', () => {
                const moreEl = document.getElementById('etf-major-more');
                if (moreEl) {
                    const isHidden = moreEl.style.display === 'none';
                    moreEl.style.display = isHidden ? 'block' : 'none';
                    majorMoreBtn.textContent = isHidden ? '접기 ∧' : '더보기 ∨';
                }
            });
        }
    }
    renderMajorList();

    document.querySelectorAll('#etf-major-asset-tabs .etf-sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-major-asset-tabs .etf-sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            majorAsset = tab.dataset.asset;
            renderMajorList();
        });
    });
    document.querySelectorAll('#etf-major-sort-tabs .etf-main-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#etf-major-sort-tabs .etf-main-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            majorSort = tab.dataset.sort;
            renderMajorList();
        });
    });
}

// 코인시장 로드
async function loadMarketCrypto() {
    const restrictionEl = document.getElementById('market-crypto-restriction');
    const contentEl = document.getElementById('market-crypto-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // [BUG FIX 3] 거래소 API 직접 연동
        const data = await invokeWithTimeout('get_market_crypto', {
            accessToken: auth.accessToken || '',
            exchange: 'all'
        }, 10000);

        if (!data || !data.success) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketCrypto()">다시 시도</button></div>';
            return;
        }

        // UI 렌더링
        const globalData = data.global || {};
        const kimchi = data.kimchi_premium;
        const coins = data.coins || [];

        contentEl.innerHTML = `
            <div class="crypto-summary-cards">
                <div class="crypto-card">
                    <div class="card-label">BTC 도미넌스</div>
                    <div class="card-value">${globalData.btc_dominance || '-'}%</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">ETH 도미넌스</div>
                    <div class="card-value">${globalData.eth_dominance || '-'}%</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">김치 프리미엄</div>
                    <div class="card-value ${kimchi >= 0 ? 'profit' : 'loss'}">${kimchi !== null ? (kimchi >= 0 ? '+' : '') + kimchi.toFixed(2) + '%' : '-'}</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">총 시가총액</div>
                    <div class="card-value">$${formatBillions(globalData.total_market_cap || 0)}</div>
                </div>
            </div>
            <div class="exchange-filter crypto-exchange-filter">
                <button class="filter-btn active" data-exchange="all">전체</button>
                <button class="filter-btn" data-exchange="binance">Binance</button>
                <button class="filter-btn" data-exchange="upbit">Upbit</button>
            </div>
            <div class="crypto-list-section card">
                <h3>코인 시세</h3>
                <table class="data-table">
                    <thead><tr><th>코인</th><th>거래소</th><th>현재가</th><th>24h 등락률</th><th>거래량</th></tr></thead>
                    <tbody id="crypto-tbody"></tbody>
                </table>
            </div>
        `;

        // 거래소 필터 이벤트
        contentEl.querySelectorAll('.crypto-exchange-filter .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                contentEl.querySelectorAll('.crypto-exchange-filter .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const exchange = btn.dataset.exchange;
                renderCryptoTable(exchange === 'all' ? coins : coins.filter(c => c.exchange === exchange));
            });
        });

        // 테이블 렌더링
        renderCryptoTable(coins);

    } catch (error) {
        console.error('Market Crypto error:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        contentEl.innerHTML = `<div class="error-state"><p>${errMsg}</p><button class="btn btn-sm btn-primary" onclick="loadMarketCrypto()">다시 시도</button></div>`;
    }
}

function renderCryptoTable(coins) {
    const tbody = document.getElementById('crypto-tbody');
    if (!tbody) return;

    if (coins.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">데이터 없음</td></tr>';
        return;
    }

    tbody.innerHTML = coins.slice(0, 30).map(c => {
        // API 응답: change_24h (not change_percent)
        const change = c.change_24h || c.change_percent || 0;
        const changeClass = change >= 0 ? 'profit' : 'loss';
        const priceStr = c.exchange === 'upbit' && c.symbol?.includes('KRW')
            ? `₩${(c.price || 0).toLocaleString()}`
            : `$${(c.price || 0).toLocaleString()}`;

        return `
            <tr class="clickable" data-symbol="${c.symbol}" data-exchange="${c.exchange}">
                <td><strong>${c.symbol}</strong></td>
                <td><span class="exchange-badge ${c.exchange}">${c.exchange?.toUpperCase()}</span></td>
                <td>${priceStr}</td>
                <td class="${changeClass}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                <td>${formatBillions(c.volume || 0)}</td>
            </tr>
        `;
    }).join('');

    // 클릭 이벤트
    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => openStockDetail(row.dataset.symbol, row.dataset.exchange));
    });
}

// =====================================================
// 종목분석 새 페이지 로드 (STEP A)
// =====================================================

// 국내주식 분석 로드
async function loadStockKr() {
    console.log('[loadStockKr] 함수 시작');
    // 검색 자동완성 초기화 (DOM이 준비된 시점에 호출)
    console.log('[loadStockKr] initStockKrAutocomplete 호출 전');
    initStockKrAutocomplete();
    console.log('[loadStockKr] initStockKrAutocomplete 호출 후');
    renderRecentSearches();

    // 하위 탭 이벤트
    document.querySelectorAll('#stock-kr-tabs .sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#stock-kr-tabs .sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabId = tab.dataset.tab;
            document.getElementById('stock-kr-rs-section').style.display = tabId === 'rs' ? 'block' : 'none';
            document.getElementById('stock-kr-high52-section').style.display = tabId === 'high52' ? 'block' : 'none';
            document.getElementById('stock-kr-valuation-section').style.display = tabId === 'valuation' ? 'block' : 'none';
            document.getElementById('stock-kr-reports-section').style.display = tabId === 'reports' ? 'block' : 'none';
        });
    });

    // 검색 버튼 이벤트
    document.getElementById('btn-stock-kr-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-kr-search')?.value?.trim();
        if (query) {
            // 자동완성의 첫 번째 항목 클릭 시뮬레이션
            const firstItem = document.querySelector('#stock-kr-autocomplete .autocomplete-item');
            if (firstItem) {
                firstItem.click();
            } else {
                searchSymbols(query);
            }
        }
    });

    // RS, 52주 신고가, 밸류에이션 데이터 로드
    await Promise.all([
        loadRsData(),
        loadHigh52Data(),
        loadValuationData()
    ]);

    // 테이블 행 클릭 이벤트 (종목 상세 열기)
    document.querySelectorAll('#rs-tbody tr, #high52-tbody tr, #valuation-tbody tr').forEach(row => {
        row.classList.add('clickable');
        row.addEventListener('click', () => {
            const symbol = row.dataset?.symbol;
            if (symbol) {
                openStockDetail(symbol, 'kis_kr');
            }
        });
    });
}

// RS 데이터 로드 (API 연동)
async function loadRsData() {
    const tbody = document.getElementById('rs-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">RS 데이터 로딩 중...</td></tr>';

    try {
        const result = await invokeWithTimeout('get_analysis_rs', {
            accessToken: auth.accessToken || '',
            market: 'kospi'
        }, 15000);

        const stocks = result?.stocks || [];
        if (stocks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">데이터가 없습니다</td></tr>';
            return;
        }

        tbody.innerHTML = stocks.map((s, idx) => {
            const changeVal = s.change || 0;
            const changeClass = changeVal >= 0 ? 'profit' : 'loss';
            const changeStr = changeVal >= 0 ? `+${changeVal.toFixed(2)}%` : `${changeVal.toFixed(2)}%`;
            const rsClass = s.rs_total >= 90 ? 'rs-high' : (s.rs_total >= 70 ? 'rs-mid' : 'rs-low');
            const priceStr = s.price ? s.price.toLocaleString() : '-';
            return `
                <tr class="clickable" data-symbol="${s.code}">
                    <td>${idx + 1}</td>
                    <td><strong>${s.name}</strong></td>
                    <td>${priceStr}</td>
                    <td class="${changeClass}">${changeStr}</td>
                    <td class="rs-score ${rsClass}">${s.rs_total || '-'}</td>
                    <td>${s.rs_1m || '-'}</td>
                    <td>${s.rs_3m || '-'}</td>
                    <td>${s.rs_6m || '-'}</td>
                    <td>-</td>
                </tr>
            `;
        }).join('');

        // 클릭 이벤트 바인딩
        tbody.querySelectorAll('tr.clickable').forEach(row => {
            row.addEventListener('click', () => {
                const symbol = row.dataset.symbol;
                if (symbol) openStockDetail(symbol, 'kis_kr');
            });
        });

    } catch (error) {
        console.error('RS 데이터 로드 실패:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        tbody.innerHTML = `<tr><td colspan="9" class="empty-cell">${errMsg}</td></tr>`;
    }
}

// 52주 신고가 데이터 로드
async function loadHigh52Data() {
    const tbody = document.getElementById('high52-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">52주 신고가 데이터 로딩 중...</td></tr>';

    try {
        const result = await invokeWithTimeout('get_analysis_new_high', {
            accessToken: auth.accessToken || ''
        }, 15000);

        const stocks = result?.stocks || [];
        if (stocks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">데이터가 없습니다</td></tr>';
            return;
        }

        // 테이블 헤더 업데이트 (데이터 있는 컬럼만)
        const tableHead = tbody.closest('table').querySelector('thead tr');
        if (tableHead) {
            tableHead.innerHTML = '<th>종목명</th><th>현재가</th><th>등락률</th><th>52주 최고가</th><th>최고가 대비</th><th>거래량</th>';
        }

        tbody.innerHTML = stocks.slice(0, 30).map(s => {
            const changeVal = s.change || 0;
            const changeClass = changeVal >= 0 ? 'profit' : 'loss';
            const changeStr = changeVal >= 0 ? `+${changeVal.toFixed(2)}%` : `${changeVal.toFixed(2)}%`;
            const distanceVal = s.distance || 0;
            const distanceClass = distanceVal >= 0 ? 'profit' : 'loss';
            const distanceStr = distanceVal >= 0 ? `+${distanceVal.toFixed(2)}%` : `${distanceVal.toFixed(2)}%`;
            return `
                <tr class="clickable" data-symbol="${s.code}">
                    <td><strong>${s.name}</strong></td>
                    <td>${s.price?.toLocaleString() || '-'}</td>
                    <td class="${changeClass}">${changeStr}</td>
                    <td>${s.high_52w?.toLocaleString() || '-'}</td>
                    <td class="${distanceClass}">${distanceStr}</td>
                    <td>${formatVolume(s.volume || 0)}</td>
                </tr>
            `;
        }).join('');

        // 클릭 이벤트 바인딩
        tbody.querySelectorAll('tr.clickable').forEach(row => {
            row.addEventListener('click', () => {
                const symbol = row.dataset.symbol;
                if (symbol) openStockDetail(symbol, 'kis_kr');
            });
        });

    } catch (error) {
        console.error('52주 신고가 데이터 로드 실패:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">${errMsg}</td></tr>`;
    }
}

// 밸류에이션 데이터 로드
async function loadValuationData() {
    const tbody = document.getElementById('valuation-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">밸류에이션 데이터 로딩 중...</td></tr>';

    try {
        const result = await invokeWithTimeout('get_analysis_valuation', {
            accessToken: auth.accessToken || '',
            market: 'all'
        }, 15000);

        const stocks = result?.stocks || [];
        if (stocks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">데이터가 없습니다</td></tr>';
            return;
        }

        // 테이블 헤더 업데이트 (데이터 있는 컬럼만)
        const tableHead = tbody.closest('table').querySelector('thead tr');
        if (tableHead) {
            tableHead.innerHTML = '<th>종목명</th><th>현재가</th><th>시가총액</th><th>PER</th><th>PBR</th><th>시장</th>';
        }

        tbody.innerHTML = stocks.slice(0, 30).map(s => {
            const per = s.per > 0 ? s.per.toFixed(2) : '-';
            const pbr = s.pbr > 0 ? s.pbr.toFixed(2) : '-';
            return `
                <tr class="clickable" data-symbol="${s.code}">
                    <td><strong>${s.name}</strong></td>
                    <td>${s.price?.toLocaleString() || '-'}</td>
                    <td>${formatBillions(s.market_cap || 0)}</td>
                    <td>${per}</td>
                    <td>${pbr}</td>
                    <td>${s.market || '-'}</td>
                </tr>
            `;
        }).join('');

        // 클릭 이벤트 바인딩
        tbody.querySelectorAll('tr.clickable').forEach(row => {
            row.addEventListener('click', () => {
                const symbol = row.dataset.symbol;
                if (symbol) openStockDetail(symbol, 'kis_kr');
            });
        });

    } catch (error) {
        console.error('밸류에이션 데이터 로드 실패:', error);
        const errMsg = error?.message || error || '알 수 없는 오류';
        tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">${errMsg}</td></tr>`;
    }
}

// 해외주식 분석 로드
async function loadStockUs() {
    // 탭 이벤트
    document.querySelectorAll('#stock-us-tabs .sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#stock-us-tabs .sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabId = tab.dataset.tab;
            document.getElementById('stock-us-rs-section').style.display = tabId === 'us-rs' ? 'block' : 'none';
            document.getElementById('stock-us-valuation-section').style.display = tabId === 'us-valuation' ? 'block' : 'none';
        });
    });

    // 검색 이벤트
    const searchInput = document.getElementById('stock-us-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchUsStock(query);
        }
    });

    document.getElementById('btn-stock-us-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-us-search')?.value?.trim();
        if (query) searchUsStock(query);
    });

    // 샘플 데이터 로드
    await loadUsRsData();
}

async function searchUsStock(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'kis_us'
        });
        const symbols = result.symbols || result || [];
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, 'kis_us');
        } else {
            showToast('검색 결과가 없습니다', 'warning');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadUsRsData() {
    const tbody = document.getElementById('us-rs-tbody');
    if (!tbody) return;

    const sampleData = [
        { rank: 1, symbol: 'NVDA', name: 'NVIDIA Corp', price: '$875.28', change: '+4.21%', rs_total: 99, rs_1m: 98, rs_3m: 99 },
        { rank: 2, symbol: 'AAPL', name: 'Apple Inc', price: '$195.89', change: '+1.23%', rs_total: 95, rs_1m: 92, rs_3m: 96 },
        { rank: 3, symbol: 'MSFT', name: 'Microsoft Corp', price: '$428.50', change: '+0.85%', rs_total: 94, rs_1m: 93, rs_3m: 95 },
        { rank: 4, symbol: 'GOOGL', name: 'Alphabet Inc', price: '$175.98', change: '+2.15%', rs_total: 92, rs_1m: 94, rs_3m: 91 },
        { rank: 5, symbol: 'AMZN', name: 'Amazon.com Inc', price: '$185.63', change: '+1.78%', rs_total: 91, rs_1m: 89, rs_3m: 92 },
    ];

    tbody.innerHTML = sampleData.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        const rsClass = s.rs_total >= 90 ? 'rs-high' : (s.rs_total >= 70 ? 'rs-mid' : 'rs-low');
        return `
            <tr class="clickable" data-symbol="${s.symbol}">
                <td>${s.rank}</td>
                <td><strong>${s.name}</strong> <span style="color:var(--text-muted)">${s.symbol}</span></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td class="rs-score ${rsClass}">${s.rs_total}</td>
                <td>${s.rs_1m}</td>
                <td>${s.rs_3m}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            if (symbol) openStockDetail(symbol, 'kis_us');
        });
    });
}

// ETF 분석 로드
async function loadStockEtf() {
    const searchInput = document.getElementById('stock-etf-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchEtf(query);
        }
    });

    document.getElementById('btn-stock-etf-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-etf-search')?.value?.trim();
        if (query) searchEtf(query);
    });

    // 테마 필터 이벤트
    document.querySelectorAll('#stock-etf-theme .theme-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#stock-etf-theme .theme-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadEtfData(btn.dataset.theme);
        });
    });

    await loadEtfData('all');
}

async function searchEtf(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'kis_kr'
        });
        const symbols = (result.symbols || result || []).filter(s =>
            s.name?.includes('ETF') || s.symbol?.includes('ETF')
        );
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, 'kis_kr');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadEtfData(theme = 'all') {
    const tbody = document.getElementById('stock-etf-tbody');
    if (!tbody) return;

    const sampleData = [
        { symbol: '069500', name: 'KODEX 200', price: '42,850', change: '+0.82%', nav: '25.5조', volume: '1,234억', theme: '대표' },
        { symbol: '229200', name: 'KODEX 코스닥150', price: '12,340', change: '+1.54%', nav: '3.2조', volume: '456억', theme: '코스닥' },
        { symbol: '305720', name: 'KODEX 2차전지산업', price: '18,650', change: '+2.31%', nav: '2.1조', volume: '892억', theme: '2차전지' },
        { symbol: '381170', name: 'TIGER AI코리아', price: '11,280', change: '+3.45%', nav: '1.5조', volume: '567억', theme: 'AI' },
        { symbol: '091160', name: 'KODEX 반도체', price: '35,200', change: '+1.87%', nav: '4.8조', volume: '2,345억', theme: '반도체' },
    ];

    const filtered = theme === 'all' ? sampleData : sampleData.filter(s => s.theme === theme);

    tbody.innerHTML = filtered.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        return `
            <tr class="clickable" data-symbol="${s.symbol}">
                <td><strong>${s.name}</strong></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td>${s.nav}</td>
                <td>${s.volume}</td>
                <td><span class="theme-tag">${s.theme}</span></td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="6" class="empty-cell">해당 테마의 ETF가 없습니다</td></tr>';

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            if (symbol) openStockDetail(symbol, 'kis_kr');
        });
    });
}

// 코인 분석 로드
async function loadStockCrypto() {
    const searchInput = document.getElementById('stock-crypto-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchCrypto(query);
        }
    });

    document.getElementById('btn-stock-crypto-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-crypto-search')?.value?.trim();
        if (query) searchCrypto(query);
    });

    // 거래소 필터 이벤트
    document.querySelectorAll('#stock-crypto-exchange .filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#stock-crypto-exchange .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadCryptoData(btn.dataset.exchange);
        });
    });

    await loadCryptoData('all');
}

async function searchCrypto(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'binance'
        });
        const symbols = result.symbols || result || [];
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, symbols[0].exchange || 'binance');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadCryptoData(exchange = 'all') {
    const tbody = document.getElementById('stock-crypto-tbody');
    if (!tbody) return;

    const sampleData = [
        { symbol: 'BTC-USDT', name: 'Bitcoin', exchange: 'binance', price: '$97,450', change: '+2.34%', volume: '$45.2B', marketCap: '$1.92T' },
        { symbol: 'ETH-USDT', name: 'Ethereum', exchange: 'binance', price: '$3,456', change: '+3.12%', volume: '$18.5B', marketCap: '$415B' },
        { symbol: 'SOL-USDT', name: 'Solana', exchange: 'okx', price: '$198.50', change: '+5.67%', volume: '$4.2B', marketCap: '$92B' },
        { symbol: 'BTC-KRW', name: '비트코인', exchange: 'upbit', price: '₩142,350,000', change: '+2.15%', volume: '₩1.2조', marketCap: '-' },
        { symbol: 'XRP-USDT', name: 'Ripple', exchange: 'bybit', price: '$2.45', change: '-1.23%', volume: '$2.8B', marketCap: '$138B' },
    ];

    const filtered = exchange === 'all' ? sampleData : sampleData.filter(s => s.exchange === exchange);

    tbody.innerHTML = filtered.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        return `
            <tr class="clickable" data-symbol="${s.symbol}" data-exchange="${s.exchange}">
                <td><strong>${s.name}</strong> <span style="color:var(--text-muted)">${s.symbol}</span></td>
                <td><span class="exchange-badge ${s.exchange}">${s.exchange.toUpperCase()}</span></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td>${s.volume}</td>
                <td>${s.marketCap}</td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="6" class="empty-cell">해당 거래소의 코인이 없습니다</td></tr>';

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            const exchange = row.dataset.exchange;
            if (symbol) openStockDetail(symbol, exchange);
        });
    });
}

// =====================================================
// 관심종목 페이지 로드 (STEP A)
// =====================================================

async function loadWatchlist() {
    try {
        const result = await invoke('get_watchlist_items', {
            accessToken: auth.accessToken || '',
            groupId: 'default'
        });

        const items = result.items || [];
        const tbody = document.getElementById('watchlist-tbody');
        const countEl = document.getElementById('watchlist-count');

        if (countEl) countEl.textContent = items.length;

        if (tbody) {
            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">관심종목이 없습니다. 종목분석에서 ⭐ 버튼을 눌러 추가하세요.</td></tr>';
            } else {
                tbody.innerHTML = items.map(item => `
                    <tr>
                        <td>${item.name || item.symbol}</td>
                        <td>${item.price || '-'}</td>
                        <td class="${item.change >= 0 ? 'profit' : 'loss'}">${item.change >= 0 ? '+' : ''}${item.change || 0}%</td>
                        <td>${item.volume || '-'}</td>
                        <td>${item.memo || '-'}</td>
                        <td><button class="btn btn-sm btn-danger" data-id="${item.id}">삭제</button></td>
                    </tr>
                `).join('');
            }
        }

    } catch (error) {
        console.error('Watchlist error:', error);
    }
}

// 유틸리티 함수
function formatBillions(value) {
    if (value == null) return '-';
    const absVal = Math.abs(value);
    if (absVal >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
    if (absVal >= 1e8) return `${(value / 1e8).toFixed(0)}억`;
    if (absVal >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
    return value.toLocaleString();
}

// 재무제표 값 포맷 (입력: 억원 단위)
// 185828억 → "18.6조", 5848억 → "5,848억"
function formatFinancialValue(valueInBillion) {
    if (valueInBillion == null || valueInBillion === 0) return '-';
    const abs = Math.abs(valueInBillion);
    const sign = valueInBillion < 0 ? '-' : '';
    if (abs >= 10000) return sign + (abs / 10000).toFixed(1) + '조';
    return sign + Math.round(abs).toLocaleString() + '억';
}

// =====================================================
// STEP B: 캔들차트 + 검색 자동완성
// =====================================================

// 캔들차트 인스턴스
let detailChart = null;
let previewChart = null;
let currentStockData = null;

// 최근 검색 관리
const MAX_RECENT_SEARCHES = 5;

function getRecentSearches() {
    try {
        return JSON.parse(localStorage.getItem('bbooster_recent_searches') || '[]');
    } catch {
        return [];
    }
}

function addRecentSearch(symbol, name) {
    const recent = getRecentSearches();
    const existing = recent.findIndex(r => r.symbol === symbol);
    if (existing > -1) recent.splice(existing, 1);
    recent.unshift({ symbol, name });
    if (recent.length > MAX_RECENT_SEARCHES) recent.pop();
    localStorage.setItem('bbooster_recent_searches', JSON.stringify(recent));
    renderRecentSearches();
}

function renderRecentSearches() {
    const container = document.getElementById('recent-items-kr');
    if (!container) return;

    const recent = getRecentSearches();
    if (recent.length === 0) {
        document.getElementById('recent-searches-kr')?.style.setProperty('display', 'none');
        return;
    }

    document.getElementById('recent-searches-kr')?.style.setProperty('display', 'flex');
    container.innerHTML = recent.map(r => `
        <span class="recent-item" data-symbol="${r.symbol}">${r.name || r.symbol}</span>
    `).join('');

    container.querySelectorAll('.recent-item').forEach(item => {
        item.addEventListener('click', () => {
            const symbol = item.dataset.symbol;
            openStockDetail(symbol, 'kis_kr');
        });
    });
}

// 검색 자동완성
let autocompleteTimeout = null;

function initSearchAutocomplete(inputId, autocompleteId, market = 'kr') {
    const input = document.getElementById(inputId);
    const autocomplete = document.getElementById(autocompleteId);
    if (!input || !autocomplete) return;

    input.addEventListener('input', () => {
        const query = input.value.trim();
        if (autocompleteTimeout) clearTimeout(autocompleteTimeout);

        if (query.length < 1) {
            autocomplete.style.display = 'none';
            return;
        }

        autocompleteTimeout = setTimeout(async () => {
            try {
                const exchange = market === 'kr' ? 'kis_kr' : (market === 'us' ? 'kis_us' : null);
                const result = await invoke('search_symbols', {
                    accessToken: auth.accessToken || '',
                    query: query,
                    exchange: exchange
                });

                const symbols = result.symbols || result || [];
                if (symbols.length === 0) {
                    autocomplete.style.display = 'none';
                    return;
                }

                autocomplete.innerHTML = symbols.slice(0, 8).map(s => {
                    const changeClass = (s.change || 0) >= 0 ? 'profit' : 'loss';
                    return `
                        <div class="autocomplete-item" data-symbol="${s.symbol}" data-exchange="${s.exchange}">
                            <div>
                                <span class="autocomplete-stock-name">${s.name || s.symbol}</span>
                                <span class="autocomplete-stock-code">${s.symbol}</span>
                            </div>
                            <div>
                                <span class="autocomplete-price">${s.price_formatted || '-'}</span>
                                <span class="autocomplete-change ${changeClass}">${s.change_formatted || ''}</span>
                            </div>
                        </div>
                    `;
                }).join('');

                autocomplete.style.display = 'block';

                autocomplete.querySelectorAll('.autocomplete-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const symbol = item.dataset.symbol;
                        const exchange = item.dataset.exchange;
                        const name = item.querySelector('.autocomplete-stock-name')?.textContent;
                        input.value = name || symbol;
                        autocomplete.style.display = 'none';
                        addRecentSearch(symbol, name);
                        openStockDetail(symbol, exchange);
                    });
                });
            } catch (error) {
                console.error('Autocomplete error:', error);
                autocomplete.style.display = 'none';
            }
        }, 200);
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !autocomplete.contains(e.target)) {
            autocomplete.style.display = 'none';
        }
    });

    // Enter 키 처리
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const firstItem = autocomplete.querySelector('.autocomplete-item');
            if (firstItem) {
                firstItem.click();
            }
        } else if (e.key === 'Escape') {
            autocomplete.style.display = 'none';
        }
    });
}

// =====================================================
// Stock Detail Modal - StockEasy Style (Light Theme)
// =====================================================

// 재무건전성 점수 계산 함수
function calculateHealthScore(data) {
    let score = 50; // 기본 점수

    // ROE 점수 (0~25점)
    const roe = parseFloat(data.roe) || 0;
    if (roe >= 15) score += 25;
    else if (roe >= 10) score += 20;
    else if (roe >= 5) score += 15;
    else if (roe > 0) score += 10;
    else score -= 10;

    // 부채비율 점수 (0~25점)
    const debtRatio = parseFloat(data.debt_ratio) || 0;
    if (debtRatio < 50) score += 25;
    else if (debtRatio < 100) score += 20;
    else if (debtRatio < 150) score += 10;
    else if (debtRatio < 200) score += 5;
    else score -= 10;

    // 영업이익률 점수 (0~15점)
    const opMargin = parseFloat(data.operating_margin) || 0;
    if (opMargin >= 20) score += 15;
    else if (opMargin >= 10) score += 10;
    else if (opMargin > 0) score += 5;
    else score -= 5;

    // 매출성장률 점수 (0~10점)
    const growth = parseFloat(data.revenue_growth) || 0;
    if (growth >= 20) score += 10;
    else if (growth >= 10) score += 7;
    else if (growth > 0) score += 5;
    else score -= 5;

    return Math.max(0, Math.min(100, score));
}

// 점수에 따른 등급 반환
function getGrade(score) {
    if (score >= 80) return { grade: 'A', label: '매우 우수', class: 'grade-a' };
    if (score >= 60) return { grade: 'B', label: '양호', class: 'grade-b' };
    if (score >= 40) return { grade: 'C', label: '보통', class: 'grade-c' };
    if (score >= 20) return { grade: 'D', label: '주의', class: 'grade-d' };
    return { grade: 'F', label: '취약', class: 'grade-f' };
}

// 투자지표 등급 계산
function getIndicatorGrade(type, value) {
    switch(type) {
        case 'growth': // 성장성 (매출성장률 기준)
            if (value >= 20) return { grade: 'A', class: 'grade-a' };
            if (value >= 10) return { grade: 'B', class: 'grade-b' };
            if (value >= 0) return { grade: 'C', class: 'grade-c' };
            return { grade: 'D', class: 'grade-d' };
        case 'profitability': // 수익성 (ROE 기준)
            if (value >= 15) return { grade: 'A', class: 'grade-a' };
            if (value >= 10) return { grade: 'B', class: 'grade-b' };
            if (value >= 5) return { grade: 'C', class: 'grade-c' };
            return { grade: 'D', class: 'grade-d' };
        case 'stability': // 안정성 (부채비율 역산)
            if (value < 50) return { grade: 'A', class: 'grade-a' };
            if (value < 100) return { grade: 'B', class: 'grade-b' };
            if (value < 150) return { grade: 'C', class: 'grade-c' };
            return { grade: 'D', class: 'grade-d' };
        case 'valuation': // 밸류에이션 (PER 기준)
            if (value > 0 && value < 10) return { grade: 'A', class: 'grade-a' };
            if (value > 0 && value < 15) return { grade: 'B', class: 'grade-b' };
            if (value > 0 && value < 25) return { grade: 'C', class: 'grade-c' };
            return { grade: 'D', class: 'grade-d' };
        default:
            return { grade: '-', class: 'grade-f' };
    }
}

// SVG 원형 차트 생성
function renderHealthCircle(score, gradeClass) {
    const radius = 50;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (score / 100) * circumference;

    return `
        <div class="sd-health-circle">
            <svg width="120" height="120" viewBox="0 0 120 120">
                <circle class="sd-health-circle-bg" cx="60" cy="60" r="${radius}"/>
                <circle class="sd-health-circle-progress ${gradeClass}"
                    cx="60" cy="60" r="${radius}"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${offset}"/>
            </svg>
            <div class="sd-health-text">
                <div class="sd-health-score-value">${score}</div>
                <div class="sd-health-grade">${getGrade(score).label}</div>
            </div>
        </div>
    `;
}

// DIV 기반 바 차트 생성
function renderTrendChart(data) {
    if (!data || data.length === 0) {
        return '<div class="sd-empty-state">실적 데이터가 없습니다</div>';
    }

    // 최대값 찾기
    const maxRevenue = Math.max(...data.map(d => Math.abs(d.revenue || 0)));
    const maxProfit = Math.max(...data.map(d => Math.abs(d.operating_profit || 0)));
    const maxVal = Math.max(maxRevenue, maxProfit);

    const bars = data.slice(-6).map(item => {
        const revenueHeight = maxVal > 0 ? (Math.abs(item.revenue || 0) / maxVal) * 120 : 0;
        const profitHeight = maxVal > 0 ? (Math.abs(item.operating_profit || 0) / maxVal) * 120 : 0;
        const profitNegative = (item.operating_profit || 0) < 0;

        return `
            <div class="sd-trend-bar-group">
                <div class="sd-trend-bars">
                    <div class="sd-trend-bar revenue" style="height: ${revenueHeight}px"></div>
                    <div class="sd-trend-bar profit ${profitNegative ? 'negative' : ''}" style="height: ${profitHeight}px"></div>
                </div>
                <div class="sd-trend-label">${item.period || ''}</div>
            </div>
        `;
    }).join('');

    return `
        <div class="sd-trend-chart">${bars}</div>
        <div class="sd-trend-legend">
            <div class="sd-trend-legend-item">
                <div class="sd-trend-legend-dot revenue"></div>
                <span>매출액</span>
            </div>
            <div class="sd-trend-legend-item">
                <div class="sd-trend-legend-dot profit"></div>
                <span>영업이익</span>
            </div>
        </div>
    `;
}

// SVG 도넛 차트 생성 (세그먼트 매출)
function renderDonutChart(segments) {
    if (!segments || segments.length === 0) {
        return '<div class="sd-empty-state">세그먼트 데이터가 없습니다</div>';
    }

    const colors = ['#7C3AED', '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'];
    const total = segments.reduce((sum, s) => sum + (s.value || 0), 0);

    let currentAngle = 0;
    const radius = 60;
    const cx = 80;
    const cy = 80;

    const paths = segments.map((seg, idx) => {
        const percentage = total > 0 ? (seg.value / total) : 0;
        const angle = percentage * 360;
        const largeArc = angle > 180 ? 1 : 0;

        const startX = cx + radius * Math.cos((currentAngle - 90) * Math.PI / 180);
        const startY = cy + radius * Math.sin((currentAngle - 90) * Math.PI / 180);
        currentAngle += angle;
        const endX = cx + radius * Math.cos((currentAngle - 90) * Math.PI / 180);
        const endY = cy + radius * Math.sin((currentAngle - 90) * Math.PI / 180);

        return `<path d="M ${cx} ${cy} L ${startX} ${startY} A ${radius} ${radius} 0 ${largeArc} 1 ${endX} ${endY} Z" fill="${colors[idx % colors.length]}"/>`;
    }).join('');

    const legendItems = segments.map((seg, idx) => `
        <div class="sd-segment-item">
            <div class="sd-segment-info">
                <div class="sd-segment-color" style="background: ${colors[idx % colors.length]}"></div>
                <span class="sd-segment-name">${seg.name}</span>
            </div>
            <span class="sd-segment-value">${total > 0 ? ((seg.value / total) * 100).toFixed(1) : 0}%</span>
        </div>
    `).join('');

    return `
        <div class="sd-segment-container">
            <div class="sd-donut-chart">
                <svg width="160" height="160" viewBox="0 0 160 160">
                    ${paths}
                    <circle cx="${cx}" cy="${cy}" r="35" fill="#FFFFFF"/>
                </svg>
            </div>
            <div class="sd-segment-legend">
                ${legendItems}
            </div>
        </div>
    `;
}

// 종목 상세 모달 열기 (StockEasy 스타일)
async function openStockDetail(symbol, exchange) {
    const modal = document.getElementById('stock-detail-modal');
    if (!modal) return;

    modal.style.display = 'flex';
    currentStockData = { symbol, exchange };

    // 로딩 상태 초기화
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const marketEl = document.getElementById('detail-stock-market');

    if (nameEl) nameEl.textContent = '로딩 중...';
    if (codeEl) codeEl.textContent = symbol || '';
    if (marketEl) marketEl.textContent = exchange?.toUpperCase() || '';

    // 첫 번째 탭(요약) 활성화
    activateStockTab('summary');

    // 시장 유형 확인
    const isEtf = exchange?.toLowerCase() === 'etf';
    const isKoreanStock = !isEtf && (exchange?.toLowerCase() === 'kis_kr' ||
                          exchange?.toLowerCase() === 'kospi' ||
                          exchange?.toLowerCase() === 'kosdaq');
    const isUsStock = exchange?.toLowerCase() === 'kis_us' ||
                      exchange?.toLowerCase() === 'us' ||
                      exchange?.toLowerCase() === 'nasdaq' ||
                      exchange?.toLowerCase() === 'nyse';

    // ETF는 별도 처리
    if (isEtf) {
        openEtfDetail(symbol);
        return;
    }

    try {
        let detail = null;

        if (isKoreanStock) {
            // 국내 종목: Phase 8-2 API 사용
            const response = await invokeWithTimeout('get_stock_summary_kr', {
                accessToken: auth.accessToken || '',
                code: symbol
            }, 10000);

            if (response && response.data) {
                const data = response.data;
                detail = {
                    name: data.name,
                    symbol: data.code,
                    market: data.market,
                    exchange: 'kis_kr',
                    currency: 'KRW',
                    price: data.price || 0,
                    change: data.change || 0,
                    change_percent: data.change_pct || 0,
                    open: data.open || 0,
                    high: data.high || 0,
                    low: data.low || 0,
                    volume: data.volume || 0,
                    market_cap: data.market_cap || '',
                    market_cap_raw: data.market_cap_raw || 0,
                    per: data.per || 0,
                    pbr: data.pbr || 0,
                    roe: data.roe || 0,
                    eps: data.eps || 0,
                    high_52w: data.high_52w || 0,
                    low_52w: data.low_52w || 0,
                    dividend_yield: data.dividend_yield || 0,
                    foreign_ratio: data.foreign_ratio || 0,
                };
            }
        } else if (isUsStock) {
            // 해외 종목: Phase 9 API 사용 (Finviz)
            const response = await invokeWithTimeout('get_stock_summary_us', {
                accessToken: auth.accessToken || '',
                ticker: symbol
            }, 15000);

            if (response && response.data) {
                const data = response.data;
                detail = {
                    name: data.name,
                    symbol: data.ticker,
                    market: 'US',
                    exchange: 'kis_us',
                    currency: 'USD',
                    sector: data.sector,
                    industry: data.industry,
                    price: data.price || 0,
                    change: data.change || 0,
                    change_percent: data.change_pct || 0,
                    volume: data.volume || 0,
                    avg_volume: data.avg_volume || 0,
                    market_cap: data.market_cap || '',
                    market_cap_raw: data.market_cap_raw || 0,
                    per: data.per || 0,
                    forward_per: data.forward_per || 0,
                    pbr: data.pbr || 0,
                    roe: data.roe || 0,
                    roa: data.roa || 0,
                    eps: data.eps || 0,
                    high_52w: data.high_52w || 0,
                    low_52w: data.low_52w || 0,
                    dividend_yield: data.dividend_yield || 0,
                    operating_margin: data.operating_margin || 0,
                    profit_margin: data.profit_margin || 0,
                    target_price: data.target_price || 0,
                    recommendation: data.recommendation || '',
                };
            }
        } else {
            // 기존 로직 (ETF/코인)
            const response = await invokeWithTimeout('get_symbol_detail', {
                accessToken: auth.accessToken || '',
                symbol: symbol,
                exchange: exchange
            }, 10000);

            if (response && typeof response === 'object') {
                if (response.basic && response.basic.name) {
                    detail = {
                        name: response.basic.name,
                        symbol: response.basic.symbol,
                        market: response.basic.market,
                        exchange: response.basic.exchange,
                        is_etf: response.basic.is_etf,
                        sector: response.basic.sector,
                        price: response.price?.current || 0,
                        change: response.price?.change_amount || 0,
                        change_percent: response.price?.change || 0,
                        open: response.price?.open || 0,
                        high: response.price?.high || 0,
                        low: response.price?.low || 0,
                        volume: response.price?.volume || 0,
                        market_cap: response.price?.market_cap || 0,
                        per: response.price?.per || 0,
                        pbr: response.price?.pbr || 0,
                        daily_prices: response.daily_prices || [],
                    };
                } else if (response.name) {
                    detail = response;
                }
            }
        }

        if (detail && detail.name) {
            updateStockDetailUI(detail);
            // 국내/해외 종목은 3M 기본, 나머지는 1D
            initCandleChart(symbol, exchange, (isKoreanStock || isUsStock) ? '3M' : '1D');
        } else {
            if (nameEl) nameEl.textContent = symbol || '-';
        }

        // 2. 재무 요약 데이터 로드 (병렬)
        if (isKoreanStock) {
            loadFinancialSummaryKr(symbol);
        } else if (isUsStock) {
            loadFinancialSummaryUs(symbol);
        } else {
            loadFinancialSummary(symbol);
        }

    } catch (error) {
        console.error('Failed to load stock detail:', error);
        if (nameEl) nameEl.textContent = symbol || '-';
        showToast('종목 정보를 불러올 수 없습니다', 'error');
    }
}

// =============================================================================
// Phase 10: ETF 상세 페이지
// =============================================================================

async function openEtfDetail(code) {
    const modal = document.getElementById('stock-detail-modal');
    if (!modal) return;

    modal.style.display = 'flex';
    currentStockData = { symbol: code, exchange: 'etf', isEtf: true };

    // 로딩 상태
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const marketEl = document.getElementById('detail-stock-market');

    if (nameEl) nameEl.textContent = '로딩 중...';
    if (codeEl) codeEl.textContent = code || '';
    if (marketEl) marketEl.textContent = 'ETF';

    // ETF 전용 탭 설정 (개요, 수익률, 분배금)
    setupEtfTabs();
    activateStockTab('summary');

    try {
        const response = await invokeWithTimeout('get_etf_summary', {
            accessToken: auth.accessToken || '',
            code: code
        }, 15000);

        if (response && response.data) {
            const data = response.data;
            updateEtfDetailUI(data);
            loadEtfSummaryTab(data);
            initCandleChart(code, 'etf', '3M');
        } else {
            if (nameEl) nameEl.textContent = code || '-';
        }
    } catch (error) {
        console.error('Failed to load ETF detail:', error);
        if (nameEl) nameEl.textContent = code || '-';
        showToast('ETF 정보를 불러올 수 없습니다', 'error');
    }
}

function setupEtfTabs() {
    // ETF는 3탭: 개요, 수익률, 분배금
    const tabContainer = document.querySelector('.stock-tabs');
    if (!tabContainer) return;

    tabContainer.innerHTML = `
        <button class="info-tab active" data-tab="summary">개요</button>
        <button class="info-tab" data-tab="returns">수익률</button>
        <button class="info-tab" data-tab="dividend">분배금</button>
    `;

    // 이벤트 리스너 재설정
    tabContainer.querySelectorAll('.info-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            activateStockTab(tab.dataset.tab);
        });
    });
}

function updateEtfDetailUI(data) {
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const priceEl = document.getElementById('detail-stock-price');
    const changeEl = document.getElementById('detail-stock-change');

    if (nameEl) nameEl.textContent = data.name || '-';
    if (codeEl) codeEl.textContent = data.code || '';

    // 가격 (KRW)
    if (priceEl) {
        priceEl.textContent = (data.price || 0).toLocaleString() + '원';
    }

    // 등락
    if (changeEl) {
        const change = data.change || 0;
        const changePct = data.change_pct || 0;
        const sign = change >= 0 ? '+' : '';
        const colorClass = change > 0 ? 'rise' : change < 0 ? 'fall' : '';
        changeEl.innerHTML = `<span class="${colorClass}">${sign}${change.toLocaleString()} (${sign}${changePct.toFixed(2)}%)</span>`;
    }
}

function loadEtfSummaryTab(data) {
    // 개요 탭 콘텐츠
    const summaryContent = document.getElementById('info-summary');
    if (!summaryContent) return;

    const formatRate = (v) => {
        if (!v && v !== 0) return '-';
        const sign = v >= 0 ? '+' : '';
        return `${sign}${v.toFixed(2)}%`;
    };

    const formatRateColor = (v) => {
        if (!v && v !== 0) return '';
        return v >= 0 ? 'rise' : 'fall';
    };

    summaryContent.innerHTML = `
        <div class="sd-card">
            <div class="sd-card-title">기본정보</div>
            <div class="sd-financial-grid">
                <div class="sd-financial-item">
                    <span class="sd-financial-label">순자산(NAV)</span>
                    <span class="sd-financial-value">${(data.nav || 0).toLocaleString()}원</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">괴리율</span>
                    <span class="sd-financial-value ${formatRateColor(data.premium_discount)}">${formatRate(data.premium_discount)}</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">총보수</span>
                    <span class="sd-financial-value">${(data.total_expense_ratio || 0).toFixed(2)}%</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">운용사</span>
                    <span class="sd-financial-value">${data.fund_company || '-'}</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">순자산총액</span>
                    <span class="sd-financial-value">${data.aum || '-'}</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">시가총액</span>
                    <span class="sd-financial-value">${data.market_cap || '-'}</span>
                </div>
                <div class="sd-financial-item">
                    <span class="sd-financial-label">배당수익률</span>
                    <span class="sd-financial-value">${(data.dividend_yield || 0).toFixed(2)}%</span>
                </div>
            </div>
        </div>

        <div class="sd-card" style="margin-top: 16px;">
            <div class="sd-card-title">수익률 요약</div>
            <div class="etf-return-grid">
                <div class="etf-return-item">
                    <span class="etf-return-label">1개월</span>
                    <span class="etf-return-value ${formatRateColor(data.return_1m)}">${formatRate(data.return_1m)}</span>
                </div>
                <div class="etf-return-item">
                    <span class="etf-return-label">3개월</span>
                    <span class="etf-return-value ${formatRateColor(data.return_3m)}">${formatRate(data.return_3m)}</span>
                </div>
                <div class="etf-return-item">
                    <span class="etf-return-label">1년</span>
                    <span class="etf-return-value ${formatRateColor(data.return_1y)}">${formatRate(data.return_1y)}</span>
                </div>
            </div>
        </div>
    `;
}

async function loadEtfReturnsTab(code) {
    // 수익률 탭 로드
    let container = document.getElementById('info-returns');
    if (!container) {
        // 동적으로 생성
        const contentArea = document.querySelector('.stock-detail-content') || document.querySelector('.stock-tabs')?.parentElement;
        if (contentArea) {
            container = document.createElement('div');
            container.id = 'info-returns';
            container.className = 'info-content';
            container.style.display = 'none';
            contentArea.appendChild(container);
        }
    }
    if (!container) return;

    container.innerHTML = '<div class="loading-indicator">로딩 중...</div>';

    try {
        const response = await invokeWithTimeout('get_etf_performance', {
            accessToken: auth.accessToken || '',
            code: code
        }, 15000);

        if (response && response.data) {
            const data = response.data;
            const returns = data.returns || {};

            const formatBar = (val) => {
                const width = Math.min(Math.abs(val) * 2, 100);
                const color = val >= 0 ? '#22C55E' : '#EF4444';
                return `
                    <div class="etf-bar-container">
                        <div class="etf-bar" style="width: ${width}%; background: ${color};"></div>
                    </div>
                `;
            };

            const formatRate = (v) => {
                if (!v && v !== 0) return '-';
                const sign = v >= 0 ? '+' : '';
                return `${sign}${v.toFixed(2)}%`;
            };

            container.innerHTML = `
                <div class="sd-card">
                    <div class="sd-card-title">기간별 수익률</div>
                    <div class="etf-returns-chart">
                        <div class="etf-return-row">
                            <span class="etf-period">1개월</span>
                            ${formatBar(returns['1m'] || 0)}
                            <span class="etf-rate ${(returns['1m'] || 0) >= 0 ? 'rise' : 'fall'}">${formatRate(returns['1m'])}</span>
                        </div>
                        <div class="etf-return-row">
                            <span class="etf-period">3개월</span>
                            ${formatBar(returns['3m'] || 0)}
                            <span class="etf-rate ${(returns['3m'] || 0) >= 0 ? 'rise' : 'fall'}">${formatRate(returns['3m'])}</span>
                        </div>
                        <div class="etf-return-row">
                            <span class="etf-period">6개월</span>
                            ${formatBar(returns['6m'] || 0)}
                            <span class="etf-rate ${(returns['6m'] || 0) >= 0 ? 'rise' : 'fall'}">${formatRate(returns['6m'])}</span>
                        </div>
                        <div class="etf-return-row">
                            <span class="etf-period">1년</span>
                            ${formatBar(returns['1y'] || 0)}
                            <span class="etf-rate ${(returns['1y'] || 0) >= 0 ? 'rise' : 'fall'}">${formatRate(returns['1y'])}</span>
                        </div>
                        <div class="etf-return-row">
                            <span class="etf-period">YTD</span>
                            ${formatBar(returns['ytd'] || 0)}
                            <span class="etf-rate ${(returns['ytd'] || 0) >= 0 ? 'rise' : 'fall'}">${formatRate(returns['ytd'])}</span>
                        </div>
                    </div>
                </div>
            `;
        } else {
            container.innerHTML = '<div class="empty-state">수익률 정보를 불러올 수 없습니다</div>';
        }
    } catch (error) {
        console.error('Failed to load ETF returns:', error);
        container.innerHTML = '<div class="empty-state">수익률 정보를 불러올 수 없습니다</div>';
    }
}

async function loadEtfDividendTab(code) {
    // 분배금 탭 로드
    let container = document.getElementById('info-dividend');
    if (!container) {
        const contentArea = document.querySelector('.stock-detail-content') || document.querySelector('.stock-tabs')?.parentElement;
        if (contentArea) {
            container = document.createElement('div');
            container.id = 'info-dividend';
            container.className = 'info-content';
            container.style.display = 'none';
            contentArea.appendChild(container);
        }
    }
    if (!container) return;

    container.innerHTML = '<div class="loading-indicator">로딩 중...</div>';

    try {
        const response = await invokeWithTimeout('get_etf_performance', {
            accessToken: auth.accessToken || '',
            code: code
        }, 15000);

        if (response && response.data) {
            const data = response.data;
            const dividends = data.dividends || [];
            const divYield = data.dividend_yield || 0;

            let dividendHtml = '';
            if (dividends.length > 0) {
                dividendHtml = `
                    <table class="sd-table">
                        <thead>
                            <tr>
                                <th>지급일</th>
                                <th>금액</th>
                                <th>유형</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${dividends.map(d => `
                                <tr>
                                    <td>${d.date || '-'}</td>
                                    <td>${(d.amount || 0).toLocaleString()}원</td>
                                    <td>${d.type || '현금분배'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `;
            } else {
                dividendHtml = `
                    <div class="empty-state">
                        <p>분배금 이력이 없거나 데이터를 불러올 수 없습니다.</p>
                    </div>
                `;
            }

            container.innerHTML = `
                <div class="sd-card">
                    <div class="sd-card-title">분배금 정보</div>
                    <div class="etf-dividend-summary">
                        <div class="etf-dividend-item">
                            <span class="label">배당수익률 (TTM)</span>
                            <span class="value">${divYield.toFixed(2)}%</span>
                        </div>
                    </div>
                    ${dividendHtml}
                </div>
            `;
        } else {
            container.innerHTML = `
                <div class="sd-card">
                    <div class="sd-card-title">분배금 정보</div>
                    <div class="empty-state">분배금 정보를 불러올 수 없습니다</div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Failed to load ETF dividend:', error);
        container.innerHTML = '<div class="empty-state">분배금 정보를 불러올 수 없습니다</div>';
    }
}

// window에 openEtfDetail 노출
window.openEtfDetail = openEtfDetail;

// =============================================================================
// Phase 11-1: 통합 종목검색 (자동완성)
// =============================================================================

let unifiedSearchTimer = null;
let unifiedSearchInitialized = false;

function initUnifiedSearch() {
    if (unifiedSearchInitialized) return;
    unifiedSearchInitialized = true;

    const input = document.getElementById('unified-search-input');
    const dropdown = document.getElementById('unified-search-dropdown');
    const clearBtn = document.getElementById('unified-search-clear');
    const resultsContainer = document.getElementById('unified-search-results');

    if (!input) return;

    // 입력 이벤트 (디바운스 300ms)
    input.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearBtn.style.display = query ? 'block' : 'none';

        clearTimeout(unifiedSearchTimer);
        if (query.length < 1) {
            dropdown.style.display = 'none';
            return;
        }

        unifiedSearchTimer = setTimeout(() => searchUnified(query), 300);
    });

    // 클리어 버튼
    clearBtn?.addEventListener('click', () => {
        input.value = '';
        dropdown.style.display = 'none';
        clearBtn.style.display = 'none';
        input.focus();
    });

    // ESC로 드롭다운 닫기
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
        // 화살표 네비게이션
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            navigateSearchResults(e.key === 'ArrowDown' ? 1 : -1);
        }
        if (e.key === 'Enter') {
            const selected = resultsContainer?.querySelector('.search-result-item.selected');
            if (selected) {
                selected.click();
            }
        }
    });

    // 외부 클릭으로 닫기
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.unified-search-container')) {
            dropdown.style.display = 'none';
        }
    });
}

function navigateSearchResults(direction) {
    const items = document.querySelectorAll('.search-result-item');
    if (!items.length) return;

    let currentIdx = -1;
    items.forEach((item, idx) => {
        if (item.classList.contains('selected')) currentIdx = idx;
    });

    items.forEach(item => item.classList.remove('selected'));

    let newIdx = currentIdx + direction;
    if (newIdx < 0) newIdx = items.length - 1;
    if (newIdx >= items.length) newIdx = 0;

    items[newIdx]?.classList.add('selected');
    items[newIdx]?.scrollIntoView({ block: 'nearest' });
}

async function searchUnified(query) {
    const dropdown = document.getElementById('unified-search-dropdown');
    const resultsContainer = document.getElementById('unified-search-results');

    if (!dropdown || !resultsContainer) return;

    try {
        const response = await invokeWithTimeout('search_stocks', {
            accessToken: auth.accessToken || '',
            query: query,
            limit: 15
        }, 5000);

        if (!response || !response.results) {
            dropdown.style.display = 'none';
            return;
        }

        const results = response.results;
        if (results.length === 0) {
            resultsContainer.innerHTML = '<div class="search-no-results">검색 결과가 없습니다</div>';
            dropdown.style.display = 'block';
            return;
        }

        // 결과 렌더링
        resultsContainer.innerHTML = results.map((item, idx) => {
            const icon = item.type === 'stock_kr' ? '🇰🇷' :
                        item.type === 'stock_us' ? '🇺🇸' : '📦';
            const code = item.code || item.symbol || '';
            const changePct = item.change_pct || 0;
            const changeClass = changePct > 0 ? 'rise' : changePct < 0 ? 'fall' : '';
            const changeSign = changePct > 0 ? '+' : '';

            return `
                <div class="search-result-item ${idx === 0 ? 'selected' : ''}"
                     data-code="${code}"
                     data-type="${item.type}"
                     data-name="${item.name || ''}">
                    <span class="search-item-icon">${icon}</span>
                    <div class="search-item-info">
                        <span class="search-item-name">${item.name || code}</span>
                        <span class="search-item-code">${code} · ${item.market || ''}</span>
                    </div>
                    <span class="search-item-change ${changeClass}">${changeSign}${changePct.toFixed(2)}%</span>
                </div>
            `;
        }).join('');

        // 클릭 이벤트
        resultsContainer.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                const code = item.dataset.code;
                const type = item.dataset.type;

                dropdown.style.display = 'none';
                document.getElementById('unified-search-input').value = '';
                document.getElementById('unified-search-clear').style.display = 'none';

                // 타입에 따라 상세 페이지 열기
                if (type === 'stock_kr') {
                    openStockDetail(code, 'kis_kr');
                } else if (type === 'stock_us') {
                    openStockDetail(code, 'kis_us');
                } else if (type === 'etf') {
                    openEtfDetail(code);
                }
            });
        });

        dropdown.style.display = 'block';

    } catch (error) {
        console.error('Search error:', error);
        dropdown.style.display = 'none';
    }
}

// =============================================================================
// Phase 11-2: BBooster AI 추천
// =============================================================================

let currentAiMarket = 'kr';

async function loadBBoosterAI() {
    const restrictionEl = document.getElementById('bbooster-ai-restriction');
    const contentEl = document.getElementById('bbooster-ai-content');

    // Pro 이상 또는 admin 체크
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        if (restrictionEl) restrictionEl.style.display = 'flex';
        if (contentEl) contentEl.style.display = 'none';
        return;
    }
    if (restrictionEl) restrictionEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';

    // 탭 이벤트 바인딩
    initAiTabEvents();

    // 초기 로드
    loadAiRecommendations(currentAiMarket);
}

let aiTabEventsInitialized = false;
function initAiTabEvents() {
    if (aiTabEventsInitialized) return;
    aiTabEventsInitialized = true;

    document.querySelectorAll('.ai-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.ai-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentAiMarket = tab.dataset.market;
            loadAiRecommendations(currentAiMarket);
        });
    });
}

async function loadAiRecommendations(market) {
    const container = document.getElementById('ai-categories');
    const updatedEl = document.getElementById('ai-updated-time');

    if (!container) return;

    container.innerHTML = `
        <div class="ai-loading">
            <div class="loading-spinner"></div>
            <span>AI 추천 종목을 불러오는 중...</span>
        </div>
    `;

    try {
        const response = await invokeWithTimeout('get_ai_recommendations', {
            accessToken: auth.accessToken || '',
            market: market
        }, 15000);

        if (!response || !response.categories) {
            container.innerHTML = '<div class="ai-empty">추천 데이터를 불러올 수 없습니다</div>';
            return;
        }

        // 업데이트 시간
        if (updatedEl && response.updated_at) {
            const date = new Date(response.updated_at);
            updatedEl.textContent = `마지막 업데이트: ${date.toLocaleString('ko-KR')}`;
        }

        // 카테고리 렌더링
        if (response.categories.length === 0) {
            container.innerHTML = '<div class="ai-empty">현재 추천 종목이 없습니다</div>';
            return;
        }

        container.innerHTML = response.categories.map(cat => {
            const itemsHtml = cat.items && cat.items.length > 0
                ? cat.items.map(item => {
                    const changePct = item.change_pct || 0;
                    const changeClass = changePct > 0 ? 'rise' : changePct < 0 ? 'fall' : '';
                    const changeSign = changePct > 0 ? '+' : '';
                    return `
                        <tr class="ai-stock-row" data-code="${item.code}" data-market="${market}">
                            <td class="ai-stock-name">${item.name || item.code}</td>
                            <td class="ai-stock-price">${(item.price || 0).toLocaleString()}</td>
                            <td class="ai-stock-change ${changeClass}">${changeSign}${changePct.toFixed(2)}%</td>
                            <td class="ai-stock-signal">${item.signal || ''}</td>
                        </tr>
                    `;
                }).join('')
                : '<tr><td colspan="4" class="ai-empty-cell">종목 없음</td></tr>';

            return `
                <div class="ai-category-card">
                    <div class="ai-category-header">
                        <h3 class="ai-category-title">${cat.title}</h3>
                        <p class="ai-category-desc">${cat.description}</p>
                    </div>
                    <table class="ai-stock-table">
                        <thead>
                            <tr>
                                <th>종목명</th>
                                <th>현재가</th>
                                <th>등락률</th>
                                <th>시그널</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${itemsHtml}
                        </tbody>
                    </table>
                </div>
            `;
        }).join('');

        // 종목 클릭 이벤트
        container.querySelectorAll('.ai-stock-row').forEach(row => {
            row.addEventListener('click', () => {
                const code = row.dataset.code;
                const market = row.dataset.market;

                if (market === 'kr') {
                    openStockDetail(code, 'kis_kr');
                } else if (market === 'us') {
                    openStockDetail(code, 'kis_us');
                } else if (market === 'etf') {
                    openEtfDetail(code);
                }
            });
        });

    } catch (error) {
        console.error('AI recommendations error:', error);
        container.innerHTML = '<div class="ai-empty">추천 데이터를 불러올 수 없습니다</div>';
    }
}

// 재무 요약 로드 (StockEasy 스타일)
async function loadFinancialSummary(code) {
    const summaryContent = document.getElementById('info-summary');
    if (!summaryContent) return;

    try {
        const response = await invokeWithTimeout('get_stock_financial_summary', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        if (response && response.data) {
            const data = response.data;
            const isPremium = response.is_premium;

            // 재무 그리드 렌더링
            const financialGridHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">주요 지표</div>
                    <div class="sd-financial-grid">
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">시가총액</span>
                            <span class="sd-financial-value">${formatBillions(data.market_cap) || '-'}</span>
                        </div>
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">PER</span>
                            <span class="sd-financial-value">${data.per > 0 ? data.per.toFixed(2) : '-'}</span>
                        </div>
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">PBR</span>
                            <span class="sd-financial-value">${data.pbr > 0 ? data.pbr.toFixed(2) : '-'}</span>
                        </div>
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">EPS</span>
                            <span class="sd-financial-value">${data.eps > 0 ? data.eps.toLocaleString() : '-'}</span>
                        </div>
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">52주 최고</span>
                            <span class="sd-financial-value positive">${data.high_52w > 0 ? data.high_52w.toLocaleString() : '-'}</span>
                        </div>
                        <div class="sd-financial-item">
                            <span class="sd-financial-label">52주 최저</span>
                            <span class="sd-financial-value negative">${data.low_52w > 0 ? data.low_52w.toLocaleString() : '-'}</span>
                        </div>
                        <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                            <span class="sd-financial-label">매출액</span>
                            <span class="sd-financial-value">${data.revenue_formatted || '-'}</span>
                        </div>
                        <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                            <span class="sd-financial-label">영업이익</span>
                            <span class="sd-financial-value">${data.operating_profit_formatted || '-'}</span>
                        </div>
                    </div>
                </div>
            `;

            // 투자지표 등급 계산
            const growthGrade = getIndicatorGrade('growth', data.revenue_growth || 0);
            const profitGrade = getIndicatorGrade('profitability', data.roe || 0);
            const stabilityGrade = getIndicatorGrade('stability', data.debt_ratio || 100);
            const valuationGrade = getIndicatorGrade('valuation', data.per || 0);

            const indicatorsHtml = `
                <div class="sd-card ${!isPremium ? 'blur-section' : ''}">
                    <div class="sd-card-title">투자 지표</div>
                    <div class="sd-indicators-grid">
                        <div class="sd-indicator-card">
                            <div class="sd-indicator-title">성장성</div>
                            <span class="sd-indicator-badge ${growthGrade.class}">${growthGrade.grade}</span>
                        </div>
                        <div class="sd-indicator-card">
                            <div class="sd-indicator-title">수익성</div>
                            <span class="sd-indicator-badge ${profitGrade.class}">${profitGrade.grade}</span>
                        </div>
                        <div class="sd-indicator-card">
                            <div class="sd-indicator-title">안정성</div>
                            <span class="sd-indicator-badge ${stabilityGrade.class}">${stabilityGrade.grade}</span>
                        </div>
                        <div class="sd-indicator-card">
                            <div class="sd-indicator-title">밸류에이션</div>
                            <span class="sd-indicator-badge ${valuationGrade.class}">${valuationGrade.grade}</span>
                        </div>
                    </div>
                    ${!isPremium ? `
                        <div class="blur-overlay">
                            <div class="blur-icon">🔒</div>
                            <div class="blur-message">
                                <p>Hub 이상 요금제에서 이용 가능</p>
                                <span>상세 투자 지표를 확인하세요</span>
                                <button class="upgrade-btn" onclick="navigateTo('settings')">업그레이드</button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;

            // 컨센서스 섹션 (프리미엄)
            const consensusHtml = isPremium ? `
                <div class="sd-card consensus-section">
                    <div class="sd-consensus-header">
                        <h4>투자의견</h4>
                        <span class="sd-target-price">목표가: ${data.target_price > 0 ? data.target_price.toLocaleString() + '원' : '-'}</span>
                    </div>
                    <span class="sd-recommendation ${data.recommendation === '매수' ? 'buy' : data.recommendation === '보유' ? 'hold' : 'sell'}">${data.recommendation || '-'}</span>
                </div>
            ` : '';

            summaryContent.innerHTML = financialGridHtml + indicatorsHtml + consensusHtml;
        }
    } catch (error) {
        console.error('Failed to load financial summary:', error);
        summaryContent.innerHTML = '<div class="sd-empty-state">재무 정보를 불러올 수 없습니다</div>';
    }
}

// 국내 종목 재무 요약 로드 (Phase 8-2) - StockEasy 스타일 리팩토링
// 현재 재무 데이터 저장 (연간/분기 토글용)
let currentFinancialDataKr = { annual: null, quarter: null };
let currentFinancialCode = '';

async function loadFinancialSummaryKr(code) {
    const summaryContent = document.getElementById('info-summary');
    if (!summaryContent) return;

    summaryContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>정보를 불러오는 중...</span></div>';

    currentFinancialCode = code;
    currentFinancialDataKr = { annual: null, quarter: null };

    try {
        // 요약 정보와 연간 재무추이 병렬 로드
        const [summaryResp, financialsResp] = await Promise.all([
            invokeWithTimeout('get_stock_summary_kr', {
                accessToken: auth.accessToken || '',
                code: code
            }, 10000),
            invokeWithTimeout('get_stock_financials_kr', {
                accessToken: auth.accessToken || '',
                code: code,
                finType: 'annual'
            }, 10000)
        ]);

        const summary = summaryResp?.data || {};
        const financials = financialsResp?.data || {};
        currentFinancialDataKr.annual = financials;

        // 최신 재무 데이터에서 값 추출 (연간 기준)
        const latestRevenue = financials.revenue?.length > 0 ? financials.revenue[financials.revenue.length - 1] : 0;
        const latestOpProfit = financials.operating_profit?.length > 0 ? financials.operating_profit[financials.operating_profit.length - 1] : 0;
        const latestNetIncome = financials.net_income?.length > 0 ? financials.net_income[financials.net_income.length - 1] : 0;
        const latestEps = financials.eps?.length > 0 ? financials.eps[financials.eps.length - 1] : 0;
        const opm = latestRevenue > 0 ? ((latestOpProfit / latestRevenue) * 100).toFixed(1) : '-';
        const latestPeriod = financials.periods?.length > 0 ? financials.periods[financials.periods.length - 1] : '';
        const isLatestEstimate = financials.isConsensus?.length > 0 ? financials.isConsensus[financials.isConsensus.length - 1] : false;

        // 요약 재무 카드 - StockEasy 스타일 6개 항목
        const summaryCardHtml = `
            <div class="sd-card">
                <div class="sd-card-title">
                    주요 재무지표
                    <span class="sd-basis-label">${latestPeriod ? `기준: ${latestPeriod}${isLatestEstimate ? '' : ' (연간)'}` : ''}</span>
                </div>
                <div class="sd-financial-grid sd-grid-6">
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">시가총액</span>
                        <span class="sd-financial-value">${summary.market_cap || '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">매출액</span>
                        <span class="sd-financial-value">${latestRevenue > 0 ? formatFinancialValue(latestRevenue) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">영업이익</span>
                        <span class="sd-financial-value ${latestOpProfit < 0 ? 'negative' : ''}">${latestOpProfit !== 0 ? formatFinancialValue(latestOpProfit) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">OPM</span>
                        <span class="sd-financial-value ${parseFloat(opm) < 0 ? 'negative' : ''}">${opm !== '-' ? opm + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">EPS</span>
                        <span class="sd-financial-value">${latestEps !== 0 ? latestEps.toLocaleString() + '원' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">당기순이익</span>
                        <span class="sd-financial-value ${latestNetIncome < 0 ? 'negative' : ''}">${latestNetIncome !== 0 ? formatFinancialValue(latestNetIncome) : '-'}</span>
                    </div>
                </div>
            </div>
        `;

        // StockEasy 완전 복제: 2열 레이아웃 + 연간/분기 동시 표시
        const financialChartsHtml = `
            <div class="sd-trend-section">
                <div class="sd-trend-note">연간은 4Q 기준이며, (E)는 전망치를 포함합니다.</div>

                <!-- 매출액 + 영업이익: 2열 나란히 -->
                <div class="sd-trend-row">
                    <!-- 매출액 -->
                    <div class="sd-trend-card">
                        <div class="sd-trend-card-header">
                            <span class="sd-trend-dot blue"></span>
                            <span class="sd-trend-title">매출액</span>
                        </div>
                        <div class="sd-trend-sub-label">연간 (4Q)</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-revenue-annual"></canvas></div>
                        <div class="sd-trend-sub-label">분기별</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-revenue-quarter"></canvas></div>
                    </div>

                    <!-- 영업이익 -->
                    <div class="sd-trend-card">
                        <div class="sd-trend-card-header">
                            <span class="sd-trend-dot green"></span>
                            <span class="sd-trend-title">영업이익</span>
                            <span class="sd-trend-legend-line">── OPM</span>
                        </div>
                        <div class="sd-trend-sub-label">연간 (4Q)</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-op-annual"></canvas></div>
                        <div class="sd-trend-sub-label">분기별</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-op-quarter"></canvas></div>
                    </div>
                </div>

                <!-- EPS + EPS 전망추이: 2열 나란히 -->
                <div class="sd-trend-row">
                    <!-- EPS -->
                    <div class="sd-trend-card">
                        <div class="sd-trend-card-header">
                            <span class="sd-trend-dot orange"></span>
                            <span class="sd-trend-title">EPS</span>
                        </div>
                        <div class="sd-trend-sub-label">연간 (4Q)</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-eps-annual"></canvas></div>
                        <div class="sd-trend-sub-label">분기별</div>
                        <div class="sd-trend-chart-wrapper"><canvas id="sd-fc-eps-quarter"></canvas></div>
                    </div>

                    <!-- EPS 전망추이 -->
                    <div class="sd-trend-card">
                        <div class="sd-trend-card-header">
                            <span class="sd-trend-dot" style="background:#a855f7"></span>
                            <span class="sd-trend-title">EPS 전망 추이</span>
                        </div>
                        <div id="sd-eps-forecast-content" class="sd-eps-forecast-empty">
                            <div class="sd-empty-card">데이터 없음</div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        summaryContent.innerHTML = summaryCardHtml + financialChartsHtml;

        // 연간 + 분기 데이터 동시 로드 후 모든 차트 렌더링
        loadAndRenderAllFinancialCharts(code, financials);

    } catch (error) {
        console.error('Failed to load KR financial summary:', error);
        summaryContent.innerHTML = '<div class="sd-empty-state">재무 정보를 불러올 수 없습니다</div>';
    }
}

// =====================================================
// StockEasy 완전 복제 — 재무추이 차트 시스템
// =====================================================

// 색상 정의 (stockeasy 정확 복제)
const FINANCIAL_CHART_COLORS = {
    revenue: {
        positive: '#3b82f6',          // 파란색
        positive_est: 'rgba(59, 130, 246, 0.15)',
        negative: '#ef4444',          // 빨간색
        negative_est: 'rgba(239, 68, 68, 0.15)',
        border: '#3b82f6',
    },
    operating: {
        positive: '#22c55e',          // 초록색
        positive_est: 'rgba(34, 197, 94, 0.15)',
        negative: '#ef4444',
        negative_est: 'rgba(239, 68, 68, 0.15)',
        border: '#22c55e',
    },
    eps: {
        positive: '#f97316',          // 주황색
        positive_est: 'rgba(249, 115, 22, 0.15)',
        negative: '#ef4444',
        negative_est: 'rgba(239, 68, 68, 0.15)',
        border: '#f97316',
    },
};

// 연간 + 분기 데이터 동시 로드 후 모든 차트 렌더링
async function loadAndRenderAllFinancialCharts(code, annualData) {
    console.log('[loadAndRenderAllFinancialCharts] 시작 code:', code, 'annualData:', annualData);
    currentFinancialDataKr.annual = annualData;

    // 분기 데이터 로드
    try {
        const quarterResp = await invokeWithTimeout('get_stock_financials_kr', {
            accessToken: auth.accessToken || '',
            code: code,
            finType: 'quarter'
        }, 10000);
        currentFinancialDataKr.quarter = quarterResp?.data || {};
    } catch (e) {
        console.error('Failed to load quarterly data:', e);
        currentFinancialDataKr.quarter = {};
    }

    const annual = currentFinancialDataKr.annual || {};
    const quarter = currentFinancialDataKr.quarter || {};
    console.log('[loadAndRenderAllFinancialCharts] annual:', annual);
    console.log('[loadAndRenderAllFinancialCharts] quarter:', quarter);

    // 매출액 — 연간 (API가 억원 단위로 반환) + GPM 라인
    renderStockEasyChart('sd-fc-revenue-annual', {
        periods: annual.periods || [],
        values: annual.revenue || [],
        isEstimate: annual.isConsensus || [],
        gpm: annual.gpm || [],  // 매출총이익률 (%)
    }, FINANCIAL_CHART_COLORS.revenue, 'revenue');

    // 매출액 — 분기
    renderStockEasyChart('sd-fc-revenue-quarter', {
        periods: quarter.periods || [],
        values: quarter.revenue || [],
        isEstimate: quarter.isConsensus || [],
        gpm: quarter.gpm || [],
    }, FINANCIAL_CHART_COLORS.revenue, 'revenue');

    // 영업이익 — 연간 (OPM 라인 포함)
    renderStockEasyChart('sd-fc-op-annual', {
        periods: annual.periods || [],
        values: annual.operating_profit || [],
        isEstimate: annual.isConsensus || [],
        opm: annual.opm || [],  // 영업이익률 (%)
    }, FINANCIAL_CHART_COLORS.operating, 'operating');

    // 영업이익 — 분기 (OPM 라인 포함)
    renderStockEasyChart('sd-fc-op-quarter', {
        periods: quarter.periods || [],
        values: quarter.operating_profit || [],
        isEstimate: quarter.isConsensus || [],
        opm: quarter.opm || [],
    }, FINANCIAL_CHART_COLORS.operating, 'operating');

    // EPS — 연간
    renderStockEasyChart('sd-fc-eps-annual', {
        periods: annual.periods || [],
        values: annual.eps || [],
        isEstimate: annual.isConsensus || [],
    }, FINANCIAL_CHART_COLORS.eps, 'eps');

    // EPS — 분기
    renderStockEasyChart('sd-fc-eps-quarter', {
        periods: quarter.periods || [],
        values: quarter.eps || [],
        isEstimate: quarter.isConsensus || [],
    }, FINANCIAL_CHART_COLORS.eps, 'eps');

    // EPS 전망추이 — FnGuide 컨센서스 수정 이력
    renderEpsForecastChart(code, annual);
}

// EPS 추정추이 차트 렌더링 (FnGuide 컨센서스 revision history)
// stockeasy처럼 EPS 추정치가 시간에 따라 어떻게 변했는지 라인차트로 표시
async function renderEpsForecastChart(code, annualData) {
    const container = document.getElementById('sd-eps-forecast-content');
    if (!container) return;

    // 로딩 표시
    container.innerHTML = '<div class="sd-empty-card">EPS 추정추이 로딩중...</div>';

    try {
        // FnGuide EPS revision history 가져오기
        const resp = await invokeWithTimeout('get_eps_revision_history', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        const revisionData = resp?.data || {};
        console.log('[EPS Revision] data:', revisionData);

        // FY1 (가장 가까운 미래 연도) 데이터 사용
        const fy1 = revisionData.fy1;

        if (!fy1 || !fy1.eps || fy1.eps.filter(v => v !== null).length < 2) {
            // revision data가 없으면 기존 연도별 막대 그래프로 폴백
            renderEpsForecastChartFallback(container, annualData);
            return;
        }

        // 라인 차트용 데이터 준비 (null 제외)
        const labels = [];
        const data = [];
        for (let i = 0; i < fy1.eps.length; i++) {
            if (fy1.eps[i] !== null) {
                labels.push(fy1.labels[i]);
                data.push(fy1.eps[i]);
            }
        }

        if (data.length < 2) {
            renderEpsForecastChartFallback(container, annualData);
            return;
        }

        // 첫 값과 마지막 값 비교해서 색상 및 변동률 결정
        const firstVal = data[0];
        const lastVal = data[data.length - 1];
        const changePercent = firstVal > 0 ? ((lastVal - firstVal) / firstVal * 100).toFixed(1) : 0;
        const isUp = lastVal >= firstVal;
        const lineColor = isUp ? '#22c55e' : '#ef4444';  // 상승=초록, 하락=빨강
        const bgColor = isUp ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)';
        const changeCount = data.length - 1;  // 변경 횟수

        const canvasId = 'eps-revision-chart-' + Date.now();

        // stockeasy 스타일 헤더
        container.innerHTML = `
            <div style="padding:4px 0;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;color:#888;">${fy1.year}년 전망치</span>
                    <span style="font-size:10px;color:${lineColor};font-weight:bold;">
                        ${isUp ? '▲' : '▼'} ${Math.abs(changePercent)}%
                        <span style="color:#666;font-weight:normal;margin-left:4px;">${changeCount}회 변경</span>
                    </span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:10px;color:#aaa;margin-bottom:4px;">
                    <span>시작: <b style="color:#ddd;">${firstVal.toLocaleString()}원</b></span>
                    <span>현재: <b style="color:${lineColor};">${lastVal.toLocaleString()}원</b></span>
                </div>
                <div style="position:relative;height:70px;">
                    <canvas id="${canvasId}"></canvas>
                </div>
            </div>
        `;

        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        if (canvas._chartInstance) {
            canvas._chartInstance.destroy();
        }

        canvas._chartInstance = new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    borderColor: lineColor,
                    backgroundColor: bgColor,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                    pointBackgroundColor: lineColor,
                    pointBorderColor: '#fff',
                    pointBorderWidth: 1,
                    datalabels: { display: false }  // 헤더에 시작/현재 표시하므로 라벨 제거
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: { top: 5, right: 10, bottom: 0, left: 10 }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `EPS 추정: ${ctx.raw?.toLocaleString() || 0}원`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: lineColor, font: { size: 8 } }  // X축 색상 = 라인 색상
                    },
                    y: {
                        display: false,
                        beginAtZero: false
                    }
                }
            }
        });

    } catch (error) {
        console.error('[EPS Revision] error:', error);
        // 에러 시 기존 연도별 막대 그래프로 폴백
        renderEpsForecastChartFallback(container, annualData);
    }
}

// EPS 전망 폴백: revision data 없을 때 연도별 막대 그래프
function renderEpsForecastChartFallback(container, annualData) {
    const periods = annualData.periods || [];
    const eps = annualData.eps || [];
    const isConsensus = annualData.isConsensus || [];

    // 전망치 EPS만 필터링
    const forecastData = [];
    for (let i = 0; i < periods.length; i++) {
        if (isConsensus[i] && eps[i] && eps[i] > 0) {
            forecastData.push({ period: periods[i], eps: eps[i] });
        }
    }

    if (forecastData.length === 0) {
        container.innerHTML = '<div class="sd-empty-card">전망치 데이터 없음</div>';
        return;
    }

    const canvasId = 'eps-forecast-chart-' + Date.now();

    container.innerHTML = `
        <div style="padding:4px 0;">
            <div style="font-size:11px;color:#888;margin-bottom:6px;text-align:center;">연도별 EPS 전망</div>
            <div style="position:relative;height:100px;">
                <canvas id="${canvasId}"></canvas>
            </div>
        </div>
    `;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    if (canvas._chartInstance) canvas._chartInstance.destroy();

    canvas._chartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: forecastData.map(d => d.period),
            datasets: [{
                data: forecastData.map(d => d.eps),
                backgroundColor: 'rgba(168, 85, 247, 0.7)',
                borderColor: '#a855f7',
                borderWidth: 1,
                borderRadius: 4,
                datalabels: {
                    display: true,
                    anchor: 'end',
                    align: 'top',
                    offset: 2,
                    color: '#a855f7',
                    font: { size: 10, weight: 'bold' },
                    formatter: (v) => v ? v.toLocaleString() + '원' : ''
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 25, right: 10, bottom: 5, left: 10 } },
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => `EPS: ${ctx.raw?.toLocaleString() || 0}원` } }
            },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#888', font: { size: 9 } } },
                y: { display: false, beginAtZero: false }
            }
        }
    });
}

// StockEasy 스타일 차트 렌더링 (실적/전망치 분리 + 점선 테두리)
function renderStockEasyChart(canvasId, chartData, colorSet, chartType) {
    console.log('[renderStockEasyChart] 시작:', canvasId, chartData);

    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn('[renderStockEasyChart] canvas 없음:', canvasId);
        return;
    }

    // 기존 차트 제거
    if (canvas._chartInstance) {
        canvas._chartInstance.destroy();
    }

    const { periods, values, isEstimate, opm, gpm } = chartData;
    console.log('[renderStockEasyChart] 데이터:', { periods, values, isEstimate, opm });

    if (!values || values.length === 0) {
        console.warn('[renderStockEasyChart] 값 없음:', canvasId);
        canvas.parentElement.innerHTML = '<div class="sd-trend-empty">데이터 없음</div>';
        return;
    }

    if (typeof Chart === 'undefined') {
        console.error('[renderStockEasyChart] Chart.js 미로드');
        return;
    }

    // 실적 데이터 (전망치 자리는 null)
    const actualData = values.map((v, i) => isEstimate[i] ? null : v);
    // 전망치 데이터 (실적 자리는 null)
    const estimateData = values.map((v, i) => isEstimate[i] ? v : null);

    // X축 라벨 (전망치에 E 추가)
    const xLabels = periods.map((p, i) => {
        if (isEstimate[i] && !p.includes('(E)') && !p.includes('E')) {
            return p + '(E)';
        }
        return p;
    });

    // 숫자 포맷 함수
    const formatLabel = (v) => {
        if (v === null || v === undefined || v === 0) return '';
        if (chartType === 'eps') {
            return Math.round(v).toLocaleString('ko-KR') + '원';
        }
        const abs = Math.abs(v);
        const sign = v < 0 ? '-' : '';
        if (abs >= 10000) return sign + (abs / 10000).toFixed(1) + '조';
        if (abs >= 100) return sign + Math.round(abs) + '억';
        return sign + v;
    };

    // 데이터셋 구성
    const datasets = [];

    // datalabels 공통 설정 (막대용)
    const dataCount = periods.length;
    const labelFontSize = dataCount >= 7 ? 9 : 11;  // 분기 7개 이상일 때 작게

    const barDatalabels = {
        display: (ctx) => ctx.dataset.data[ctx.dataIndex] !== null,
        anchor: 'end',
        align: 'top',
        offset: 3,
        clip: false,
        color: '#ccc',
        font: { size: labelFontSize, weight: 'bold' },
        formatter: (v) => {
            if (v === null || v === undefined || v === 0) return '';
            if (chartType === 'eps') {
                return Math.round(v).toLocaleString() + '원';
            }
            const abs = Math.abs(v);
            const sign = v < 0 ? '-' : '';
            if (abs >= 10000) return sign + (abs / 10000).toFixed(1) + '조';
            if (abs >= 100) return sign + Math.round(abs) + '억';
            return sign + v;
        },
    };

    // 실적 막대 (채운 색상)
    datasets.push({
        type: 'bar',
        label: '실적',
        data: actualData,
        backgroundColor: actualData.map(v =>
            v === null ? 'transparent' : (v >= 0 ? colorSet.positive : colorSet.negative)
        ),
        borderColor: 'transparent',
        borderWidth: 0,
        borderRadius: 3,
        barPercentage: 0.6,
        categoryPercentage: 0.8,
        order: 2,
        datalabels: barDatalabels,  // ★ 명시적 추가
    });

    // 전망치 막대 (투명 배경 + 강조 테두리)
    datasets.push({
        type: 'bar',
        label: '전망',
        data: estimateData,
        backgroundColor: 'transparent',
        borderColor: estimateData.map(v =>
            v === null ? 'transparent' : (v >= 0 ? colorSet.border : '#ef4444')
        ),
        borderWidth: 2.5,
        borderRadius: 3,
        barPercentage: 0.6,
        categoryPercentage: 0.8,
        order: 2,
        datalabels: barDatalabels,  // ★ 명시적 추가
    });

    // OPM 라인 (영업이익 연간 차트에서만 - 분기는 제외)
    const isAnnualChart = canvasId.includes('annual');
    const hasOpmData = opm && opm.length > 0 && opm.some(v => v !== null && v !== undefined && v > 0);
    const showOpmLine = hasOpmData && chartType === 'operating' && isAnnualChart;

    if (showOpmLine) {
        datasets.push({
            type: 'line',
            label: 'OPM',
            data: opm,
            borderColor: '#f59e0b',  // 주황색
            borderWidth: 2,
            borderDash: [6, 3],
            pointRadius: 4,
            pointBackgroundColor: '#f59e0b',
            fill: false,
            yAxisID: 'y1',
            order: 1,
            datalabels: { display: false },
        });
    }

    // GPM 라인 (매출액 연간 차트에서만 + 실적 구간만 표시)
    // stockeasy 규칙: GPM은 실적만, 전망치(estimate) 구간은 라인 끊기
    const hasGpmData = gpm && gpm.length > 0 && gpm.some(v => v !== null && v !== undefined && v > 0);
    const showGpmLine = hasGpmData && chartType === 'revenue' && isAnnualChart;

    if (showGpmLine) {
        // 전망치 구간은 null로 설정하여 라인 끊기
        const gpmActualOnly = gpm.map((v, i) => isEstimate[i] ? null : v);
        datasets.push({
            type: 'line',
            label: 'GPM',
            data: gpmActualOnly,
            borderColor: '#3b82f6',  // 파란색
            borderWidth: 2,
            borderDash: [6, 3],
            pointRadius: 3,
            pointBackgroundColor: '#3b82f6',
            fill: false,
            yAxisID: 'y1',
            order: 1,
            spanGaps: false,  // null 구간 끊기
            datalabels: { display: false },
        });
    }

    try {
        console.log('[renderStockEasyChart] Chart 생성 시작:', canvasId, 'labels:', xLabels, 'datasets:', datasets);
        canvas._chartInstance = new Chart(canvas, {
            data: { labels: xLabels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                clip: false,
                interaction: { mode: 'index', intersect: false },
                layout: {
                    padding: { top: 35, bottom: 2, left: 4, right: 4 }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(17, 26, 46, 0.95)',
                        titleColor: '#E5E7EB',
                        bodyColor: '#E5E7EB',
                        borderColor: '#22304A',
                        borderWidth: 1,
                        padding: 8,
                        filter: (item) => item.raw !== null,
                        callbacks: {
                            label: (ctx) => {
                                const v = ctx.raw;
                                if (v === null) return null;
                                const isEst = isEstimate[ctx.dataIndex];
                                const estLabel = isEst ? ' (전망)' : '';
                                return formatLabel(v) + estLabel;
                            },
                        },
                    },
                    datalabels: {
                        display: (ctx) => ctx.dataset.data[ctx.dataIndex] !== null,
                        anchor: 'end',
                        align: 'top',
                        offset: 4,
                        clip: false,
                        color: '#ccc',
                        font: { size: 11, weight: 'bold' },
                        formatter: (v) => {
                            if (v === null || v === undefined || v === 0) return '';
                            if (chartType === 'eps') {
                                return Math.round(v).toLocaleString() + '원';
                            }
                            const abs = Math.abs(v);
                            const sign = v < 0 ? '-' : '';
                            if (abs >= 10000) return sign + (abs / 10000).toFixed(1) + '조';
                            if (abs >= 100) return sign + Math.round(abs) + '억';
                            return sign + v;
                        },
                    },
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: {
                            color: (ctx) => isEstimate[ctx.index] ? '#22c55e' : '#888',
                            font: { size: 9 },
                        },
                        grid: { display: false },
                    },
                    y: {
                        stacked: true,
                        grace: '10%',
                        ticks: {
                            color: '#666',
                            font: { size: 8 },
                            maxTicksLimit: 4,
                            callback: (v) => {
                                if (chartType === 'eps') {
                                    return v.toLocaleString();
                                }
                                const abs = Math.abs(v);
                                if (abs >= 10000) return (v / 10000).toFixed(0) + '조';
                                if (abs >= 100) return Math.round(v) + '억';
                                return v;
                            },
                        },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                    ...((showOpmLine || showGpmLine) ? {
                        y1: {
                            position: 'right',
                            display: true,
                            ticks: {
                                color: 'rgba(136,136,136,0.3)',
                                font: { size: 8 },
                                callback: (v) => v.toFixed(0) + '%',
                                maxTicksLimit: 3,
                            },
                            grid: { display: false },
                        }
                    } : {}),
                },
            },
        });
        console.log('[renderStockEasyChart] Chart 생성 완료:', canvasId);
    } catch (error) {
        console.error('[renderStockEasyChart] Chart 생성 오류:', canvasId, error);
    }
}

// 해외 종목 재무 요약 로드 (Phase 9)
async function loadFinancialSummaryUs(ticker) {
    const summaryContent = document.getElementById('info-summary');
    if (!summaryContent) return;

    summaryContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>Loading...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_summary_us', {
            accessToken: auth.accessToken || '',
            ticker: ticker
        }, 15000);

        const data = response?.data || {};

        // 요약 재무 카드 (USD 단위)
        const summaryCardHtml = `
            <div class="sd-card">
                <div class="sd-card-title">Key Metrics</div>
                <div class="sd-financial-grid">
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Market Cap</span>
                        <span class="sd-financial-value">${data.market_cap || '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">P/E</span>
                        <span class="sd-financial-value">${data.per > 0 ? data.per.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Forward P/E</span>
                        <span class="sd-financial-value">${data.forward_per > 0 ? data.forward_per.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">P/B</span>
                        <span class="sd-financial-value">${data.pbr > 0 ? data.pbr.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">EPS (TTM)</span>
                        <span class="sd-financial-value">$${data.eps > 0 ? data.eps.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROE</span>
                        <span class="sd-financial-value">${data.roe > 0 ? data.roe.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROA</span>
                        <span class="sd-financial-value">${data.roa > 0 ? data.roa.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Dividend</span>
                        <span class="sd-financial-value">${data.dividend_yield > 0 ? data.dividend_yield.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">52W High</span>
                        <span class="sd-financial-value positive">$${data.high_52w > 0 ? data.high_52w.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">52W Low</span>
                        <span class="sd-financial-value negative">$${data.low_52w > 0 ? data.low_52w.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Op. Margin</span>
                        <span class="sd-financial-value">${data.operating_margin > 0 ? data.operating_margin.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Profit Margin</span>
                        <span class="sd-financial-value">${data.profit_margin > 0 ? data.profit_margin.toFixed(1) + '%' : '-'}</span>
                    </div>
                </div>
            </div>
            <div class="sd-card">
                <div class="sd-card-title">Analyst Ratings</div>
                <div class="sd-consensus-grid">
                    <div class="sd-consensus-item">
                        <span class="sd-consensus-label">Target Price</span>
                        <span class="sd-consensus-value">$${data.target_price > 0 ? data.target_price.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-consensus-item">
                        <span class="sd-consensus-label">Recommendation</span>
                        <span class="sd-consensus-value">${data.recommendation || '-'}</span>
                    </div>
                </div>
            </div>
        `;

        summaryContent.innerHTML = summaryCardHtml;

    } catch (error) {
        console.error('Failed to load US financial summary:', error);
        summaryContent.innerHTML = '<div class="sd-empty-state">Failed to load financial information</div>';
    }
}

// 재무추이 차트 렌더링 (Chart.js)
function renderFinancialTrendChart(financials) {
    const canvas = document.getElementById('financial-trend-chart');
    if (!canvas) return;

    const periods = financials.periods || [];
    const revenue = financials.revenue || [];
    const opProfit = financials.operating_profit || [];

    // 기존 차트 제거
    if (window.financialTrendChartInstance) {
        window.financialTrendChartInstance.destroy();
    }

    // Chart.js가 로드되어 있는지 확인
    if (typeof Chart === 'undefined') {
        canvas.parentElement.innerHTML = '<div style="padding:20px;text-align:center;color:#9CA3AF;">차트를 불러올 수 없습니다</div>';
        return;
    }

    // API가 이미 억원 단위로 반환
    const revenueInBillion = revenue;
    const opProfitInBillion = opProfit;

    window.financialTrendChartInstance = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: periods,
            datasets: [
                {
                    label: '매출액 (억원)',
                    data: revenueInBillion,
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: 'rgba(59, 130, 246, 1)',
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: '영업이익 (억원)',
                    data: opProfitInBillion,
                    backgroundColor: 'rgba(34, 197, 94, 0.7)',
                    borderColor: 'rgba(34, 197, 94, 1)',
                    borderWidth: 1,
                    yAxisID: 'y'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#9CA3AF' }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#9CA3AF' },
                    grid: { color: 'rgba(156, 163, 175, 0.1)' }
                },
                y: {
                    type: 'linear',
                    position: 'left',
                    ticks: {
                        color: '#9CA3AF',
                        callback: function(value) {
                            return value.toLocaleString() + '억';
                        }
                    },
                    grid: { color: 'rgba(156, 163, 175, 0.1)' }
                }
            }
        }
    });
}

// 국내 종목 뉴스 로드 (Phase 8-2)
async function loadStockNewsKr(code) {
    const newsContent = document.getElementById('info-news');
    if (!newsContent) return;

    newsContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>뉴스를 불러오는 중...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_news_kr', {
            accessToken: auth.accessToken || '',
            code: code,
            limit: 20
        }, 10000);

        const items = response?.data?.items || [];

        if (items.length === 0) {
            newsContent.innerHTML = '<div class="sd-empty-state">최신 뉴스가 없습니다</div>';
            return;
        }

        let html = '<div class="sd-news-list">';
        for (const item of items) {
            html += `
                <a href="${item.url}" target="_blank" class="sd-news-item">
                    <div class="sd-news-title">${item.title}</div>
                    <div class="sd-news-meta">
                        <span class="sd-news-source">${item.source}</span>
                        <span class="sd-news-date">${item.date}</span>
                    </div>
                </a>
            `;
        }
        html += '</div>';

        newsContent.innerHTML = html;

    } catch (error) {
        console.error('Failed to load KR news:', error);
        newsContent.innerHTML = '<div class="sd-empty-state">뉴스를 불러올 수 없습니다</div>';
    }
}

// 뉴스/공시 로드 (StockEasy 스타일)
async function loadStockNews(code) {
    const newsContent = document.getElementById('info-news');
    if (!newsContent) return;

    newsContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>뉴스를 불러오는 중...</span></div>';

    try {
        // 뉴스 로드
        const newsResponse = await invokeWithTimeout('get_stock_news', {
            accessToken: auth.accessToken || '',
            code: code,
            limit: 15
        }, 10000);

        let newsHtml = '';
        if (newsResponse && newsResponse.data && newsResponse.data.news && newsResponse.data.news.length > 0) {
            newsHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">최신 뉴스</div>
                    <div class="sd-news-list">
                        ${newsResponse.data.news.map(item => `
                            <div class="sd-news-item" onclick="window.open('${item.url}', '_blank')">
                                <div class="sd-news-title">${item.title}</div>
                                <div class="sd-news-meta">
                                    <span class="sd-news-source">${item.source || '뉴스'}</span>
                                    <span class="sd-news-date">${formatNewsDate(item.date)}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            newsHtml = '<div class="sd-card"><div class="sd-empty-state">관련 뉴스가 없습니다</div></div>';
        }

        // 공시 로드
        const disclosureResponse = await invokeWithTimeout('get_stock_disclosures', {
            accessToken: auth.accessToken || '',
            code: code,
            limit: 10
        }, 10000);

        let disclosureHtml = '';
        if (disclosureResponse && disclosureResponse.data && disclosureResponse.data.length > 0) {
            disclosureHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">최근 공시</div>
                    <div class="sd-disclosure-list">
                        ${disclosureResponse.data.map(item => `
                            <div class="sd-disclosure-item">
                                <span class="sd-disclosure-title">${item.title}</span>
                                <span class="sd-disclosure-date">${formatNewsDate(item.date)}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            disclosureHtml = '<div class="sd-card"><div class="sd-empty-state">최근 공시가 없습니다</div></div>';
        }

        newsContent.innerHTML = newsHtml + disclosureHtml;

    } catch (error) {
        console.error('Failed to load news:', error);
        newsContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">뉴스를 불러올 수 없습니다</div></div>';
    }
}

// 기업 정보 로드 (StockEasy 스타일)
async function loadCompanyInfo(code) {
    const companyContent = document.getElementById('info-company');
    if (!companyContent) return;

    companyContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>기업 정보를 불러오는 중...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_company', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        if (response && response.data) {
            const data = response.data;
            const isPremium = response.is_premium;

            // 기본 기업 정보
            const companyInfoHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">기업 개요</div>
                    <div class="sd-company-grid">
                        <div class="sd-company-item">
                            <span class="sd-company-label">회사명</span>
                            <span class="sd-company-value">${data.name || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">업종</span>
                            <span class="sd-company-value">${data.sector || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">시장</span>
                            <span class="sd-company-value">${data.market || '-'}</span>
                        </div>
                    </div>
                </div>
            `;

            // 세그먼트 매출 (도넛 차트) - 프리미엄
            let segmentHtml = '';
            if (isPremium && data.segments && data.segments.length > 0) {
                segmentHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">세그먼트별 매출</div>
                        ${renderDonutChart(data.segments)}
                    </div>
                `;
            } else if (!isPremium) {
                segmentHtml = `
                    <div class="sd-card blur-section">
                        <div class="sd-card-title">세그먼트별 매출</div>
                        <div style="height: 180px; display: flex; align-items: center; justify-content: center; color: #9CA3AF;">
                            세그먼트 데이터
                        </div>
                        <div class="blur-overlay">
                            <div class="blur-icon">🔒</div>
                            <div class="blur-message">
                                <p>Hub 이상 요금제에서 이용 가능</p>
                                <button class="upgrade-btn" onclick="navigateTo('settings')">업그레이드</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            // 동종업계 비교
            let comparablesHtml = '';
            if (data.comparables && data.comparables.length > 0) {
                comparablesHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">동종업계 비교</div>
                        <div class="sd-comparables-list">
                            ${data.comparables.map(comp => `
                                <div class="sd-comparable-item" onclick="openStockDetail('${comp.code}', 'kis_kr')">
                                    <span class="sd-comp-name">${comp.name}</span>
                                    <span class="sd-comp-price">${comp.price?.toLocaleString() || '-'}원</span>
                                    <span class="sd-comp-change ${(comp.change || 0) >= 0 ? 'positive' : 'negative'}">
                                        ${(comp.change || 0) >= 0 ? '+' : ''}${(comp.change || 0).toFixed(2)}%
                                    </span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } else {
                comparablesHtml = '<div class="sd-card"><div class="sd-empty-state">동종업계 비교 데이터가 없습니다</div></div>';
            }

            companyContent.innerHTML = companyInfoHtml + segmentHtml + comparablesHtml;
        } else {
            companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">기업 정보를 불러올 수 없습니다</div></div>';
        }
    } catch (error) {
        console.error('Failed to load company info:', error);
        companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">기업 정보를 불러올 수 없습니다</div></div>';
    }
}

// 기업 정보 로드 - 한국 종목 (Phase 8-3)
async function loadCompanyInfoKr(code) {
    const companyContent = document.getElementById('info-company');
    if (!companyContent) return;

    companyContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>기업 정보를 불러오는 중...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_company_kr', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        if (response && response.data) {
            const data = response.data;

            // 투자의견/목표가 섹션
            let consensusHtml = '';
            if (data.consensus) {
                const rating = data.consensus.rating || 0;
                const targetPrice = data.consensus.target_price || 0;
                const ratingText = rating >= 4 ? '매수' : rating >= 3 ? '중립' : rating >= 2 ? '매도' : '-';
                consensusHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">투자의견</div>
                        <div class="sd-consensus-grid">
                            <div class="sd-consensus-item">
                                <span class="sd-consensus-label">투자의견</span>
                                <span class="sd-consensus-value ${rating >= 4 ? 'positive' : rating <= 2 ? 'negative' : ''}">${ratingText}</span>
                            </div>
                            <div class="sd-consensus-item">
                                <span class="sd-consensus-label">목표주가</span>
                                <span class="sd-consensus-value">${targetPrice > 0 ? targetPrice.toLocaleString() + '원' : '-'}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            // 동종업계 비교 섹션
            let peersHtml = '';
            if (data.peers && data.peers.length > 0) {
                peersHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">동종업계 종목</div>
                        <div class="sd-comparables-list">
                            ${data.peers.map(peer => `
                                <div class="sd-comparable-item" onclick="openStockDetail('${peer.code}', 'kis_kr')">
                                    <span class="sd-comp-name">${peer.name}</span>
                                    <span class="sd-comp-price">${peer.price?.toLocaleString() || '-'}원</span>
                                    <span class="sd-comp-change ${(peer.change_percent || 0) >= 0 ? 'positive' : 'negative'}">
                                        ${(peer.change_percent || 0) >= 0 ? '+' : ''}${(peer.change_percent || 0).toFixed(2)}%
                                    </span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            // 리서치 리포트 섹션
            let researchHtml = '';
            if (data.researches && data.researches.length > 0) {
                researchHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">리서치 리포트</div>
                        <div class="sd-research-list">
                            ${data.researches.map(r => `
                                <div class="sd-research-item">
                                    <div class="sd-research-title">${r.title}</div>
                                    <div class="sd-research-meta">
                                        <span class="sd-research-broker">${r.broker}</span>
                                        <span class="sd-research-date">${formatResearchDate(r.date)}</span>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            companyContent.innerHTML = consensusHtml + peersHtml + researchHtml ||
                '<div class="sd-card"><div class="sd-empty-state">기업 정보가 없습니다</div></div>';
        } else {
            companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">기업 정보를 불러올 수 없습니다</div></div>';
        }
    } catch (error) {
        console.error('Failed to load company info (KR):', error);
        companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">기업 정보를 불러올 수 없습니다</div></div>';
    }
}

// 리서치 날짜 포맷
function formatResearchDate(dateStr) {
    if (!dateStr) return '';
    // 20260210 → 2026.02.10
    if (dateStr.length === 8) {
        return `${dateStr.slice(0, 4)}.${dateStr.slice(4, 6)}.${dateStr.slice(6, 8)}`;
    }
    return dateStr;
}

// =============================================================================
// Phase 9: 해외 종목 상세 (US Stocks)
// =============================================================================

// 해외 종목 뉴스 로드 (Phase 9)
async function loadStockNewsUs(ticker) {
    const newsContent = document.getElementById('info-news');
    if (!newsContent) return;

    newsContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>Loading news...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_news_us', {
            accessToken: auth.accessToken || '',
            ticker: ticker,
            limit: 20
        }, 15000);

        const items = response?.data?.items || [];

        if (items.length === 0) {
            newsContent.innerHTML = '<div class="sd-empty-state">No recent news available</div>';
            return;
        }

        let html = '<div class="sd-news-list">';
        for (const item of items) {
            html += `
                <a href="${item.url}" target="_blank" class="sd-news-item">
                    <div class="sd-news-title">${item.title}</div>
                    <div class="sd-news-meta">
                        <span class="sd-news-source">${item.source}</span>
                        <span class="sd-news-date">${item.date} ${item.time || ''}</span>
                    </div>
                </a>
            `;
        }
        html += '</div>';

        newsContent.innerHTML = html;

    } catch (error) {
        console.error('Failed to load US news:', error);
        newsContent.innerHTML = '<div class="sd-empty-state">Failed to load news</div>';
    }
}

// 해외 종목 기업 정보 로드 (Phase 9)
async function loadCompanyInfoUs(ticker) {
    const companyContent = document.getElementById('info-company');
    if (!companyContent) return;

    companyContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>Loading company info...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_company_us', {
            accessToken: auth.accessToken || '',
            ticker: ticker
        }, 15000);

        if (response && response.data) {
            const data = response.data;

            // 기업 개요
            const overviewHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">Company Overview</div>
                    <div class="sd-company-grid">
                        <div class="sd-company-item">
                            <span class="sd-company-label">Name</span>
                            <span class="sd-company-value">${data.name || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">Sector</span>
                            <span class="sd-company-value">${data.sector || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">Industry</span>
                            <span class="sd-company-value">${data.industry || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">Country</span>
                            <span class="sd-company-value">${data.country || '-'}</span>
                        </div>
                        <div class="sd-company-item">
                            <span class="sd-company-label">Employees</span>
                            <span class="sd-company-value">${data.employees || '-'}</span>
                        </div>
                    </div>
                </div>
            `;

            // 기업 설명
            let descriptionHtml = '';
            if (data.description) {
                descriptionHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">Description</div>
                        <p class="sd-description">${data.description}</p>
                    </div>
                `;
            }

            // 애널리스트 정보
            let analystHtml = '';
            if (data.target_price > 0 || data.recommendation) {
                analystHtml = `
                    <div class="sd-card">
                        <div class="sd-card-title">Analyst Ratings</div>
                        <div class="sd-consensus-grid">
                            <div class="sd-consensus-item">
                                <span class="sd-consensus-label">Target Price</span>
                                <span class="sd-consensus-value">$${data.target_price > 0 ? data.target_price.toFixed(2) : '-'}</span>
                            </div>
                            <div class="sd-consensus-item">
                                <span class="sd-consensus-label">Recommendation</span>
                                <span class="sd-consensus-value">${data.recommendation || '-'}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            companyContent.innerHTML = overviewHtml + descriptionHtml + analystHtml ||
                '<div class="sd-card"><div class="sd-empty-state">No company information available</div></div>';
        } else {
            companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">Failed to load company info</div></div>';
        }
    } catch (error) {
        console.error('Failed to load company info (US):', error);
        companyContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">Failed to load company info</div></div>';
    }
}

// 해외 종목 재무 탭 로드 (Phase 9)
async function loadFinancialTabUs(ticker) {
    const financialContent = document.getElementById('info-financial');
    if (!financialContent) return;

    financialContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>Loading financial data...</span></div>';

    try {
        const response = await invokeWithTimeout('get_stock_summary_us', {
            accessToken: auth.accessToken || '',
            ticker: ticker
        }, 15000);

        const data = response?.data || {};

        // 재무 지표 그리드
        const financialHtml = `
            <div class="sd-card">
                <div class="sd-card-title">Financial Metrics</div>
                <div class="sd-financial-grid">
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">P/E</span>
                        <span class="sd-financial-value">${data.per > 0 ? data.per.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Forward P/E</span>
                        <span class="sd-financial-value">${data.forward_per > 0 ? data.forward_per.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">P/B</span>
                        <span class="sd-financial-value">${data.pbr > 0 ? data.pbr.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">EPS (TTM)</span>
                        <span class="sd-financial-value">$${data.eps > 0 ? data.eps.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROE</span>
                        <span class="sd-financial-value">${data.roe > 0 ? data.roe.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROA</span>
                        <span class="sd-financial-value">${data.roa > 0 ? data.roa.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Oper. Margin</span>
                        <span class="sd-financial-value">${data.operating_margin > 0 ? data.operating_margin.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Profit Margin</span>
                        <span class="sd-financial-value">${data.profit_margin > 0 ? data.profit_margin.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Dividend Yield</span>
                        <span class="sd-financial-value">${data.dividend_yield > 0 ? data.dividend_yield.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Debt/Equity</span>
                        <span class="sd-financial-value">${data.debt_equity > 0 ? data.debt_equity.toFixed(2) : '-'}</span>
                    </div>
                </div>
            </div>
            <div class="sd-card">
                <div class="sd-card-title">Trading Info</div>
                <div class="sd-financial-grid">
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Volume</span>
                        <span class="sd-financial-value">${data.volume > 0 ? formatVolumeUs(data.volume) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">Avg Volume</span>
                        <span class="sd-financial-value">${data.avg_volume > 0 ? formatVolumeUs(data.avg_volume) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">52W High</span>
                        <span class="sd-financial-value positive">$${data.high_52w > 0 ? data.high_52w.toFixed(2) : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">52W Low</span>
                        <span class="sd-financial-value negative">$${data.low_52w > 0 ? data.low_52w.toFixed(2) : '-'}</span>
                    </div>
                </div>
            </div>
        `;

        financialContent.innerHTML = financialHtml;

    } catch (error) {
        console.error('Failed to load financial tab (US):', error);
        financialContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">Failed to load financial data</div></div>';
    }
}

// 거래량 포맷 (US)
function formatVolumeUs(volume) {
    if (volume >= 1e9) return (volume / 1e9).toFixed(2) + 'B';
    if (volume >= 1e6) return (volume / 1e6).toFixed(2) + 'M';
    if (volume >= 1e3) return (volume / 1e3).toFixed(1) + 'K';
    return volume.toLocaleString();
}

// 재무 탭 로드 (StockEasy 스타일)
async function loadFinancialTab(code) {
    const financialContent = document.getElementById('info-financial');
    if (!financialContent) return;

    financialContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>재무 정보를 불러오는 중...</span></div>';

    try {
        // 재무 추이 데이터 로드
        const trendResponse = await invokeWithTimeout('get_stock_financial_trend', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        // 재무 요약 데이터 로드
        const summaryResponse = await invokeWithTimeout('get_stock_financial_summary', {
            accessToken: auth.accessToken || '',
            code: code
        }, 10000);

        const isPremium = trendResponse?.is_premium || summaryResponse?.is_premium;
        const trendData = trendResponse?.data || {};
        const summaryData = summaryResponse?.data || {};

        // 실적 추이 차트 (DIV 기반)
        let trendChartHtml = '';
        if (isPremium && trendData.annual && trendData.annual.length > 0) {
            trendChartHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">실적 추이</div>
                    ${renderTrendChart(trendData.annual)}
                </div>
            `;
        } else if (!isPremium) {
            trendChartHtml = `
                <div class="sd-card blur-section">
                    <div class="sd-card-title">실적 추이</div>
                    <div style="height: 180px; display: flex; align-items: center; justify-content: center; color: #9CA3AF;">
                        실적 추이 차트
                    </div>
                    <div class="blur-overlay">
                        <div class="blur-icon">🔒</div>
                        <div class="blur-message">
                            <p>Hub 이상 요금제에서 이용 가능</p>
                            <span>상세 재무 데이터를 확인하세요</span>
                            <button class="upgrade-btn" onclick="navigateTo('settings')">업그레이드</button>
                        </div>
                    </div>
                </div>
            `;
        }

        // 재무건전성 점수
        const healthScore = calculateHealthScore(summaryData);
        const gradeInfo = getGrade(healthScore);

        let healthScoreHtml = '';
        if (isPremium) {
            healthScoreHtml = `
                <div class="sd-card">
                    <div class="sd-card-title">재무 건전성</div>
                    <div class="sd-health-score">
                        ${renderHealthCircle(healthScore, gradeInfo.class)}
                        <div class="sd-health-details">
                            <div class="sd-health-detail-item">
                                <span class="sd-health-detail-label">ROE</span>
                                <span class="sd-health-detail-value">${summaryData.roe > 0 ? summaryData.roe.toFixed(2) + '%' : '-'}</span>
                            </div>
                            <div class="sd-health-detail-item">
                                <span class="sd-health-detail-label">부채비율</span>
                                <span class="sd-health-detail-value">${summaryData.debt_ratio > 0 ? summaryData.debt_ratio.toFixed(1) + '%' : '-'}</span>
                            </div>
                            <div class="sd-health-detail-item">
                                <span class="sd-health-detail-label">배당수익률</span>
                                <span class="sd-health-detail-value">${summaryData.dividend_yield > 0 ? summaryData.dividend_yield.toFixed(2) + '%' : '-'}</span>
                            </div>
                            <div class="sd-health-detail-item">
                                <span class="sd-health-detail-label">BPS</span>
                                <span class="sd-health-detail-value">${summaryData.bps > 0 ? summaryData.bps.toLocaleString() + '원' : '-'}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            healthScoreHtml = `
                <div class="sd-card blur-section">
                    <div class="sd-card-title">재무 건전성</div>
                    <div style="height: 140px; display: flex; align-items: center; justify-content: center; color: #9CA3AF;">
                        재무 건전성 점수
                    </div>
                    <div class="blur-overlay">
                        <div class="blur-icon">🔒</div>
                        <div class="blur-message">
                            <p>Hub 이상 요금제에서 이용 가능</p>
                            <button class="upgrade-btn" onclick="navigateTo('settings')">업그레이드</button>
                        </div>
                    </div>
                </div>
            `;
        }

        // 상세 재무 지표
        let financialDetailsHtml = `
            <div class="sd-card">
                <div class="sd-card-title">상세 재무 지표</div>
                <div class="sd-financial-grid">
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROE</span>
                        <span class="sd-financial-value">${summaryData.roe > 0 ? summaryData.roe.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">ROA</span>
                        <span class="sd-financial-value">${summaryData.roa > 0 ? summaryData.roa.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                        <span class="sd-financial-label">부채비율</span>
                        <span class="sd-financial-value">${summaryData.debt_ratio > 0 ? summaryData.debt_ratio.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                        <span class="sd-financial-label">유보율</span>
                        <span class="sd-financial-value">${summaryData.reserve_ratio > 0 ? summaryData.reserve_ratio.toFixed(1) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">배당수익률</span>
                        <span class="sd-financial-value">${summaryData.dividend_yield > 0 ? summaryData.dividend_yield.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item">
                        <span class="sd-financial-label">BPS</span>
                        <span class="sd-financial-value">${summaryData.bps > 0 ? summaryData.bps.toLocaleString() : '-'}</span>
                    </div>
                    <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                        <span class="sd-financial-label">외국인지분율</span>
                        <span class="sd-financial-value">${summaryData.foreign_ratio > 0 ? summaryData.foreign_ratio.toFixed(2) + '%' : '-'}</span>
                    </div>
                    <div class="sd-financial-item ${!isPremium ? 'blur-item blurred' : ''}">
                        <span class="sd-financial-label">영업이익률</span>
                        <span class="sd-financial-value">${summaryData.operating_margin > 0 ? summaryData.operating_margin.toFixed(2) + '%' : '-'}</span>
                    </div>
                </div>
            </div>
        `;

        financialContent.innerHTML = trendChartHtml + healthScoreHtml + financialDetailsHtml;

    } catch (error) {
        console.error('Failed to load financial tab:', error);
        financialContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">재무 정보를 불러올 수 없습니다</div></div>';
    }
}

// 재무 탭 로드 - 한국 종목 상세 재무제표 (Phase 8-3)
async function loadFinancialTabKr(code) {
    const financialContent = document.getElementById('info-financial');
    if (!financialContent) return;

    financialContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>재무 정보를 불러오는 중...</span></div>';

    // 현재 기간 타입 (연간/분기)
    let periodType = 'annual';

    try {
        const loadData = async (period) => {
            const response = await invokeWithTimeout('get_stock_statement_kr', {
                accessToken: auth.accessToken || '',
                code: code,
                periodType: period
            }, 10000);
            return response?.data || null;
        };

        const renderTable = (data) => {
            if (!data || !data.periods || data.periods.length === 0) {
                return '<div class="sd-empty-state">재무제표 데이터가 없습니다</div>';
            }

            const periods = data.periods;
            const rows = data.rows || [];

            let tableHtml = `
                <table class="sd-statement-table">
                    <thead>
                        <tr>
                            <th>항목</th>
                            ${periods.map(p => `<th>${p}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => {
                            const unit = row.unit || '';
                            return `
                                <tr>
                                    <td class="row-label">${row.label}</td>
                                    ${row.values.map(v => {
                                        if (unit === '%') {
                                            return `<td class="${v > 0 ? 'positive' : v < 0 ? 'negative' : ''}">${v !== 0 ? v.toFixed(1) + '%' : '-'}</td>`;
                                        } else {
                                            return `<td class="${v > 0 ? '' : v < 0 ? 'negative' : ''}">${v !== 0 ? v.toLocaleString() : '-'}</td>`;
                                        }
                                    }).join('')}
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
            return tableHtml;
        };

        const updateContent = async () => {
            const data = await loadData(periodType);
            const tableHtml = renderTable(data);

            financialContent.innerHTML = `
                <div class="sd-card">
                    <div class="sd-card-header">
                        <div class="sd-card-title">손익계산서</div>
                        <div class="sd-period-toggle">
                            <button class="sd-period-btn ${periodType === 'annual' ? 'active' : ''}" data-period="annual">연간</button>
                            <button class="sd-period-btn ${periodType === 'quarter' ? 'active' : ''}" data-period="quarter">분기</button>
                        </div>
                    </div>
                    <div class="sd-statement-wrapper">
                        ${tableHtml}
                    </div>
                </div>
            `;

            // 기간 토글 이벤트 바인딩
            financialContent.querySelectorAll('.sd-period-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const newPeriod = e.target.dataset.period;
                    if (newPeriod !== periodType) {
                        periodType = newPeriod;
                        financialContent.innerHTML = '<div class="sd-loading"><div class="sd-loading-spinner"></div><span>재무 정보를 불러오는 중...</span></div>';
                        await updateContent();
                    }
                });
            });
        };

        await updateContent();

    } catch (error) {
        console.error('Failed to load financial tab (KR):', error);
        financialContent.innerHTML = '<div class="sd-card"><div class="sd-empty-state">재무 정보를 불러올 수 없습니다</div></div>';
    }
}

// 탭 활성화
function activateStockTab(tabName) {
    // 탭 버튼 활성화
    document.querySelectorAll('.info-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // 탭 콘텐츠 표시
    document.querySelectorAll('.info-content').forEach(content => {
        content.style.display = 'none';
    });
    const activeContent = document.getElementById(`info-${tabName}`);
    if (activeContent) activeContent.style.display = 'block';

    // 탭별 데이터 로드
    if (currentStockData && currentStockData.symbol) {
        const code = currentStockData.symbol;
        const exchange = currentStockData.exchange || '';
        const isEtf = exchange.toLowerCase() === 'etf' || currentStockData.isEtf;
        const isKorean = !isEtf && (exchange.toLowerCase() === 'kis_kr' ||
                         exchange.toLowerCase() === 'kospi' ||
                         exchange.toLowerCase() === 'kosdaq');
        const isUs = exchange.toLowerCase() === 'kis_us' ||
                     exchange.toLowerCase() === 'us' ||
                     exchange.toLowerCase() === 'nasdaq' ||
                     exchange.toLowerCase() === 'nyse';

        switch (tabName) {
            case 'news':
                if (isKorean) {
                    loadStockNewsKr(code);
                } else if (isUs) {
                    loadStockNewsUs(code);
                } else {
                    loadStockNews(code);
                }
                break;
            case 'company':
                if (isKorean) {
                    loadCompanyInfoKr(code);
                } else if (isUs) {
                    loadCompanyInfoUs(code);
                } else {
                    loadCompanyInfo(code);
                }
                break;
            case 'financial':
                if (isKorean) {
                    loadFinancialTabKr(code);
                } else if (isUs) {
                    loadFinancialTabUs(code);
                } else {
                    loadFinancialTab(code);
                }
                break;
            // ETF 전용 탭
            case 'returns':
                if (isEtf) {
                    loadEtfReturnsTab(code);
                }
                break;
            case 'dividend':
                if (isEtf) {
                    loadEtfDividendTab(code);
                }
                break;
        }
    }
}

// 뉴스 날짜 포맷
function formatNewsDate(dateStr) {
    if (!dateStr) return '';
    // 202602071900 → 2026.02.07
    if (dateStr.length === 12) {
        return `${dateStr.slice(0, 4)}.${dateStr.slice(4, 6)}.${dateStr.slice(6, 8)}`;
    }
    // ISO 형식 → YYYY.MM.DD
    if (dateStr.includes('T')) {
        return dateStr.split('T')[0].replace(/-/g, '.');
    }
    return dateStr;
}

// 한국식 숫자 포맷
function formatKoreanNum(val) {
    if (!val || val === 0) return '-';
    if (val >= 1e12) return `${(val / 1e12).toFixed(1)}조`;
    if (val >= 1e8) return `${(val / 1e8).toFixed(0)}억`;
    if (val >= 1e4) return `${(val / 1e4).toFixed(0)}만`;
    return val.toLocaleString();
}

/**
 * [BUG FIX 2] 종목 상세 UI 업데이트 - 안전한 데이터 접근
 */
function updateStockDetailUI(detail) {
    // 안전한 값 추출 함수
    const safeString = (val) => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'object') return JSON.stringify(val) === '{}' ? '-' : String(val);
        return String(val);
    };

    const safeNumber = (val) => {
        if (val === null || val === undefined || val === '') return 0;
        const num = parseFloat(val);
        return isNaN(num) ? 0 : num;
    };

    const formatPrice = (val) => {
        const num = safeNumber(val);
        if (num === 0) return '-';
        return num.toLocaleString();
    };

    // 기본 정보
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const marketEl = document.getElementById('detail-stock-market');

    if (nameEl) nameEl.textContent = safeString(detail.name) || safeString(detail.symbol) || '-';
    if (codeEl) codeEl.textContent = safeString(detail.symbol) || safeString(detail.code) || '-';
    if (marketEl) marketEl.textContent = safeString(detail.market) || safeString(detail.exchange) || '-';

    // 가격 정보
    const priceEl = document.getElementById('detail-current-price');
    const price = safeNumber(detail.price) || safeNumber(detail.current_price);
    if (priceEl) priceEl.textContent = price > 0 ? formatPrice(price) : '-';

    // 등락률
    const changeEl = document.getElementById('detail-price-change');
    if (changeEl) {
        const change = safeNumber(detail.change);
        const changePercent = safeNumber(detail.change_percent) || safeNumber(detail.changePercent);

        if (change !== 0 || changePercent !== 0) {
            const sign = change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${change.toLocaleString()} (${sign}${changePercent.toFixed(2)}%)`;
            changeEl.className = `price-change ${change >= 0 ? 'profit' : 'loss'}`;
        } else {
            changeEl.textContent = '-';
            changeEl.className = 'price-change';
        }
    }

    // 시가/고가/저가/거래량 (stock-detail-modal 내 엘리먼트 우선 선택 - 중복 ID 대응)
    const modal = document.getElementById('stock-detail-modal');
    const openEl = modal?.querySelector('#detail-open') || document.getElementById('detail-open');
    const highEl = modal?.querySelector('#detail-high') || document.getElementById('detail-high');
    const lowEl = modal?.querySelector('#detail-low') || document.getElementById('detail-low');
    const volumeEl = modal?.querySelector('#detail-volume') || document.getElementById('detail-volume');

    if (openEl) openEl.textContent = formatPrice(detail.open);
    if (highEl) highEl.textContent = formatPrice(detail.high);
    if (lowEl) lowEl.textContent = formatPrice(detail.low);
    if (volumeEl) volumeEl.textContent = formatVolume(safeNumber(detail.volume)) || '-';

    // 종합 정보 - 안전한 DOM 접근
    const marketCapEl = document.getElementById('detail-market-cap');
    if (marketCapEl) marketCapEl.textContent = formatBillions(safeNumber(detail.market_cap)) || '-';
    safeSetText('#detail-high52', detail.high52?.toLocaleString() || '-');
    safeSetText('#detail-low52', detail.low52?.toLocaleString() || '-');
    safeSetText('#detail-rs', detail.rs || '-');
    safeSetText('#detail-sector1', detail.sector1 || detail.sector || '-');
    safeSetText('#detail-sector2', detail.sector2 || '-');

    // 밸류에이션 - 안전한 DOM 접근
    safeSetText('#detail-per', safeNumber(detail.per) > 0 ? safeNumber(detail.per).toFixed(2) : '-');
    safeSetText('#detail-per-e1', detail.per_e1 || '-');
    safeSetText('#detail-per-e2', detail.per_e2 || '-');
    safeSetText('#detail-pbr', safeNumber(detail.pbr) > 0 ? safeNumber(detail.pbr).toFixed(2) : '-');
    safeSetText('#detail-psr', detail.psr || '-');
    safeSetText('#detail-div-yield', detail.div_yield ? `${detail.div_yield}%` : '-');

    // 재무 - 안전한 DOM 접근
    safeSetText('#detail-revenue', formatBillions(detail.revenue) || '-');
    safeSetText('#detail-operating', formatBillions(detail.operating_income) || '-');
    safeSetText('#detail-net-income', formatBillions(detail.net_income) || '-');
    safeSetText('#detail-roe', detail.roe ? `${detail.roe}%` : '-');
    safeSetText('#detail-debt-ratio', detail.debt_ratio ? `${detail.debt_ratio}%` : '-');
    safeSetText('#detail-eps', detail.eps?.toLocaleString() || '-');
}

function formatVolume(volume) {
    if (!volume) return '-';
    if (volume >= 1e8) return `${(volume / 1e8).toFixed(0)}억`;
    if (volume >= 1e4) return `${(volume / 1e4).toFixed(0)}만`;
    return volume.toLocaleString();
}

// 캔들차트 초기화 (TradingView Lightweight Charts)
async function initCandleChart(symbol, exchange, period = '1D') {
    const container = document.getElementById('candle-chart');
    if (!container) return;

    // 기존 차트 제거
    container.innerHTML = '';

    // KRW 여부 판별 (국내 종목, ETF, 업비트)
    const ex = (exchange || '').toUpperCase();
    const isKrw = ex === 'KIS_KR' || ex === 'UPBIT' || ex === 'ETF' || ex === '';
    const isUsd = ex === 'KIS_US' || ex === 'US' || ex === 'NASDAQ' || ex === 'NYSE';

    try {
        // 차트 생성 (ES 모듈 import 사용)
        detailChart = createChart(container, {
            width: container.clientWidth,
            height: 350,
            layout: {
                background: { color: '#0D1525' },
                textColor: '#9CA3AF'
            },
            grid: {
                vertLines: { color: '#22304A' },
                horzLines: { color: '#22304A' }
            },
            crosshair: {
                mode: CrosshairMode.Normal
            },
            rightPriceScale: {
                borderColor: '#22304A'
            },
            timeScale: {
                borderColor: '#22304A',
                timeVisible: true,
                secondsVisible: false
            },
            localization: {
                dateFormat: 'yyyy-MM-dd',
                locale: 'ko-KR',
                timeFormatter: (time) => {
                    const date = new Date(time * 1000);
                    const y = date.getFullYear();
                    const m = String(date.getMonth() + 1).padStart(2, '0');
                    const d = String(date.getDate()).padStart(2, '0');
                    return `${y}-${m}-${d}`;
                },
                // KRW: 소수점 없음 / USD: 소수점 2자리
                priceFormatter: isKrw
                    ? (price) => price.toLocaleString('ko-KR', { maximumFractionDigits: 0 })
                    : isUsd
                        ? (price) => '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                        : (price) => price.toLocaleString()
            }
        });

        // 캔들스틱 시리즈 추가
        const candleSeries = detailChart.addCandlestickSeries({
            upColor: '#22C55E',
            downColor: '#EF4444',
            borderUpColor: '#22C55E',
            borderDownColor: '#EF4444',
            wickUpColor: '#22C55E',
            wickDownColor: '#EF4444'
        });

        // 거래량 시리즈
        const volumeSeries = detailChart.addHistogramSeries({
            color: '#3B82F6',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
            scaleMargins: { top: 0.8, bottom: 0 }
        });

        // 실제 API에서 차트 데이터 가져오기
        // 기간별 충분한 데이터 로드 (SMA 200 계산 위해 여유있게)
        // UI 표시 기간 → API 요청 기간 (더 넉넉하게)
        const periodMap = {
            '1D': '1w',   // 1일 표시 → 1주 데이터 (분봉)
            '1W': '1m',   // 1주 표시 → 1개월 데이터
            '1M': '3m',   // 1개월 표시 → 3개월 데이터
            '3M': '1y',   // 3개월 표시 → 1년 데이터
            '6M': '2y',   // 6개월 표시 → 2년 데이터
            '1Y': '3y'    // 1년 표시 → 3년 데이터 (SMA 200 확보)
        };
        const apiPeriod = periodMap[period] || '1y';

        // 종목 유형 확인
        const ex = (exchange || '').toUpperCase();
        const isEtf = ex === 'ETF';
        const isUsStock = ex === 'KIS_US' || ex === 'US' || ex === 'NASDAQ' || ex === 'NYSE';

        try {
            let chartResponse;
            if (isEtf) {
                // ETF 차트 API
                chartResponse = await invokeWithTimeout('get_etf_chart', {
                    accessToken: auth.accessToken || '',
                    code: symbol,
                    period: apiPeriod
                }, 15000);
            } else if (isUsStock) {
                // 해외 종목 차트 API
                chartResponse = await invokeWithTimeout('get_stock_chart_us', {
                    accessToken: auth.accessToken || '',
                    ticker: symbol,
                    period: apiPeriod
                }, 15000);
            } else {
                // 국내 종목 차트 API
                chartResponse = await invokeWithTimeout('get_stock_chart_kr', {
                    accessToken: auth.accessToken || '',
                    code: symbol,
                    period: apiPeriod
                }, 15000);
            }

            if (chartResponse && chartResponse.candles && chartResponse.candles.length > 0) {
                // API 데이터를 TradingView 형식으로 변환
                const candleData = chartResponse.candles.map(c => {
                    // US: "YYYY-MM-DD", KR: "YYYYMMDD"
                    const dateStr = c.date || '';
                    let y, m, d;
                    if (dateStr.includes('-')) {
                        // US format: "2025-02-18"
                        const parts = dateStr.split('-');
                        y = parseInt(parts[0], 10);
                        m = parseInt(parts[1], 10) - 1;
                        d = parseInt(parts[2], 10);
                    } else {
                        // KR format: "20250218"
                        y = parseInt(dateStr.substring(0, 4), 10);
                        m = parseInt(dateStr.substring(4, 6), 10) - 1;
                        d = parseInt(dateStr.substring(6, 8), 10);
                    }
                    const timestamp = Math.floor(new Date(y, m, d).getTime() / 1000);

                    return {
                        time: timestamp,
                        open: c.open || 0,
                        high: c.high || 0,
                        low: c.low || 0,
                        close: c.close || 0
                    };
                }).filter(c => c.time > 0).sort((a, b) => a.time - b.time);

                const volumeData = chartResponse.candles.map(c => {
                    const dateStr = c.date || '';
                    let y, m, d;
                    if (dateStr.includes('-')) {
                        const parts = dateStr.split('-');
                        y = parseInt(parts[0], 10);
                        m = parseInt(parts[1], 10) - 1;
                        d = parseInt(parts[2], 10);
                    } else {
                        y = parseInt(dateStr.substring(0, 4), 10);
                        m = parseInt(dateStr.substring(4, 6), 10) - 1;
                        d = parseInt(dateStr.substring(6, 8), 10);
                    }
                    const timestamp = Math.floor(new Date(y, m, d).getTime() / 1000);

                    return {
                        time: timestamp,
                        value: c.volume || 0,
                        color: (c.close || 0) >= (c.open || 0) ? '#22C55E44' : '#EF444444'
                    };
                }).filter(v => v.time > 0).sort((a, b) => a.time - b.time);

                candleSeries.setData(candleData);
                volumeSeries.setData(volumeData);

                // SMA 이동평균선 추가 (20, 50, 200일)
                const calculateSMA = (data, period) => {
                    const result = [];
                    for (let i = period - 1; i < data.length; i++) {
                        let sum = 0;
                        for (let j = 0; j < period; j++) {
                            sum += data[i - j].close;
                        }
                        result.push({ time: data[i].time, value: sum / period });
                    }
                    return result;
                };

                // SMA 20 (노란색)
                if (candleData.length >= 20) {
                    const sma20Series = detailChart.addLineSeries({
                        color: '#FBBF24',
                        lineWidth: 1,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    sma20Series.setData(calculateSMA(candleData, 20));
                }

                // SMA 50 (주황색)
                if (candleData.length >= 50) {
                    const sma50Series = detailChart.addLineSeries({
                        color: '#F97316',
                        lineWidth: 1,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    sma50Series.setData(calculateSMA(candleData, 50));
                }

                // SMA 200 (보라색)
                if (candleData.length >= 200) {
                    const sma200Series = detailChart.addLineSeries({
                        color: '#A855F7',
                        lineWidth: 1,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    sma200Series.setData(calculateSMA(candleData, 200));
                }

                // SMA 레전드 표시
                addSmaLegend(container, candleData.length);
            } else {
                // API 실패 시 샘플 데이터 사용
                const sampleData = generateSampleCandleData(period);
                candleSeries.setData(sampleData);
                const sampleVolume = sampleData.map(d => ({
                    time: d.time,
                    value: Math.random() * 1e6,
                    color: d.close >= d.open ? '#22C55E44' : '#EF444444'
                }));
                volumeSeries.setData(sampleVolume);
            }
        } catch (chartError) {
            console.warn('Chart API failed, using sample data:', chartError);
            // API 실패 시 샘플 데이터로 폴백
            const sampleData = generateSampleCandleData(period);
            candleSeries.setData(sampleData);
            const sampleVolume = sampleData.map(d => ({
                time: d.time,
                value: Math.random() * 1e6,
                color: d.close >= d.open ? '#22C55E44' : '#EF444444'
            }));
            volumeSeries.setData(sampleVolume);
        }

        detailChart.timeScale().fitContent();

        // 리사이즈 핸들러
        const resizeObserver = new ResizeObserver(() => {
            detailChart?.resize(container.clientWidth, 350);
        });
        resizeObserver.observe(container);

    } catch (error) {
        console.error('Chart init error:', error);
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">차트를 불러올 수 없습니다</div>';
    }
}

// SMA 레전드 추가 함수
function addSmaLegend(container, dataLength) {
    // 기존 레전드 제거
    const existingLegend = container.querySelector('.sma-legend');
    if (existingLegend) existingLegend.remove();

    // 활성화된 SMA만 표시
    const smaItems = [];
    if (dataLength >= 20) {
        smaItems.push({ name: 'SMA 20', color: '#FBBF24' });
    }
    if (dataLength >= 50) {
        smaItems.push({ name: 'SMA 50', color: '#F97316' });
    }
    if (dataLength >= 200) {
        smaItems.push({ name: 'SMA 200', color: '#A855F7' });
    }

    if (smaItems.length === 0) return;

    const legend = document.createElement('div');
    legend.className = 'sma-legend';
    legend.style.cssText = 'position:absolute;top:8px;left:8px;display:flex;gap:12px;z-index:10;font-size:11px;';

    smaItems.forEach(item => {
        const span = document.createElement('span');
        span.style.cssText = `display:flex;align-items:center;gap:4px;color:${item.color};`;
        span.innerHTML = `<span style="width:12px;height:2px;background:${item.color};"></span>${item.name}`;
        legend.appendChild(span);
    });

    container.style.position = 'relative';
    container.appendChild(legend);
}

// 샘플 캔들 데이터 생성 (실제 API 연동 전 테스트용)
function generateSampleCandleData(period) {
    const data = [];
    const now = new Date();
    let numBars = 100;
    let timeStep = 24 * 60 * 60; // 1 day in seconds

    if (period === '1D') {
        numBars = 78; // 9:00 ~ 15:30, 5분봉
        timeStep = 5 * 60;
    } else if (period === '1W') {
        numBars = 5;
        timeStep = 24 * 60 * 60;
    } else if (period === '1M') {
        numBars = 22;
        timeStep = 24 * 60 * 60;
    } else if (period === '3M') {
        numBars = 65;
        timeStep = 24 * 60 * 60;
    } else if (period === '1Y') {
        numBars = 250;
        timeStep = 24 * 60 * 60;
    }

    let basePrice = 50000 + Math.random() * 50000;
    let startTime = Math.floor(now.getTime() / 1000) - (numBars * timeStep);

    for (let i = 0; i < numBars; i++) {
        const time = startTime + (i * timeStep);
        const volatility = basePrice * 0.02;
        const open = basePrice + (Math.random() - 0.5) * volatility;
        const close = open + (Math.random() - 0.5) * volatility;
        const high = Math.max(open, close) + Math.random() * volatility * 0.5;
        const low = Math.min(open, close) - Math.random() * volatility * 0.5;

        data.push({
            time: time,
            open: Math.round(open),
            high: Math.round(high),
            low: Math.round(low),
            close: Math.round(close)
        });

        basePrice = close;
    }

    return data;
}

// 종목 상세 모달 닫기 (공통 함수)
function closeStockDetailModal() {
    document.getElementById('stock-detail-modal').style.display = 'none';
    if (detailChart) {
        detailChart.remove();
        detailChart = null;
    }
    // 뒤로가기 버튼 숨기기
    const backBtn = document.getElementById('stock-detail-back');
    if (backBtn) backBtn.style.display = 'none';
}

// 종목 상세 모달 닫기 (X 버튼)
document.getElementById('stock-detail-modal-close')?.addEventListener('click', () => {
    closeStockDetailModal();
    // 상태 초기화
    window._screenerState = null;
});

// 뒤로가기 버튼 이벤트 (Phase 8-3)
document.getElementById('stock-detail-back')?.addEventListener('click', () => {
    closeStockDetailModal();

    // 스크리너 상태 복원
    if (window._screenerState && window._screenerState.fromScreener) {
        const savedState = window._screenerState;

        // screenerState 복원
        screenerState.market = savedState.market || 'kr';
        screenerState.sort = savedState.sort || 'market_cap';
        screenerState.order = savedState.order || 'desc';
        screenerState.page = savedState.page || 1;
        screenerState.activeFilters = savedState.activeFilters || {};
        screenerState.hasSearched = savedState.hasSearched || false;

        // 스크롤 위치 복원
        const screenerSection = document.querySelector('.page[data-page="screener"]');
        if (screenerSection && savedState.scrollTop) {
            setTimeout(() => {
                screenerSection.scrollTop = savedState.scrollTop;
            }, 100);
        }

        // 상태 초기화
        window._screenerState = null;
    }
});

// 모달 외부 클릭 닫기
document.getElementById('stock-detail-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'stock-detail-modal') {
        closeStockDetailModal();
        window._screenerState = null;
    }
});

// 차트 기간 탭 이벤트
document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const period = btn.dataset.period;
        if (currentStockData) {
            initCandleChart(currentStockData.symbol, currentStockData.exchange, period);
        }
    });
});

// 차트 타입 탭 이벤트
document.querySelectorAll('.type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        // 라인/캔들 전환 로직 (추후 구현)
    });
});

// 종목 정보 탭 이벤트 (4-Tab: 요약/소식/기업/재무)
document.querySelectorAll('.info-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;
        activateStockTab(tabId);
    });
});

// 관심종목 추가 버튼
document.getElementById('btn-add-to-watchlist')?.addEventListener('click', async () => {
    if (!currentStockData) return;
    try {
        await invoke('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupId: 'default',
            symbol: currentStockData.symbol,
            exchange: currentStockData.exchange
        });
        showToast('관심종목에 추가되었습니다', 'success');
    } catch (error) {
        showToast('추가 실패: ' + error, 'error');
    }
});

// AI 분석 버튼
document.getElementById('btn-ai-analysis')?.addEventListener('click', () => {
    if (!currentStockData) return;
    document.getElementById('stock-detail-modal').style.display = 'none';
    // AI 분석 모달 열기 (기존 로직 활용)
    requestAiAnalysis(currentStockData.symbol);
});

// window에 openStockDetail 노출 (테이블 클릭에서 사용)
window.openStockDetail = openStockDetail;

// =====================================================
// MR Premium Engine (Phase 4)
// =====================================================
let mrSymbolAutocomplete = null;

async function loadMrEngineTab() {
    // MR 리디자인 UI 초기화
    initMrUiComponents();
    loadMrExchangeDropdown();
    initMrSymbolAutocomplete();
}

async function loadMrSchedulerStatus() {
    try {
        const status = await invoke('get_scheduler_status', {
            accessToken: auth.accessToken || ''
        });

        const stateEl = document.getElementById('mr-scheduler-state');
        const countEl = document.getElementById('mr-asset-count');
        const tfsEl = document.getElementById('mr-active-tfs');

        if (stateEl) {
            stateEl.textContent = status.state?.toUpperCase() || 'STOPPED';
            stateEl.className = 'scheduler-state state-' + (status.state || 'stopped');
        }
        if (countEl) countEl.textContent = status.asset_count || 0;
        if (tfsEl) tfsEl.textContent = status.active_timeframes?.join(', ') || '-';
    } catch (error) {
        console.error('스케줄러 상태 로드 실패:', error);
    }
}

async function loadMrConfigs() {
    const tbody = document.getElementById('mr-configs-tbody');
    if (!tbody) return;

    try {
        const configs = await invoke('get_premium_configs', {
            accessToken: auth.accessToken || ''
        });

        if (!configs || configs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">등록된 종목이 없습니다</td></tr>';
            return;
        }

        tbody.innerHTML = configs.map(config => {
            const stateInfo = config.state || {};
            return `
                <tr data-asset-id="${config.asset_id}">
                    <td>${config.symbol || 'Asset #' + config.asset_id}</td>
                    <td>${config.signal_tf}</td>
                    <td>${config.osc_preset}</td>
                    <td>${stateInfo.buy_stage || 0}/${(config.buy_tranches?.length || 4)}</td>
                    <td>${stateInfo.sell_stage || 0}/${(config.sell_tranches?.length || 2)}</td>
                    <td><span class="status-badge ${config.enabled ? 'active' : 'inactive'}">${config.enabled ? '활성' : '비활성'}</span></td>
                    <td>
                        <button class="btn btn-sm btn-icon" onclick="triggerMrSignal(${config.asset_id})" title="수동 시그널">▶</button>
                        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteMrConfig(${config.asset_id})" title="삭제">✕</button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('MR 설정 로드 실패:', error);
        tbody.innerHTML = '<tr><td colspan="7" class="error-state">로드 실패: ' + error + '</td></tr>';
    }
}

async function loadMrSignals() {
    const list = document.getElementById('mr-signals-list');
    if (!list) return;

    try {
        const events = await invoke('get_signal_events', {
            accessToken: auth.accessToken || '',
            limit: 10
        });

        if (!events || events.length === 0) {
            list.innerHTML = '<p class="empty-state">시그널 기록이 없습니다</p>';
            return;
        }

        list.innerHTML = events.map(event => {
            const actionClass = event.action === 'buy' ? 'signal-buy' : 'signal-sell';
            const actionText = event.action === 'buy' ? '매수' : '매도';
            const time = new Date(event.timestamp).toLocaleString('ko-KR');
            return `
                <div class="signal-item ${actionClass}">
                    <span class="signal-action">${actionText}</span>
                    <span class="signal-asset">${event.symbol || 'Asset #' + event.asset_id}</span>
                    <span class="signal-reason">${event.reason_code || '-'}</span>
                    <span class="signal-time">${time}</span>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('시그널 로드 실패:', error);
    }
}

function initMrSymbolAutocomplete() {
    const input = document.getElementById('mr-symbol');
    const exchangeSelect = document.getElementById('mr-exchange');
    if (!input || mrSymbolAutocomplete) return;

    const initialExchange = exchangeSelect?.value || 'all';
    mrSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        }
    }, { exchange: initialExchange, showBadge: true });

    // 거래소 변경 시 자동완성 필터 업데이트
    exchangeSelect?.addEventListener('change', () => {
        if (mrSymbolAutocomplete) {
            mrSymbolAutocomplete.setExchange(exchangeSelect.value);
        }
    });
}

async function loadMrExchangeDropdown() {
    const select = document.getElementById('mr-exchange');
    if (!select) return;

    // 기본 거래소 목록 (v4 명령서 순서: KIS_KR → KIS_US → UPBIT → Binance → BYBIT → OKX)
    // ETF는 KIS_KR/KIS_US에 통합되므로 별도 옵션 없음
    const defaultExchanges = ['KIS_KR', 'KIS_US', 'UPBIT', 'BINANCE', 'BYBIT', 'OKX'];

    try {
        let accounts = [];
        try {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken || '' });
        } catch { }

        if (!accounts || accounts.length === 0) {
            try {
                accounts = await invoke('list_local_accounts');
            } catch { }
        }

        // 등록된 계정의 거래소 추출
        const registeredExchanges = new Set();
        (accounts || []).forEach(acc => {
            const exName = acc.exchange?.toUpperCase() || acc.exchange_name?.toUpperCase();
            if (exName) registeredExchanges.add(exName);
        });

        // 기본 + 등록된 거래소 합치기 (중복 제거)
        const allExchanges = [...new Set([...defaultExchanges, ...registeredExchanges])];

        select.innerHTML = '<option value="">선택하세요</option>';
        allExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    } catch (error) {
        console.error('거래소 드롭다운 로드 실패:', error);
        // 에러 시에도 기본 거래소 표시
        select.innerHTML = '<option value="">선택하세요</option>';
        defaultExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    }

    // KIS 거래소 선택 시 타임프레임 제한 + 설정 모달
    select.addEventListener('change', () => {
        updateMrTimeframeOptions(select.value);
        handleExchangeChange({ target: select });
    });
}

/**
 * 거래소에 따라 타임프레임 옵션 활성화/비활성화
 * KIS는 일봉/주봉/월봉만 지원
 */
function updateMrTimeframeOptions(exchange) {
    const signalTfSelect = document.getElementById('mr-signal-tf');
    const htfSelect = document.getElementById('mr-htf');

    const isKIS = exchange === 'KIS_KR' || exchange === 'KIS_US';
    const kisAllowedTfs = ['1D', '1W', '1M'];

    // 시그널 TF 옵션 처리
    if (signalTfSelect) {
        Array.from(signalTfSelect.options).forEach(opt => {
            if (isKIS) {
                opt.disabled = !kisAllowedTfs.includes(opt.value);
            } else {
                opt.disabled = false;
            }
        });

        // KIS인데 현재 선택이 분봉이면 일봉으로 변경
        if (isKIS && !kisAllowedTfs.includes(signalTfSelect.value)) {
            signalTfSelect.value = '1D';
        }
    }

    // HTF 옵션 처리
    if (htfSelect) {
        Array.from(htfSelect.options).forEach(opt => {
            if (isKIS) {
                opt.disabled = !kisAllowedTfs.includes(opt.value);
            } else {
                opt.disabled = false;
            }
        });

        // KIS인데 현재 선택이 분봉이면 일봉으로 변경
        if (isKIS && !kisAllowedTfs.includes(htfSelect.value)) {
            htfSelect.value = '1D';
        }
    }

    // KIS 선택 시 안내 메시지 (거래소 헬프 텍스트 변경)
    const exchangeHelpEl = document.querySelector('#mr-section-target .mr-help');
    if (exchangeHelpEl) {
        if (isKIS) {
            exchangeHelpEl.textContent = '한국투자증권: 일봉/주봉만 지원 (분봉 불가)';
            exchangeHelpEl.style.color = '#f59e0b';
        } else {
            exchangeHelpEl.textContent = '백테스트할 거래소를 선택하세요';
            exchangeHelpEl.style.color = '';
        }
    }
}

// =====================================================
// MR UI 리디자인 - 아코디언/탭/트랜치 동적생성
// =====================================================

const DEFAULT_BUY_TRANCHES = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5];
const DEFAULT_SELL_TRANCHES = [10, 20, 30, 5, 2.5, 1];

// 아코디언 초기화
function initMrAccordions() {
    document.querySelectorAll('.mr-accordion-header').forEach(header => {
        header.addEventListener('click', () => {
            const accordion = header.closest('.mr-accordion');
            const body = accordion.querySelector('.mr-accordion-body');
            const icon = header.querySelector('.mr-accordion-icon');

            if (body.style.display === 'none') {
                body.style.display = 'block';
                icon.textContent = '▼';
                accordion.classList.add('open');
            } else {
                body.style.display = 'none';
                icon.textContent = '▶';
                accordion.classList.remove('open');
            }
        });
    });
}

// 국면 탭 초기화
function initMrRegimeTabs() {
    document.querySelectorAll('.mr-regime-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            // 탭 활성화
            document.querySelectorAll('.mr-regime-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // 콘텐츠 전환
            const regime = tab.dataset.regime;
            document.querySelectorAll('.mr-regime-content').forEach(c => {
                c.style.display = 'none';
                c.classList.remove('active');
            });
            const targetContent = document.getElementById(`mr-regime-${regime}`);
            if (targetContent) {
                targetContent.style.display = 'block';
                targetContent.classList.add('active');
            }
        });
    });
}

// 매수 트랜치 동적 렌더링
function renderBuyTranches(count) {
    const container = document.getElementById('mr-buy-tranches-container');
    if (!container) return;

    container.innerHTML = '';
    for (let i = 0; i < count; i++) {
        const defaultVal = DEFAULT_BUY_TRANCHES[i] || DEFAULT_BUY_TRANCHES[DEFAULT_BUY_TRANCHES.length - 1];
        container.innerHTML += `
            <div class="mr-tranche-item">
                <label>BUY${i + 1}</label>
                <input type="number" class="mr-buy-tranche-input" value="${defaultVal}"
                       min="0" max="100" step="0.5" data-index="${i}"> %
            </div>
        `;
    }
    updateBuyTotal();
    // 각 입력에 change 이벤트
    container.querySelectorAll('.mr-buy-tranche-input').forEach(input => {
        input.addEventListener('input', updateBuyTotal);
    });
}

// 매도 트랜치 동적 렌더링
function renderSellTranches(count) {
    const container = document.getElementById('mr-sell-tranches-container');
    if (!container) return;

    container.innerHTML = '';
    for (let i = 0; i < count; i++) {
        const defaultVal = DEFAULT_SELL_TRANCHES[i] || DEFAULT_SELL_TRANCHES[DEFAULT_SELL_TRANCHES.length - 1];
        container.innerHTML += `
            <div class="mr-tranche-item">
                <label>SELL${i + 1}</label>
                <input type="number" class="mr-sell-tranche-input" value="${defaultVal}"
                       min="0" max="100" step="0.5" data-index="${i}"> %
            </div>
        `;
    }
    updateSellTotal();
    container.querySelectorAll('.mr-sell-tranche-input').forEach(input => {
        input.addEventListener('input', updateSellTotal);
    });
}

function updateBuyTotal() {
    const inputs = document.querySelectorAll('.mr-buy-tranche-input');
    let total = 0;
    inputs.forEach(input => total += parseFloat(input.value) || 0);
    const el = document.getElementById('mr-buy-total-pct');
    if (el) el.textContent = total.toFixed(1);
}

function updateSellTotal() {
    const inputs = document.querySelectorAll('.mr-sell-tranche-input');
    let total = 0;
    inputs.forEach(input => total += parseFloat(input.value) || 0);
    const el = document.getElementById('mr-sell-total-pct');
    if (el) el.textContent = total.toFixed(1);
}

// 트랜치 차수 변경 이벤트
function initMrTrancheHandlers() {
    const buyCountEl = document.getElementById('mr-buy-tranche-count');
    const sellCountEl = document.getElementById('mr-sell-tranche-count');

    if (buyCountEl) {
        buyCountEl.addEventListener('change', (e) => {
            renderBuyTranches(parseInt(e.target.value) || 10);
        });
    }
    if (sellCountEl) {
        sellCountEl.addEventListener('change', (e) => {
            renderSellTranches(parseInt(e.target.value) || 6);
        });
    }

    // 초기 렌더링
    renderBuyTranches(10);
    renderSellTranches(6);
}

// MR 설정 수집 함수
function collectMrConfig() {
    // 매수 트랜치 비중 수집
    const buyTranches = [];
    document.querySelectorAll('.mr-buy-tranche-input').forEach(input => {
        buyTranches.push(parseFloat(input.value) || 0);
    });

    // 매도 트랜치 비중 수집
    const sellTranches = [];
    document.querySelectorAll('.mr-sell-tranche-input').forEach(input => {
        sellTranches.push(parseFloat(input.value) || 0);
    });

    // 종목 심볼: 자동완성에서 선택 시 dataset.selectedCode (BTC-USDT), 없으면 입력값
    const symbolInput = document.getElementById('mr-symbol');
    const symbolValue = symbolInput?.dataset?.selectedCode || symbolInput?.value || '';

    return {
        // ① 거래소 + 종목
        exchange: document.getElementById('mr-exchange')?.value || '',
        symbol: symbolValue,

        // ② 가용자금
        cash_use_pct: parseFloat(document.getElementById('mr-cash-use-pct')?.value) || 55,
        hard_cap_pct: parseFloat(document.getElementById('mr-hard-cap-pct')?.value) || 100,

        // ③ 기본 설정
        signal_tf: document.getElementById('mr-signal-tf')?.value || '30m',
        htf_tf: document.getElementById('mr-htf')?.value || '1D',
        osc_smooth_len: parseInt(document.getElementById('mr-osc-smooth')?.value) || 20,
        osc_threshold: parseFloat(document.getElementById('mr-osc-threshold')?.value) || 1.0,
        min_profit_pct: parseFloat(document.getElementById('mr-min-profit-pct')?.value) || 0.1,
        fee_buffer_pct: parseFloat(document.getElementById('mr-fee-buffer-pct')?.value) || 0.2,
        st_reversal_fix: document.getElementById('mr-st-reversal-fix')?.checked ?? true,
        one_trade_per_bar: document.getElementById('mr-one-trade-per-bar')?.checked ?? true,

        // ④ 트랜치
        buy_tranches: buyTranches,
        max_buy_tranches: buyTranches.length,
        after_max_buy: document.querySelector('input[name="mr-after-max-buy"]:checked')?.value || 'extend',
        sell_tranches: sellTranches,
        max_sell_tranches: sellTranches.length,
        after_max_sell: document.querySelector('input[name="mr-after-max-sell"]:checked')?.value || 'cycle',

        // ⑤ 국면별 설정
        use_4regime: document.getElementById('mr-use-4regime')?.checked ?? true,

        // R1
        r1_buy_mult: parseFloat(document.getElementById('mr-r1-buy-mult')?.value) || 1.0,
        r1_sell_mult: parseFloat(document.getElementById('mr-r1-sell-mult')?.value) || 1.3,
        r1_allow_osc_buy: document.getElementById('mr-r1-allow-osc-buy')?.checked ?? true,
        r1_buy1_only: document.getElementById('mr-r1-buy1-only')?.checked ?? false,
        r1_sell1_only: document.getElementById('mr-r1-sell1-only')?.checked ?? false,
        r1_sell_mode: document.querySelector('input[name="mr-r1-sell-mode"]:checked')?.value || 'Normal',
        r1_filt_below_avg: document.getElementById('mr-r1-filt-below-avg')?.checked ?? true,
        r1_filt_prev_signal: document.getElementById('mr-r1-filt-prev-signal')?.checked ?? true,
        r1_filt_prev_exec: document.getElementById('mr-r1-filt-prev-exec')?.checked ?? true,
        r1_pullback_on: document.getElementById('mr-r1-pullback-on')?.checked ?? true,
        r1_pullback_buy_mult: parseFloat(document.getElementById('mr-r1-pullback-mult')?.value) || 1.0,

        // R2
        r2_buy_mult: parseFloat(document.getElementById('mr-r2-buy-mult')?.value) || 0.0,
        r2_sell_mult: parseFloat(document.getElementById('mr-r2-sell-mult')?.value) || 1.6,
        r2_allow_osc_buy: document.getElementById('mr-r2-allow-osc-buy')?.checked ?? false,
        r2_buy1_only: document.getElementById('mr-r2-buy1-only')?.checked ?? false,
        r2_sell1_only: document.getElementById('mr-r2-sell1-only')?.checked ?? false,
        r2_sell_mode: document.querySelector('input[name="mr-r2-sell-mode"]:checked')?.value || 'Alternate',
        r2_filt_below_avg: document.getElementById('mr-r2-filt-below-avg')?.checked ?? false,
        r2_filt_prev_signal: document.getElementById('mr-r2-filt-prev-signal')?.checked ?? false,
        r2_filt_prev_exec: document.getElementById('mr-r2-filt-prev-exec')?.checked ?? false,

        // R3
        r3_buy_mult: parseFloat(document.getElementById('mr-r3-buy-mult')?.value) || 1.0,
        r3_sell_mult: parseFloat(document.getElementById('mr-r3-sell-mult')?.value) || 1.3,
        r3_allow_osc_buy: document.getElementById('mr-r3-allow-osc-buy')?.checked ?? true,
        r3_buy1_only: document.getElementById('mr-r3-buy1-only')?.checked ?? true,
        r3_sell1_only: document.getElementById('mr-r3-sell1-only')?.checked ?? false,
        r3_sell_mode: document.querySelector('input[name="mr-r3-sell-mode"]:checked')?.value || 'Normal',
        r3_filt_below_avg: document.getElementById('mr-r3-filt-below-avg')?.checked ?? false,
        r3_filt_prev_signal: document.getElementById('mr-r3-filt-prev-signal')?.checked ?? true,
        r3_filt_prev_exec: document.getElementById('mr-r3-filt-prev-exec')?.checked ?? true,
        r3_breakout_on: document.getElementById('mr-r3-breakout-on')?.checked ?? true,
        r3_breakout_buy_mult: parseFloat(document.getElementById('mr-r3-breakout-mult')?.value) || 1.0,

        // R4
        r4_buy_mult: parseFloat(document.getElementById('mr-r4-buy-mult')?.value) || 1.2,
        r4_sell_mult: parseFloat(document.getElementById('mr-r4-sell-mult')?.value) || 0.7,
        r4_allow_osc_buy: document.getElementById('mr-r4-allow-osc-buy')?.checked ?? true,
        r4_buy1_only: document.getElementById('mr-r4-buy1-only')?.checked ?? false,
        r4_sell1_only: document.getElementById('mr-r4-sell1-only')?.checked ?? false,
        r4_sell_mode: document.querySelector('input[name="mr-r4-sell-mode"]:checked')?.value || 'Normal',
        r4_filt_below_avg: document.getElementById('mr-r4-filt-below-avg')?.checked ?? true,
        r4_filt_prev_signal: document.getElementById('mr-r4-filt-prev-signal')?.checked ?? true,
        r4_filt_prev_exec: document.getElementById('mr-r4-filt-prev-exec')?.checked ?? false,
    };
}

// MR UI 초기화 (탭 로드 시 호출)
function initMrUiComponents() {
    initMrAccordions();
    initMrRegimeTabs();
    initMrTrancheHandlers();
    initTrendDynamicUI();
}

// ============================================================
// Trend 피라미딩/분할매도 동적 UI (v8 UI 전면 재설계)
// ============================================================

// 피라미딩 기본 비중 (차수별)
const TREND_PYR_DEFAULTS = {
    1: [100],
    2: [60, 40],
    3: [50, 30, 20],
    4: [40, 30, 20, 10],
    5: [30, 25, 20, 15, 10],
    6: [25, 20, 18, 15, 12, 10],
    7: [22, 18, 16, 14, 12, 10, 8],
    8: [20, 16, 14, 13, 12, 10, 8, 7],
    9: [18, 15, 13, 12, 11, 10, 8, 7, 6],
    10: [16, 14, 12, 11, 10, 9, 8, 7, 7, 6],
};

// 분할매도 기본 비중 (차수별)
const TREND_SELL_DEFAULTS = {
    1: [100],
    2: [30, 70],
    3: [15, 25, 60],
    4: [10, 15, 25, 50],
    5: [5, 10, 15, 25, 45],
    6: [5, 5, 10, 15, 25, 40],
};

/**
 * 추세매매 설정 수집 함수 (UI 전면 재설계 버전)
 */
function collectTrendConfig() {
    const symbolInput = document.getElementById('trend-symbol');
    const symbolValue = symbolInput?.dataset?.selectedCode || symbolInput?.value || '';

    // 피라미딩 비중 수집
    const pyrWeights = [];
    document.querySelectorAll('.trend-pyr-weight-input').forEach(input => {
        pyrWeights.push(parseFloat(input.value) || 0);
    });

    // 분할매도 비중 수집
    const sellTranches = [];
    document.querySelectorAll('.trend-sell-tranche-input').forEach(input => {
        sellTranches.push(parseFloat(input.value) || 0);
    });

    return {
        // 기본 설정
        exchange: document.getElementById('trend-exchange')?.value || '',
        symbol: symbolValue,
        signal_tf: document.getElementById('trend-signal-tf')?.value || '1D',
        exit_tf: document.getElementById('trend-exit-tf')?.value || '1W',
        htf_tf: document.getElementById('trend-htf-tf')?.value || '1W',
        cash_use_pct: parseFloat(document.getElementById('trend-cash-use-pct')?.value) || 100,

        // 슈퍼트렌드
        st_atr_len: parseInt(document.getElementById('trend-st-atr-len')?.value) || 20,
        st_factor: parseFloat(document.getElementById('trend-st-factor')?.value) || 5.0,

        // 피라미딩
        use_pyramiding: document.getElementById('trend-use-pyramiding')?.checked ?? true,
        max_pyr_entries: parseInt(document.getElementById('trend-max-pyr')?.value) || 4,
        pyr_high_len: parseInt(document.getElementById('trend-pyr-high-len')?.value) || 60,
        pyr_cooldown: parseInt(document.getElementById('trend-pyr-cooldown')?.value) || 5,
        pyr_refill_after_sell: document.getElementById('trend-pyr-refill')?.checked ?? false,
        pyr_weights: pyrWeights.length > 0 ? pyrWeights : [40, 30, 20, 10],

        // 추세전환 전량매도
        use_st_exit: document.getElementById('trend-use-st-exit')?.checked ?? true,

        // 부분익절
        use_tp1: document.getElementById('trend-use-tp1')?.checked ?? false,
        tp1_pct: parseFloat(document.getElementById('trend-tp1-pct')?.value) || 21,
        tp1_sell_pct: parseFloat(document.getElementById('trend-tp1-sell-pct')?.value) || 50,

        // 과매수구간 분할매도
        use_spo_split: document.getElementById('trend-use-spo')?.checked ?? true,
        sell_tranches: sellTranches.length > 0 ? sellTranches : [5, 5, 10, 15, 25, 40],
        max_sell_tranches: parseInt(document.getElementById('trend-max-sell-tranches')?.value) || 6,
        after_max_sell: document.getElementById('trend-after-max-sell')?.value || 'cycle',
        use_profit_gate: document.getElementById('trend-use-profit-gate')?.checked ?? true,

        // 손절 (택 1)
        stop_type: document.getElementById('trend-stop-type')?.value || 'fixed',
        hard_sl_pct: parseFloat(document.getElementById('trend-hard-sl-pct')?.value) || 7,
        atr_stop_len: parseInt(document.getElementById('trend-atr-stop-len')?.value) || 14,
        atr_stop_mult: parseFloat(document.getElementById('trend-atr-stop-mult')?.value) || 2.0,

        // 백테스트
        days: parseInt(document.getElementById('trend-bt-days')?.value) || 365,
        initial_capital: parseFloat(document.getElementById('trend-bt-capital')?.value) || 10000000,
    };
}

/**
 * 피라미딩 비중 동적 렌더링
 */
function renderTrendPyrWeights(count) {
    const container = document.getElementById('trend-pyr-weights-row');
    if (!container) return;

    container.innerHTML = '';
    const weights = TREND_PYR_DEFAULTS[count] || TREND_PYR_DEFAULTS[4];

    for (let i = 0; i < count; i++) {
        const field = document.createElement('div');
        field.className = 'mr-field';
        field.style.flex = '1';
        field.innerHTML = `
            <label>${i + 1}차 (%)</label>
            <input type="number" class="form-input trend-pyr-weight-input"
                   value="${weights[i]}" min="0" max="100" step="1">
        `;
        container.appendChild(field);
    }

    // 합계 실시간 체크
    container.querySelectorAll('.trend-pyr-weight-input').forEach(input => {
        input.addEventListener('input', updateTrendPyrWeightSum);
    });
    updateTrendPyrWeightSum();
}

/**
 * 피라미딩 비중 합계 업데이트
 */
function updateTrendPyrWeightSum() {
    let sum = 0;
    document.querySelectorAll('.trend-pyr-weight-input').forEach(input => {
        sum += parseFloat(input.value) || 0;
    });
    const el = document.getElementById('trend-pyr-weights-sum');
    if (el) {
        el.textContent = `합계: ${sum}%`;
        el.style.color = Math.abs(sum - 100) < 0.01 ? '#9CA3AF' : '#EF4444';
    }
}

/**
 * 분할매도 비중 동적 렌더링
 */
function renderTrendSellTranches(count) {
    const container = document.getElementById('trend-sell-tranches-row');
    if (!container) return;

    container.innerHTML = '';
    const tranches = TREND_SELL_DEFAULTS[count] || TREND_SELL_DEFAULTS[6];

    for (let i = 0; i < count; i++) {
        const field = document.createElement('div');
        field.className = 'mr-field';
        field.style.flex = '1';
        field.innerHTML = `
            <label>${i + 1}차 (%)</label>
            <input type="number" class="form-input trend-sell-tranche-input"
                   value="${tranches[i]}" min="0" max="100" step="0.1">
        `;
        container.appendChild(field);
    }
}

/**
 * Trend 동적 UI 핸들러 초기화
 */
let _trendDynamicUIInitialized = false;
function initTrendDynamicUI() {
    // 초기 렌더링 (항상 실행 - 탭 전환 시 재렌더링 필요)
    const maxPyr = parseInt(document.getElementById('trend-max-pyr')?.value) || 4;
    const maxSell = parseInt(document.getElementById('trend-max-sell-tranches')?.value) || 6;
    renderTrendPyrWeights(maxPyr);
    renderTrendSellTranches(maxSell);

    // 이벤트 리스너는 한 번만 등록
    if (_trendDynamicUIInitialized) return;
    _trendDynamicUIInitialized = true;

    // 피라미딩 최대 횟수 변경 → 비중칸 동적 생성
    document.getElementById('trend-max-pyr')?.addEventListener('change', (e) => {
        renderTrendPyrWeights(parseInt(e.target.value) || 4);
    });

    // 분할매도 최대 횟수 변경 → 비중칸 동적 생성
    document.getElementById('trend-max-sell-tranches')?.addEventListener('change', (e) => {
        renderTrendSellTranches(parseInt(e.target.value) || 6);
    });

    // 피라미딩 사용 체크박스 → 설정 표시/숨김
    document.getElementById('trend-use-pyramiding')?.addEventListener('change', (e) => {
        const settings = document.getElementById('trend-pyramiding-settings');
        if (settings) settings.style.display = e.target.checked ? 'block' : 'none';
    });

    // TP1 사용 체크박스 → 설정 표시/숨김
    document.getElementById('trend-use-tp1')?.addEventListener('change', (e) => {
        const settings = document.getElementById('trend-tp1-settings');
        if (settings) settings.style.display = e.target.checked ? 'block' : 'none';
    });

    // 분할매도 사용 체크박스 → 설정 표시/숨김
    document.getElementById('trend-use-spo')?.addEventListener('change', (e) => {
        const settings = document.getElementById('trend-spo-settings');
        if (settings) settings.style.display = e.target.checked ? 'block' : 'none';
    });

    // 손절 방식 드롭다운 → Fixed/ATR UI 전환
    document.getElementById('trend-stop-type')?.addEventListener('change', (e) => {
        const fixedSettings = document.getElementById('trend-sl-fixed-settings');
        const atrSettings = document.getElementById('trend-sl-atr-settings');
        if (e.target.value === 'fixed') {
            if (fixedSettings) fixedSettings.style.display = 'block';
            if (atrSettings) atrSettings.style.display = 'none';
        } else {
            if (fixedSettings) fixedSettings.style.display = 'none';
            if (atrSettings) atrSettings.style.display = 'block';
        }
    });

    // 아코디언 토글 (매수/매도/백테스트)
    document.querySelectorAll('#strategy-tab-trend .mr-accordion-header').forEach(header => {
        header.addEventListener('click', () => {
            const section = header.closest('.mr-accordion');
            if (!section) return;
            const body = section.querySelector('.mr-accordion-body');
            const icon = header.querySelector('.mr-accordion-icon');
            if (section.classList.contains('open')) {
                section.classList.remove('open');
                if (body) body.style.display = 'none';
                if (icon) icon.textContent = '▶';
            } else {
                section.classList.add('open');
                if (body) body.style.display = 'block';
                if (icon) icon.textContent = '▼';
            }
        });
    });
}

// MR 스케줄러 시작
document.getElementById('btn-mr-start')?.addEventListener('click', async () => {
    try {
        await invoke('start_scheduler', { accessToken: auth.accessToken || '' });
        showToast('스케줄러가 시작되었습니다', 'success');
        await loadMrSchedulerStatus();
    } catch (error) {
        showToast('스케줄러 시작 실패: ' + error, 'error');
    }
});

// MR 스케줄러 중지
document.getElementById('btn-mr-stop')?.addEventListener('click', async () => {
    try {
        await invoke('stop_scheduler_premium', { accessToken: auth.accessToken || '' });
        showToast('스케줄러가 중지되었습니다', 'info');
        await loadMrSchedulerStatus();
    } catch (error) {
        showToast('스케줄러 중지 실패: ' + error, 'error');
    }
});

// MR 새로고침
document.getElementById('btn-mr-refresh')?.addEventListener('click', async () => {
    await loadMrEngineTab();
    showToast('새로고침 완료', 'info');
});

// MR 종목 추가
// MR 설정 저장 버튼
document.getElementById('btn-mr-save')?.addEventListener('click', async () => {
    const config = collectMrConfig();

    if (!config.exchange || !config.symbol) {
        showToast('거래소와 종목을 선택해주세요', 'error');
        return;
    }

    try {
        await invoke('create_premium_config', {
            accessToken: auth.accessToken || '',
            config: config
        });

        showToast('설정이 저장되었습니다', 'success');
    } catch (error) {
        showToast('설정 저장 실패: ' + error, 'error');
    }
});

// MR 전략 시작 버튼
document.getElementById('btn-mr-start-strategy')?.addEventListener('click', async () => {
    const config = collectMrConfig();

    if (!config.exchange || !config.symbol) {
        showToast('거래소와 종목을 선택해주세요', 'error');
        return;
    }

    try {
        // 설정 저장
        const savedConfig = await invoke('create_premium_config', {
            accessToken: auth.accessToken || '',
            config: config
        });

        // 스케줄러에 등록
        await invoke('register_to_scheduler', {
            accessToken: auth.accessToken || '',
            assetId: savedConfig?.asset_id || 0,
            symbol: config.symbol,
            exchange: config.exchange,
            timeframe: config.signal_tf,
            htfTimeframe: config.htf_tf
        });

        // 스케줄러 시작
        await invoke('start_scheduler', { accessToken: auth.accessToken || '' });

        showToast('전략이 시작되었습니다', 'success');
    } catch (error) {
        showToast('전략 시작 실패: ' + error, 'error');
    }
});

// MR 빠른 백테스트 버튼
document.getElementById('btn-mr-backtest-quick')?.addEventListener('click', () => {
    // 백테스트 아코디언 열기
    const accordion = document.getElementById('mr-section-backtest');
    const body = accordion?.querySelector('.mr-accordion-body');
    const icon = accordion?.querySelector('.mr-accordion-icon');
    if (body && body.style.display === 'none') {
        body.style.display = 'block';
        if (icon) icon.textContent = '▼';
        accordion?.classList.add('open');
    }
});

// MR 백테스트 실행
let mrBacktestChart = null;

document.getElementById('btn-mr-run-backtest')?.addEventListener('click', async () => {
    console.log('[MR 백테스트] 시작');

    const config = collectMrConfig();
    const days = parseInt(document.getElementById('mr-bt-days')?.value) || 365;
    const capital = parseFloat(document.getElementById('mr-bt-capital')?.value) || 10000000;

    if (!config.exchange) config.exchange = 'OKX';
    if (!config.symbol) config.symbol = 'BTC-USDT';

    console.log('[MR 백테스트] config:', JSON.stringify(config).substring(0, 300));

    // 로딩 표시
    const btn = document.getElementById('btn-mr-run-backtest');
    const loadingEl = document.getElementById('mr-backtest-loading');
    const loadingMsgEl = document.getElementById('mr-backtest-loading-msg');
    const errorEl = document.getElementById('mr-backtest-error');
    const resultEl = document.getElementById('mr-backtest-result');

    const setLoadingMsg = (msg) => {
        if (loadingMsgEl) loadingMsgEl.textContent = msg;
    };

    if (btn) {
        btn.disabled = true;
        btn.textContent = '준비 중...';
        btn.classList.add('btn-loading');
    }
    if (loadingEl) loadingEl.style.display = 'block';
    if (errorEl) errorEl.style.display = 'none';
    if (resultEl) resultEl.style.display = 'none';

    try {
        // 1단계: 캔들 프리로드 (시세 데이터 준비)
        setLoadingMsg('시세 데이터 준비 중...');
        console.log('[MR 백테스트] 프리로드 시작');

        const preloadResult = await invoke('preload_candles', {
            accessToken: auth.accessToken || '',
            exchange: config.exchange,
            symbol: config.symbol,
            timeframe: config.signal_tf,
            days: days,
        });

        if (!preloadResult.success) {
            throw new Error(preloadResult.message || '시세 데이터 로드 실패');
        }

        console.log('[MR 백테스트] 프리로드 완료:', preloadResult.candles, '봉,', preloadResult.time_sec, '초');

        // 2단계: 백테스트 실행
        setLoadingMsg('전략 분석 중...');
        if (btn) btn.textContent = '분석 중...';
        console.log('[MR 백테스트] invoke 호출');

        const result = await invoke('run_mr_backtest', {
            accessToken: auth.accessToken || '',
            exchange: config.exchange,
            symbol: config.symbol,
            timeframe: config.signal_tf,
            htfTf: config.htf_tf,
            days: days,
            initialCapital: capital,
            // 오실레이터 설정
            oscPreset: 'custom',
            oscSmoothLen: config.osc_smooth_len,
            oscThreshold: config.osc_threshold,
            // 자금관리
            cashUsePct: config.cash_use_pct,
            minProfitPct: config.min_profit_pct,
            feeBufferPct: config.fee_buffer_pct,
            buyTranches: config.buy_tranches,
            sellTranches: config.sell_tranches,
            // R1 국면 (역배열+ST상승)
            r1BuyMult: config.r1_buy_mult,
            r1SellMult: config.r1_sell_mult,
            r1AllowOscBuy: config.r1_allow_osc_buy,
            r1PullbackOn: config.r1_pullback_on,
            r1FiltBelowAvg: config.r1_filt_below_avg,
            r1FiltPrevSignal: config.r1_filt_prev_signal,
            r1FiltPrevExec: config.r1_filt_prev_exec,
            // R2 국면 (역배열+ST하락)
            r2BuyMult: config.r2_buy_mult,
            r2SellMult: config.r2_sell_mult,
            r2AllowOscBuy: config.r2_allow_osc_buy,
            r2FiltBelowAvg: config.r2_filt_below_avg,
            r2FiltPrevSignal: config.r2_filt_prev_signal,
            r2FiltPrevExec: config.r2_filt_prev_exec,
            // R3 국면 (정배열+ST상승)
            r3BuyMult: config.r3_buy_mult,
            r3SellMult: config.r3_sell_mult,
            r3AllowOscBuy: config.r3_allow_osc_buy,
            r3BreakoutOn: config.r3_breakout_on,
            r3FiltBelowAvg: config.r3_filt_below_avg,
            r3FiltPrevSignal: config.r3_filt_prev_signal,
            r3FiltPrevExec: config.r3_filt_prev_exec,
            // R4 국면 (정배열+ST하락)
            r4BuyMult: config.r4_buy_mult,
            r4SellMult: config.r4_sell_mult,
            r4AllowOscBuy: config.r4_allow_osc_buy,
            r4FiltBelowAvg: config.r4_filt_below_avg,
            r4FiltPrevSignal: config.r4_filt_prev_signal,
            r4FiltPrevExec: config.r4_filt_prev_exec,
        });

        console.log('[MR 백테스트] 결과:', JSON.stringify(result).substring(0, 300));

        if (result.success) {
            displayMrBacktestResult(result, config.exchange, config.symbol);
            showToast('백테스트 완료', 'success');
        } else {
            const errorMsg = result.error || result.message || '백테스트 실패';
            displayMrBacktestError(errorMsg);
            showToast(errorMsg, 'error');
        }
    } catch (error) {
        console.error('[MR 백테스트] 에러:', error);
        const errorMsg = humanizeMrError(error);
        displayMrBacktestError(errorMsg);
        showToast(errorMsg, 'error');
    } finally {
        // 로딩 해제
        if (btn) {
            btn.disabled = false;
            btn.textContent = '백테스트 실행';
            btn.classList.remove('btn-loading');
        }
        if (loadingEl) loadingEl.style.display = 'none';
    }
});

function humanizeMrError(error) {
    const msg = String(error);
    if (msg.includes('timed out') || msg.includes('timeout') || msg.includes('Gateway Time-out') || msg.includes('504'))
        return '서버 응답 시간이 초과되었습니다. 기간을 줄이거나 잠시 후 다시 시도해주세요.';
    if (msg.includes('429') || msg.includes('Too Many Requests'))
        return '거래소 요청 제한에 걸렸습니다. 1~2분 후 다시 시도해주세요.';
    if (msg.includes('KIS_KR') || msg.includes('KIS_US'))
        return '주식 백테스트는 현재 준비 중입니다. OKX, Binance, Bybit에서 이용 가능합니다.';
    if (msg.includes('network') || msg.includes('fetch') || msg.includes('Failed to fetch'))
        return '서버에 연결할 수 없습니다. 네트워크를 확인해주세요.';
    if (msg.includes('Not Found') || msg.includes('404'))
        return '백테스트 API를 찾을 수 없습니다. 서버 상태를 확인해주세요.';
    if (msg.includes('int_from_float'))
        return '매수/매도 비중에 소수점이 포함되어 있습니다. 정수로 입력해주세요.';
    if (msg.includes('JSON'))
        return '서버 응답을 처리할 수 없습니다. 잠시 후 다시 시도해주세요.';
    try {
        const p = JSON.parse(msg);
        if (p.error) return p.error;
        if (p.detail) return typeof p.detail === 'string' ? p.detail : JSON.stringify(p.detail);
        if (p.message) return p.message;
    } catch {}
    return msg;
}

function displayMrBacktestError(errorMsg) {
    const errorEl = document.getElementById('mr-backtest-error');
    const resultEl = document.getElementById('mr-backtest-result');

    if (resultEl) resultEl.style.display = 'none';
    if (errorEl) {
        errorEl.innerHTML = `<strong style="color:#EF4444;">⚠️ 백테스트 실패</strong><br><span style="color:#9CA3AF;">${errorMsg}</span>`;
        errorEl.style.display = 'block';
    }
}

// ===== 화폐 단위 결정 (거래소 + 심볼 기반) =====
function getMrCurrency(exchange, symbol) {
    const ex = (exchange || '').toUpperCase();
    const sym = (symbol || '').toUpperCase();

    // 국내주식 / 업비트 → KRW
    if (ex === 'KIS_KR' || ex === 'UPBIT') return 'KRW';

    // 해외주식 → USD
    if (ex === 'KIS_US') return 'USD';

    // 코인 거래소 → 심볼 뒤의 quote currency 기반
    if (sym.endsWith('USDC') || sym.endsWith('-USDC')) return 'USDC';
    if (sym.endsWith('USDT') || sym.endsWith('-USDT') || sym.endsWith('-SWAP')) return 'USDT';
    if (sym.endsWith('BTC') || sym.endsWith('-BTC')) return 'BTC';
    if (sym.endsWith('KRW') || sym.startsWith('KRW-')) return 'KRW';

    // 기본값
    return 'USDT';
}

// ===== 금액 포맷 (만원/억 축약 없이 원본 그대로) =====
function formatMrAmount(value, currency) {
    if (value == null || isNaN(value)) return '--';
    const num = Number(value);

    switch (currency) {
        case 'KRW':
            return num.toLocaleString('ko-KR', {maximumFractionDigits: 0}) + '원';
        case 'USD':
            return '$' + Math.abs(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        default: // USDT, USDC, BTC 등
            return Math.abs(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' ' + currency;
    }
}

// ===== 부호 포함 금액 포맷 =====
function formatMrAmountSigned(value, currency) {
    if (value == null || isNaN(value)) return '--';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '-';

    switch (currency) {
        case 'KRW':
            return sign + Math.abs(num).toLocaleString('ko-KR', {maximumFractionDigits: 0}) + '원';
        case 'USD':
            return sign + '$' + Math.abs(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        default:
            return sign + Math.abs(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' ' + currency;
    }
}

// ===== 수익지수 포맷 (Infinity 처리) =====
function formatProfitFactor(value) {
    if (value == null || value === '' || value === undefined) return '--';
    const num = Number(value);
    if (!isFinite(num) || num >= 999 || value === Infinity || value === 'Infinity') return '∞';
    return num.toFixed(3);
}

// ===== 거래소 표시명 (v4 명령서) =====
const EXCHANGE_DISPLAY = {
    'KIS_KR': 'KIS_KR(한국투자증권)',
    'KIS_US': 'KIS_US(한국투자증권)',
    'UPBIT': 'UPBIT',
    'BINANCE': 'Binance',
    'BYBIT': 'BYBIT',
    'OKX': 'OKX',
};
function getExchangeDisplay(exchange) {
    return EXCHANGE_DISPLAY[(exchange || '').toUpperCase()] || exchange;
}

// ===== 캔들 차트 생성 (TradingView Lightweight Charts) =====
// 차트 인스턴스 저장용
window.mrCandleChartInstance = null;
window.trendCandleChartInstance = null;

function createBacktestCandleChart(containerId, candles, trades) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`Candle chart container not found: ${containerId}`);
        return null;
    }

    // 기존 차트 제거
    container.innerHTML = '';

    // 방어: candles가 없거나 빈 배열이면 스킵
    if (!candles || !Array.isArray(candles) || candles.length === 0) {
        container.innerHTML = '<div style="color:#6B7280; text-align:center; padding:40px;">캔들 데이터가 없습니다</div>';
        return null;
    }

    // 방어: trades가 없으면 빈 배열로 초기화
    if (!trades || !Array.isArray(trades)) {
        trades = [];
    }

    // 컨테이너 스타일 강제 적용 (무한 확장 방지)
    container.style.width = '100%';
    container.style.maxWidth = '100%';
    container.style.overflow = 'hidden';
    container.style.position = 'relative';

    // 부모 요소 너비 기준으로 차트 너비 계산
    const parentWidth = container.parentElement?.getBoundingClientRect().width || 800;
    const chartWidth = Math.min(Math.max(parentWidth - 40, 300), 1400);

    try {
    // 차트 생성
    const chart = createChart(container, {
        layout: {
            background: { type: ColorType.Solid, color: 'transparent' },
            textColor: '#9CA3AF',
        },
        grid: {
            vertLines: { color: 'rgba(255,255,255,0.05)' },
            horzLines: { color: 'rgba(255,255,255,0.05)' },
        },
        crosshair: {
            mode: CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: 'rgba(255,255,255,0.1)',
        },
        timeScale: {
            borderColor: 'rgba(255,255,255,0.1)',
            timeVisible: true,
            secondsVisible: false,
            fixLeftEdge: true,
            fixRightEdge: true,
            lockVisibleTimeRangeOnResize: true,
            tickMarkFormatter: (time) => {
                const date = new Date(time * 1000);
                const month = date.getMonth() + 1;
                const day = date.getDate();
                return `${month}/${day}`;
            },
        },
        localization: {
            dateFormat: 'yyyy-MM-dd',
            locale: 'ko-KR',
            timeFormatter: (time) => {
                const date = new Date(time * 1000);
                const y = date.getFullYear();
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            },
        },
        width: chartWidth,
        height: 400,
        handleScale: { axisPressedMouseMove: true },
        handleScroll: { vertTouchDrag: false },
    });

    // 캔들스틱 시리즈 추가
    const candleSeries = chart.addCandlestickSeries({
        upColor: '#22C55E',
        downColor: '#EF4444',
        borderUpColor: '#22C55E',
        borderDownColor: '#EF4444',
        wickUpColor: '#22C55E',
        wickDownColor: '#EF4444',
    });

    // 캔들 데이터 설정
    candleSeries.setData(candles);

    // SMA 계산 함수
    function calcSMA(data, period) {
        const result = [];
        for (let i = period - 1; i < data.length; i++) {
            let sum = 0;
            for (let j = i - period + 1; j <= i; j++) {
                sum += data[j].close;
            }
            result.push({ time: data[i].time, value: sum / period });
        }
        return result;
    }

    // 20일선 (노란색)
    if (candles.length >= 20) {
        const sma20Series = chart.addLineSeries({
            color: '#FBBF24',
            lineWidth: 1,
            lastValueVisible: false,
            priceLineVisible: false,
        });
        sma20Series.setData(calcSMA(candles, 20));
    }

    // 50일선 (주황색)
    if (candles.length >= 50) {
        const sma50Series = chart.addLineSeries({
            color: '#F97316',
            lineWidth: 1,
            lastValueVisible: false,
            priceLineVisible: false,
        });
        sma50Series.setData(calcSMA(candles, 50));
    }

    // 200일선 (파란색)
    if (candles.length >= 200) {
        const sma200Series = chart.addLineSeries({
            color: '#3B82F6',
            lineWidth: 1,
            lastValueVisible: false,
            priceLineVisible: false,
        });
        sma200Series.setData(calcSMA(candles, 200));
    }

    // 거래 마커 추가 (있는 경우)
    if (trades && trades.length > 0) {
        const markers = [];
        trades.forEach(t => {
            if (!t.timestamp) return;
            const time = Math.floor(t.timestamp / 1000);
            const isBuy = t.action === 'buy';
            markers.push({
                time: time,
                position: isBuy ? 'belowBar' : 'aboveBar',
                color: isBuy ? '#22C55E' : '#EF4444',
                shape: isBuy ? 'arrowUp' : 'arrowDown',
                text: isBuy ? 'B' : 'S',
            });
        });
        if (markers.length > 0) {
            // 시간순 정렬 (필수)
            markers.sort((a, b) => a.time - b.time);
            candleSeries.setMarkers(markers);
        }
    }

    // 차트 크기 맞추기 (전체 데이터가 화면에 맞게 표시)
    chart.timeScale().fitContent();

    // 렌더링 완료 후 다시 fitContent (확실하게)
    requestAnimationFrame(() => {
        if (chart) {
            chart.timeScale().fitContent();
        }
    });

    // 리사이즈 처리
    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || entries[0].target !== container) return;
        const newWidth = entries[0].contentRect.width;
        if (newWidth > 0 && newWidth < 2000) {
            chart.applyOptions({ width: newWidth });
            chart.timeScale().fitContent();
        }
    });
    resizeObserver.observe(container);

        return chart;
    } catch (err) {
        console.error('캔들차트 생성 에러:', err);
        container.innerHTML = '<div style="color:#F87171; text-align:center; padding:40px;">차트 생성 실패: ' + (err.message || err) + '</div>';
        return null;
    }
}

function displayMrBacktestResult(result, exchange, symbol) {
    const errorEl = document.getElementById('mr-backtest-error');
    const resultEl = document.getElementById('mr-backtest-result');

    if (!result || !result.success) {
        displayMrBacktestError(result?.error || result?.message || '결과를 받지 못했습니다.');
        return;
    }

    if (errorEl) errorEl.style.display = 'none';
    if (resultEl) resultEl.style.display = 'block';

    const m = result.metrics || {};

    // 거래소+심볼 기반 화폐 단위 결정
    const currency = getMrCurrency(result.exchange || exchange, result.symbol || symbol);

    // 헬퍼: 금액 포맷
    const fmtAmt = (v) => formatMrAmount(v, currency);

    // null-safe 헬퍼
    const set = (id, value, color) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = value;
        if (color) el.style.color = color;
    };

    // 색상 헬퍼
    const pnlColor = (v) => (Number(v) || 0) >= 0 ? '#22C55E' : '#EF4444';

    // 메시지
    set('mr-bt-message', result.message || '');

    // ===== 상단 카드 5개 (트레이딩뷰 동일) =====
    // 1. 총 손익
    set('mr-bt-net-profit', fmtAmt(m.net_profit), pnlColor(m.net_profit));
    const netPct = m.net_profit_pct ?? 0;
    set('mr-bt-net-profit-pct', `${netPct > 0 ? '+' : ''}${netPct.toFixed(2)}%`, pnlColor(netPct));

    // 2. 최대 자본 감소
    set('mr-bt-mdd', fmtAmt(m.max_drawdown));
    const mddPct = m.max_drawdown_pct ?? 0;
    set('mr-bt-mdd-pct', `${mddPct.toFixed(2)}%`);

    // 3. 총 거래횟수
    set('mr-bt-total-trades', `${m.total_trades ?? 0}회`);

    // 4. 수익성 거래 (승률 + n/n)
    set('mr-bt-winrate', `${(m.win_rate_pct ?? 0).toFixed(1)}%`, pnlColor((m.win_rate_pct ?? 0) - 50));
    const wt = m.winning_trades ?? 0;
    const lt = m.losing_trades ?? 0;
    set('mr-bt-winrate-detail', `${wt}/${wt + lt}`);

    // 5. 수익지수
    set('mr-bt-profit-factor', formatProfitFactor(m.profit_factor));

    // ===== 수익률 테이블 (전체/매수/매도 3열) =====
    renderMrPerformanceTable(m, currency, fmtAmt);

    // ===== 자산 추이 차트 (Y축 수익률%) =====
    if (result.equity_curve && result.equity_curve.length > 0) {
        drawMrBacktestChart(result.equity_curve, m.initial_capital || 10000000, currency);
    }

    // ===== 캔들 차트 (TradingView Lightweight Charts) =====
    if (result.candles && result.candles.length > 0) {
        if (window.mrCandleChartInstance) {
            window.mrCandleChartInstance.remove();
        }
        window.mrCandleChartInstance = createBacktestCandleChart('mr-candle-chart', result.candles, result.trades);
    }

    // ===== 거래 내역 테이블 =====
    renderMrTradesTable(result.trades || [], currency);
}

function renderMrPerformanceTable(m, currency, fmtAmt) {
    const tbody = document.getElementById('mr-bt-perf-body');
    if (!tbody) return;

    const pnlColor = (v) => (Number(v) || 0) >= 0 ? '#22C55E' : '#EF4444';

    const row = (label, allAmt, allPct, buyAmt, buyPct, sellAmt, sellPct) => {
        const fPct = (v) => v != null ? `<br><span style="font-size:11px;color:${pnlColor(v)}">${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%</span>` : '';
        const cellColor = (v) => pnlColor(v);
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:${cellColor(allAmt)};">${fmtAmt(allAmt)}${fPct(allPct)}</td>
            <td style="text-align:right; color:${cellColor(buyAmt)};">${fmtAmt(buyAmt)}${fPct(buyPct)}</td>
            <td style="text-align:right; color:#6B7280;">${sellAmt != null && sellAmt !== 0 ? fmtAmt(sellAmt) : '—'}${sellPct != null && sellPct !== 0 ? fPct(sellPct) : ''}</td>
        </tr>`;
    };

    const simpleRow = (label, all, buy, sell) => {
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:#D1D5DB;">${all ?? '—'}</td>
            <td style="text-align:right; color:#D1D5DB;">${buy ?? '—'}</td>
            <td style="text-align:right; color:#6B7280;">${sell != null && sell !== 0 ? sell : '—'}</td>
        </tr>`;
    };

    tbody.innerHTML = [
        row('순손익', m.net_profit, m.net_profit_pct, m.buy_net_profit, m.buy_net_profit_pct, m.sell_net_profit, m.sell_net_profit_pct),
        row('총수익', m.gross_profit, m.gross_profit_pct, m.buy_gross_profit, m.buy_gross_profit_pct, m.sell_gross_profit, m.sell_gross_profit_pct),
        row('총손실', m.gross_loss ? -Math.abs(m.gross_loss) : 0, m.gross_loss_pct ? -Math.abs(m.gross_loss_pct) : 0,
            m.buy_gross_loss ? -Math.abs(m.buy_gross_loss) : 0, m.buy_gross_loss_pct ? -Math.abs(m.buy_gross_loss_pct) : 0, null, null),
        row('미실현 손익', m.unrealized_pnl, m.unrealized_pnl_pct, null, null, null, null),
        simpleRow('수익지수', formatProfitFactor(m.profit_factor), formatProfitFactor(m.buy_profit_factor), '—'),
        simpleRow('수수료', fmtAmt(m.commission_paid), fmtAmt(m.buy_commission), fmtAmt(m.sell_commission)),
        simpleRow('기대수익', fmtAmt(m.expected_value), fmtAmt(m.buy_expected_value), fmtAmt(m.sell_expected_value)),
    ].join('');
}

function renderMrTradesTable(trades, currency) {
    const tbody = document.getElementById('mr-bt-trades-body');
    const countEl = document.getElementById('mr-bt-trade-count');
    if (!tbody) return;

    if (countEl) countEl.textContent = `총 ${trades.length}건`;

    if (trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:#6B7280;">거래 내역이 없습니다</td></tr>';
        return;
    }

    tbody.innerHTML = trades.map((t, idx) => {
        // 타입 (서버에서 이미 한글로 옴)
        const isBuy = (t.type === '매수' || t.action === 'buy' || t.action === 'BUY');
        const typeColor = isBuy ? '#3B82F6' : '#EF4444';
        const typeText = t.type || (isBuy ? '매수' : '매도');

        // 날짜 (서버에서 date 필드로 옴)
        const dateStr = t.date || '';

        // 가격
        const priceStr = t.price ? Number(t.price).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '-';

        // 수량
        const qtyStr = t.qty != null ? Number(t.qty).toFixed(6) : (t.quantity != null ? Number(t.quantity).toFixed(6) : '-');

        // 차수 (서버에서 tranche 필드로 이미 한글로 옴)
        const trancheText = t.tranche || '-';

        // 수익금 (금액) — formatMrAmountSigned 사용
        const pnlColor = (t.pnl || 0) >= 0 ? '#22C55E' : '#EF4444';
        const pnlAmtText = (t.pnl != null && !isBuy) ? formatMrAmountSigned(t.pnl, currency) : '-';

        // 수익률 (%)
        const pnlPctText = t.pnl_pct != null && !isBuy ? `${t.pnl_pct > 0 ? '+' : ''}${Number(t.pnl_pct).toFixed(2)}%` : '-';

        // 누적
        const cumColor = (t.cumulative_pnl || 0) >= 0 ? '#22C55E' : '#EF4444';
        const cumText = t.cumulative_pnl != null ? formatMrAmount(t.cumulative_pnl, currency) : '-';

        return `<tr>
            <td style="padding:6px 4px; color:#9CA3AF;">${t.no || idx + 1}</td>
            <td style="padding:6px 4px; color:${typeColor}; font-weight:600;">${typeText}</td>
            <td style="padding:6px 4px; color:#D1D5DB;">${dateStr}</td>
            <td style="padding:6px 4px; text-align:right; color:#E5E7EB;">${priceStr}</td>
            <td style="padding:6px 4px; text-align:right; color:#D1D5DB;">${qtyStr}</td>
            <td style="padding:6px 4px; color:#9CA3AF;">${trancheText}</td>
            <td style="padding:6px 4px; text-align:right; color:${pnlColor};">${pnlAmtText}</td>
            <td style="padding:6px 4px; text-align:right; color:${pnlColor};">${pnlPctText}</td>
            <td style="padding:6px 4px; text-align:right; color:${cumColor};">${cumText}</td>
        </tr>`;
    }).join('');
}

function drawMrBacktestChart(equityCurve, initialCapital = 10000000, currency = 'USDT') {
    const canvas = document.getElementById('mr-backtest-chart');
    if (!canvas || !window.Chart) return;

    const ctx = canvas.getContext('2d');

    // 기존 차트 완전 제거 (instanceof Chart 체크)
    if (window.mrBacktestChart instanceof Chart) {
        window.mrBacktestChart.destroy();
        window.mrBacktestChart = null;
    }

    if (!equityCurve || equityCurve.length === 0) return;

    // canvas 크기 리셋 (무한 확장 방지)
    canvas.style.height = '100%';
    canvas.style.width = '100%';

    // 초기자본 추출 (첫 데이터 또는 전달된 값)
    const initCap = equityCurve[0]?.equity || initialCapital;

    // 날짜 라벨 생성
    const labels = equityCurve.map(p => {
        if (p.timestamp) {
            const d = new Date(p.timestamp);
            return `${d.getMonth() + 1}/${d.getDate()}`;
        }
        return '';
    });

    // Y축 데이터: 수익률 % (백엔드에서 pct 필드 제공, 없으면 직접 계산)
    const data = equityCurve.map(p => {
        if (p.pct !== undefined) return p.pct;
        return initCap > 0 ? ((p.equity - initCap) / initCap) * 100 : 0;
    });

    // 최종 수익률 기준으로 전체 색상 결정
    const finalPct = data[data.length - 1] || 0;
    const isProfitable = finalPct >= 0;
    const mainColor = isProfitable ? '#22C55E' : '#EF4444';
    const fillGradient = ctx.createLinearGradient(0, 0, 0, 300);
    fillGradient.addColorStop(0, isProfitable ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)');
    fillGradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    window.mrBacktestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                // 0% 기준선
                {
                    label: '기준선',
                    data: Array(data.length).fill(0),
                    borderColor: 'rgba(156, 163, 175, 0.5)',
                    borderDash: [5, 5],
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: false,
                },
                // 수익률 추이
                {
                    label: '수익률',
                    data: data,
                    borderColor: mainColor,
                    backgroundColor: fillGradient,
                    borderWidth: 2,
                    fill: true,
                    tension: 0.2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: mainColor,
                    segment: {
                        borderColor: ctx => {
                            const y = ctx.p0?.parsed?.y;
                            return y >= 0 ? '#22C55E' : '#EF4444';
                        }
                    }
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#E5E7EB',
                    bodyColor: '#D1D5DB',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        title: (items) => {
                            const idx = items[0]?.dataIndex;
                            if (idx !== undefined && equityCurve[idx]?.timestamp) {
                                const d = new Date(equityCurve[idx].timestamp);
                                return d.toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' });
                            }
                            return '';
                        },
                        label: (item) => {
                            if (item.datasetIndex === 0) return null; // 기준선은 숨김
                            const idx = item.dataIndex;
                            const pct = item.raw;
                            const equity = equityCurve[idx]?.equity || 0;
                            const pnl = equity - initCap;
                            const sign = pct >= 0 ? '+' : '';

                            // 만원/억 단위 절대 사용 금지 — 원본 금액 그대로 표시
                            return [
                                `수익률: ${sign}${pct.toFixed(2)}%`,
                                `손익: ${formatMrAmountSigned(pnl, currency)}`,
                                `자산: ${formatMrAmount(equity, currency)}`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#6B7280',
                        font: { size: 10 },
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    }
                },
                y: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#6B7280',
                        font: { size: 10 },
                        callback: function(value) {
                            const sign = value >= 0 ? '+' : '';
                            return `${sign}${value.toFixed(1)}%`;
                        }
                    }
                }
            }
        }
    });
}

// =====================================================
// Trend 백테스트 (추세매매)
// =====================================================
let trendBacktestChart = null;

async function loadTrendExchangeDropdown() {
    const select = document.getElementById('trend-exchange');
    if (!select) return;

    // 기본 거래소 목록 (v4 명령서 순서: KIS_KR → KIS_US → UPBIT → Binance → BYBIT → OKX)
    const defaultExchanges = ['KIS_KR', 'KIS_US', 'UPBIT', 'BINANCE', 'BYBIT', 'OKX'];

    try {
        let accounts = [];
        try {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken || '' });
        } catch { }

        if (!accounts || accounts.length === 0) {
            try {
                accounts = await invoke('list_local_accounts');
            } catch { }
        }

        // 등록된 계정의 거래소 추출
        const registeredExchanges = new Set();
        (accounts || []).forEach(acc => {
            const exName = acc.exchange?.toUpperCase() || acc.exchange_name?.toUpperCase();
            if (exName) registeredExchanges.add(exName);
        });

        // 기본 + 등록된 거래소 합치기 (중복 제거)
        const allExchanges = [...new Set([...defaultExchanges, ...registeredExchanges])];

        select.innerHTML = '<option value="">선택하세요</option>';
        allExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    } catch (error) {
        console.error('거래소 드롭다운 로드 실패:', error);
        // 에러 시에도 기본 거래소 표시
        select.innerHTML = '<option value="">선택하세요</option>';
        defaultExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    }

    // KIS 거래소 선택 시 설정 모달 표시
    select.addEventListener('change', () => {
        handleExchangeChange({ target: select });
    });
}


// =====================================================
// Custom Strategy (커스텀 전략 조건 빌더)
// =====================================================
let customBacktestChart = null;
let indicatorRegistry = null;  // 지표 레지스트리 캐시

// 거래소 드롭다운 초기화 (MR/Trend와 동일 패턴)
async function loadCustomExchangeDropdown() {
    const select = document.getElementById('custom-exchange');
    if (!select) return;

    // 기본 거래소 목록 (v4 명령서 순서: KIS_KR → KIS_US → UPBIT → Binance → BYBIT → OKX)
    const defaultExchanges = ['KIS_KR', 'KIS_US', 'UPBIT', 'BINANCE', 'BYBIT', 'OKX'];

    try {
        let accounts = [];
        try {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken || '' });
        } catch { }

        if (!accounts || accounts.length === 0) {
            try {
                accounts = await invoke('list_local_accounts');
            } catch { }
        }

        const registeredExchanges = new Set();
        (accounts || []).forEach(acc => {
            const exName = acc.exchange?.toUpperCase() || acc.exchange_name?.toUpperCase();
            if (exName) registeredExchanges.add(exName);
        });

        const allExchanges = [...new Set([...defaultExchanges, ...registeredExchanges])];

        select.innerHTML = '<option value="">선택하세요</option>';
        allExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    } catch (error) {
        console.error('커스텀 거래소 드롭다운 로드 실패:', error);
        select.innerHTML = '<option value="">선택하세요</option>';
        defaultExchanges.forEach(ex => {
            const displayName = EXCHANGE_DISPLAY[ex] || ex;
            select.innerHTML += `<option value="${ex}">${displayName}</option>`;
        });
    }

    // 거래소 변경 시 종목 필터 업데이트 + KIS 설정 모달
    select.addEventListener('change', () => {
        if (customSymbolAutocomplete) {
            customSymbolAutocomplete.setExchange(select.value);
        }
        updateCustomTimeframeOptions(select.value);
        handleExchangeChange({ target: select });
    });
}

// KIS 거래소 타임프레임 제한
function updateCustomTimeframeOptions(exchange) {
    const tfSelect = document.getElementById('custom-timeframe');
    if (!tfSelect) return;

    const isKIS = exchange === 'KIS_KR' || exchange === 'KIS_US';
    const kisAllowedTfs = ['1D', '1W', '1M'];

    Array.from(tfSelect.options).forEach(opt => {
        if (isKIS) {
            opt.disabled = !kisAllowedTfs.includes(opt.value);
        } else {
            opt.disabled = false;
        }
    });

    if (isKIS && !kisAllowedTfs.includes(tfSelect.value)) {
        tfSelect.value = '1D';
    }
}

// 조건 빌더 초기화
async function initCustomConditionBuilder() {
    // 지표 레지스트리 로드
    if (!indicatorRegistry) {
        try {
            const resp = await fetch('https://qube-system.com/api/premium/indicators');
            const data = await resp.json();
            if (data.success) {
                indicatorRegistry = data.indicators;
                window.indicatorOperators = data.operators || [];
            }
        } catch (e) {
            console.error('지표 레지스트리 로드 실패:', e);
            // 기본 지표 레지스트리 (폴백)
            indicatorRegistry = getDefaultIndicatorRegistry();
        }
    }

    // 조건 그룹 초기화
    initConditionGroups('entry');
    initConditionGroups('exit');

    // 이벤트 리스너 설정
    setupConditionBuilderListeners();
}

// 기본 지표 레지스트리 (API 실패 시 폴백)
function getDefaultIndicatorRegistry() {
    return {
        // 이동평균 (6개)
        "SMA": { name: "단순이동평균 (SMA)", category: "이동평균", params: [{ key: "period", label: "기간", default: 20, min: 2, max: 500, type: "int" }], outputs: ["value"] },
        "EMA": { name: "지수이동평균 (EMA)", category: "이동평균", params: [{ key: "period", label: "기간", default: 20, min: 2, max: 500, type: "int" }], outputs: ["value"] },
        "WMA": { name: "가중이동평균 (WMA)", category: "이동평균", params: [{ key: "period", label: "기간", default: 20, min: 2, max: 500, type: "int" }], outputs: ["value"] },
        "HMA": { name: "헐이동평균 (HMA)", category: "이동평균", params: [{ key: "period", label: "기간", default: 20, min: 2, max: 500, type: "int" }], outputs: ["value"] },
        "VWMA": { name: "거래량가중이동평균 (VWMA)", category: "이동평균", params: [{ key: "period", label: "기간", default: 20, min: 2, max: 500, type: "int" }], outputs: ["value"] },
        "BB": { name: "볼린저 밴드", category: "이동평균", params: [{ key: "period", label: "기간", default: 20 }, { key: "std_mult", label: "표준편차 배수", default: 2.0 }], outputs: ["upper", "middle", "lower"] },
        // 오실레이터 (4개)
        "RSI": { name: "RSI (상대강도지수)", category: "오실레이터", params: [{ key: "period", label: "기간", default: 14, min: 2, max: 100, type: "int" }], outputs: ["value"] },
        "MACD": { name: "MACD", category: "오실레이터", params: [{ key: "fast_length", label: "단기", default: 12 }, { key: "slow_length", label: "장기", default: 26 }, { key: "signal_length", label: "시그널", default: 9 }], outputs: ["macd", "signal", "histogram"] },
        "STOCH": { name: "스토캐스틱", category: "오실레이터", params: [{ key: "k_period", label: "K 기간", default: 14 }, { key: "d_period", label: "D 기간", default: 3 }, { key: "slowing", label: "슬로잉", default: 3 }], outputs: ["k", "d"] },
        "CCI": { name: "CCI (상품채널지수)", category: "오실레이터", params: [{ key: "period", label: "기간", default: 20 }], outputs: ["value"] },
        // 추세 (3개)
        "ADX": { name: "ADX (평균방향지수)", category: "추세", params: [{ key: "period", label: "기간", default: 14 }], outputs: ["adx", "plus_di", "minus_di"] },
        "SUPERTREND": { name: "슈퍼트렌드", category: "추세", params: [{ key: "atr_len", label: "ATR 길이", default: 20 }, { key: "factor", label: "팩터", default: 5.0 }], outputs: ["direction", "value"] },
        "ICHIMOKU": { name: "일목균형표", category: "추세", params: [{ key: "tenkan_len", label: "전환선", default: 9 }, { key: "kijun_len", label: "기준선", default: 26 }, { key: "senkou_len", label: "선행스팬B", default: 52 }, { key: "chikou_offset", label: "전환", default: 26 }], outputs: ["tenkan", "kijun", "senkou_a", "senkou_b", "chikou"] },
        // 변동성 (1개)
        "ATR": { name: "ATR (평균진폭)", category: "변동성", params: [{ key: "period", label: "기간", default: 14 }], outputs: ["value"] },
        // 가격 (1개)
        "PRICE": { name: "가격", category: "가격", params: [], outputs: ["open", "high", "low", "close", "volume"] },
    };
}

// 연산자 목록 (7개)
function getOperators() {
    return window.indicatorOperators || [
        { value: ">", label: ">" },
        { value: "<", label: "<" },
        { value: ">=", label: ">=" },
        { value: "<=", label: "<=" },
        { value: "==", label: "==" },
        { value: "cross_above", label: "상향돌파 (골든크로스)" },
        { value: "cross_below", label: "하향돌파 (데드크로스)" },
    ];
}

// ═══════════════════════════════════════════════════════════════
// 지표별 프리셋 (자주 쓰는 조건)
// ═══════════════════════════════════════════════════════════════
const INDICATOR_PRESETS = {
    "RSI": [
        { label: "과매도 진입 (RSI < 30)", description: "RSI가 30 이하로 내려가면 매수", config: { indicator: "RSI", output: "value", params: { period: 14 }, operator: "<", compare_type: "value", compare_value: 30 } },
        { label: "과매수 진입 (RSI > 70)", description: "RSI가 70 이상으로 올라가면 매도", config: { indicator: "RSI", output: "value", params: { period: 14 }, operator: ">", compare_type: "value", compare_value: 70 } },
        { label: "과매도 탈출 (RSI ↑ 30)", description: "RSI가 30을 상향 돌파", config: { indicator: "RSI", output: "value", params: { period: 14 }, operator: "cross_above", compare_type: "value", compare_value: 30 } },
        { label: "과매수 탈출 (RSI ↓ 70)", description: "RSI가 70을 하향 돌파", config: { indicator: "RSI", output: "value", params: { period: 14 }, operator: "cross_below", compare_type: "value", compare_value: 70 } },
        { label: "중립선 상향돌파 (RSI ↑ 50)", description: "상승 추세 시작", config: { indicator: "RSI", output: "value", params: { period: 14 }, operator: "cross_above", compare_type: "value", compare_value: 50 } },
    ],
    "MACD": [
        { label: "골든크로스 (MACD ↑ 시그널)", description: "매수 신호", config: { indicator: "MACD", output: "macd", params: { fast_length: 12, slow_length: 26, signal_length: 9 }, operator: "cross_above", compare_type: "indicator", compare_indicator: "MACD", compare_output: "signal", compare_params: { fast_length: 12, slow_length: 26, signal_length: 9 } } },
        { label: "데드크로스 (MACD ↓ 시그널)", description: "매도 신호", config: { indicator: "MACD", output: "macd", params: { fast_length: 12, slow_length: 26, signal_length: 9 }, operator: "cross_below", compare_type: "indicator", compare_indicator: "MACD", compare_output: "signal", compare_params: { fast_length: 12, slow_length: 26, signal_length: 9 } } },
        { label: "히스토그램 양전환", description: "상승 모멘텀", config: { indicator: "MACD", output: "histogram", params: { fast_length: 12, slow_length: 26, signal_length: 9 }, operator: "cross_above", compare_type: "value", compare_value: 0 } },
        { label: "히스토그램 음전환", description: "하락 모멘텀", config: { indicator: "MACD", output: "histogram", params: { fast_length: 12, slow_length: 26, signal_length: 9 }, operator: "cross_below", compare_type: "value", compare_value: 0 } },
    ],
    "BB": [
        { label: "하단밴드 터치 (과매도)", description: "종가 < 하단밴드 = 반등 기대", config: { indicator: "PRICE", output: "close", params: {}, operator: "<", compare_type: "indicator", compare_indicator: "BB", compare_output: "lower", compare_params: { period: 20, std_mult: 2.0 } } },
        { label: "상단밴드 터치 (과매수)", description: "종가 > 상단밴드 = 조정 기대", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "BB", compare_output: "upper", compare_params: { period: 20, std_mult: 2.0 } } },
        { label: "중간밴드 상향돌파", description: "20일선 돌파", config: { indicator: "PRICE", output: "close", params: {}, operator: "cross_above", compare_type: "indicator", compare_indicator: "BB", compare_output: "middle", compare_params: { period: 20, std_mult: 2.0 } } },
    ],
    "STOCH": [
        { label: "과매도 (%K < 20)", description: "과매도 구간", config: { indicator: "STOCH", output: "k", params: { k_period: 14, d_period: 3, slowing: 3 }, operator: "<", compare_type: "value", compare_value: 20 } },
        { label: "과매수 (%K > 80)", description: "과매수 구간", config: { indicator: "STOCH", output: "k", params: { k_period: 14, d_period: 3, slowing: 3 }, operator: ">", compare_type: "value", compare_value: 80 } },
        { label: "골든크로스 (%K ↑ %D)", description: "매수 신호", config: { indicator: "STOCH", output: "k", params: { k_period: 14, d_period: 3, slowing: 3 }, operator: "cross_above", compare_type: "indicator", compare_indicator: "STOCH", compare_output: "d", compare_params: { k_period: 14, d_period: 3, slowing: 3 } } },
        { label: "데드크로스 (%K ↓ %D)", description: "매도 신호", config: { indicator: "STOCH", output: "k", params: { k_period: 14, d_period: 3, slowing: 3 }, operator: "cross_below", compare_type: "indicator", compare_indicator: "STOCH", compare_output: "d", compare_params: { k_period: 14, d_period: 3, slowing: 3 } } },
    ],
    "SMA": [
        { label: "종가 > 이평선 (상승추세)", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "SMA", compare_output: "value", compare_params: { period: 20 } } },
        { label: "종가 < 이평선 (하락추세)", config: { indicator: "PRICE", output: "close", params: {}, operator: "<", compare_type: "indicator", compare_indicator: "SMA", compare_output: "value", compare_params: { period: 20 } } },
        { label: "골든크로스", description: "단기>장기", config: { indicator: "SMA", output: "value", params: { period: 20 }, operator: "cross_above", compare_type: "indicator", compare_indicator: "SMA", compare_output: "value", compare_params: { period: 50 } } },
        { label: "데드크로스", description: "단기<장기", config: { indicator: "SMA", output: "value", params: { period: 20 }, operator: "cross_below", compare_type: "indicator", compare_indicator: "SMA", compare_output: "value", compare_params: { period: 50 } } },
    ],
    "EMA": [
        { label: "종가 > 이평선", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "EMA", compare_output: "value", compare_params: { period: 20 } } },
        { label: "골든크로스", config: { indicator: "EMA", output: "value", params: { period: 12 }, operator: "cross_above", compare_type: "indicator", compare_indicator: "EMA", compare_output: "value", compare_params: { period: 26 } } },
    ],
    "SUPERTREND": [
        { label: "상승전환 (매수)", description: "하락→상승", config: { indicator: "SUPERTREND", output: "direction", params: { atr_len: 20, factor: 5.0 }, operator: "cross_below", compare_type: "value", compare_value: 0 } },
        { label: "하락전환 (매도)", description: "상승→하락", config: { indicator: "SUPERTREND", output: "direction", params: { atr_len: 20, factor: 5.0 }, operator: "cross_above", compare_type: "value", compare_value: 0 } },
        { label: "상승 유지", description: "direction < 0", config: { indicator: "SUPERTREND", output: "direction", params: { atr_len: 20, factor: 5.0 }, operator: "<", compare_type: "value", compare_value: 0 } },
        { label: "하락 유지", description: "direction > 0", config: { indicator: "SUPERTREND", output: "direction", params: { atr_len: 20, factor: 5.0 }, operator: ">", compare_type: "value", compare_value: 0 } },
    ],
    "ADX": [
        { label: "강한 추세 (ADX > 25)", config: { indicator: "ADX", output: "adx", params: { period: 14 }, operator: ">", compare_type: "value", compare_value: 25 } },
        { label: "약한 추세 (ADX < 20)", description: "횡보 구간", config: { indicator: "ADX", output: "adx", params: { period: 14 }, operator: "<", compare_type: "value", compare_value: 20 } },
        { label: "상승 추세 (+DI > -DI)", config: { indicator: "ADX", output: "plus_di", params: { period: 14 }, operator: ">", compare_type: "indicator", compare_indicator: "ADX", compare_output: "minus_di", compare_params: { period: 14 } } },
        { label: "하락 추세 (-DI > +DI)", config: { indicator: "ADX", output: "minus_di", params: { period: 14 }, operator: ">", compare_type: "indicator", compare_indicator: "ADX", compare_output: "plus_di", compare_params: { period: 14 } } },
    ],
    "CCI": [
        { label: "과매도 (CCI < -100)", config: { indicator: "CCI", output: "value", params: { period: 20 }, operator: "<", compare_type: "value", compare_value: -100 } },
        { label: "과매수 (CCI > 100)", config: { indicator: "CCI", output: "value", params: { period: 20 }, operator: ">", compare_type: "value", compare_value: 100 } },
        { label: "중립선 상향돌파", config: { indicator: "CCI", output: "value", params: { period: 20 }, operator: "cross_above", compare_type: "value", compare_value: 0 } },
    ],
    "ATR": [
        { label: "변동성 크다 (ATR > 기준)", config: { indicator: "ATR", output: "value", params: { period: 14 }, operator: ">", compare_type: "value", compare_value: 1000 } },
    ],
    "ICHIMOKU": [
        { label: "구름 위 (상승추세)", description: "종가 > 선행스팬A", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "ICHIMOKU", compare_output: "senkou_a", compare_params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 } } },
        { label: "구름 아래 (하락추세)", description: "종가 < 선행스팬B", config: { indicator: "PRICE", output: "close", params: {}, operator: "<", compare_type: "indicator", compare_indicator: "ICHIMOKU", compare_output: "senkou_b", compare_params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 } } },
        { label: "전환선 > 기준선", config: { indicator: "ICHIMOKU", output: "tenkan", params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 }, operator: ">", compare_type: "indicator", compare_indicator: "ICHIMOKU", compare_output: "kijun", compare_params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 } } },
        { label: "전환선 ↑ 기준선", description: "매수 신호", config: { indicator: "ICHIMOKU", output: "tenkan", params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 }, operator: "cross_above", compare_type: "indicator", compare_indicator: "ICHIMOKU", compare_output: "kijun", compare_params: { tenkan_len: 9, kijun_len: 26, senkou_len: 52, chikou_offset: 26 } } },
    ],
    "PRICE": [
        { label: "양봉 (종가 > 시가)", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "PRICE", compare_output: "open", compare_params: {} } },
        { label: "음봉 (종가 < 시가)", config: { indicator: "PRICE", output: "close", params: {}, operator: "<", compare_type: "indicator", compare_indicator: "PRICE", compare_output: "open", compare_params: {} } },
    ],
    "WMA": [
        { label: "종가 > 이평선", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "WMA", compare_output: "value", compare_params: { period: 20 } } },
    ],
    "HMA": [
        { label: "종가 > 이평선", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "HMA", compare_output: "value", compare_params: { period: 20 } } },
    ],
    "VWMA": [
        { label: "종가 > 이평선", config: { indicator: "PRICE", output: "close", params: {}, operator: ">", compare_type: "indicator", compare_indicator: "VWMA", compare_output: "value", compare_params: { period: 20 } } },
    ],
};

// 프리셋 옵션 생성
function getPresetOptions(indicatorKey) {
    const presets = INDICATOR_PRESETS[indicatorKey] || [];
    if (presets.length === 0) return '<option value="">프리셋 없음</option>';
    return presets.map((p, i) => `<option value="${i}" title="${p.description || ''}">${p.label}</option>`).join('');
}

// 조건 그룹 초기화
function initConditionGroups(type) {
    const container = document.getElementById(`${type}-condition-groups`);
    if (!container) return;

    container.innerHTML = '';
    addConditionGroup(type);
}

// 조건 그룹 추가
function addConditionGroup(type) {
    const container = document.getElementById(`${type}-condition-groups`);
    if (!container) return;

    const groupCount = container.querySelectorAll('.condition-group').length;
    const groupId = `${type}-group-${groupCount}`;

    const groupDiv = document.createElement('div');
    groupDiv.className = 'condition-group';
    groupDiv.dataset.groupId = groupId;

    groupDiv.innerHTML = `
        <div class="condition-group-header">
            <span class="group-label">그룹 ${groupCount + 1}</span>
            ${groupCount > 0 ? '<span class="group-logic-label">OR</span>' : ''}
            <button type="button" class="btn-remove-group" title="그룹 삭제">&times;</button>
        </div>
        <div class="conditions-list" data-group-id="${groupId}"></div>
        <div class="condition-actions">
            <button type="button" class="btn btn-secondary btn-sm btn-add-condition">+ 조건 추가</button>
        </div>
    `;

    container.appendChild(groupDiv);

    // 첫 번째 조건 추가
    addCondition(groupId);

    // 이벤트 바인딩
    groupDiv.querySelector('.btn-remove-group')?.addEventListener('click', () => {
        if (container.querySelectorAll('.condition-group').length > 1) {
            groupDiv.remove();
            updateGroupLabels(type);
        }
    });

    groupDiv.querySelector('.btn-add-condition')?.addEventListener('click', () => {
        addCondition(groupId);
    });
}

// 그룹 라벨 업데이트
function updateGroupLabels(type) {
    const container = document.getElementById(`${type}-condition-groups`);
    if (!container) return;

    container.querySelectorAll('.condition-group').forEach((group, idx) => {
        const label = group.querySelector('.group-label');
        if (label) label.textContent = `그룹 ${idx + 1}`;

        const logicLabel = group.querySelector('.group-logic-label');
        if (idx === 0 && logicLabel) {
            logicLabel.remove();
        } else if (idx > 0 && !logicLabel) {
            const header = group.querySelector('.condition-group-header');
            const span = document.createElement('span');
            span.className = 'group-logic-label';
            span.textContent = 'OR';
            header.insertBefore(span, header.querySelector('.btn-remove-group'));
        }
    });
}

// 조건 추가 (프리셋/직접설정 모드 지원)
function addCondition(groupId) {
    const container = document.querySelector(`.conditions-list[data-group-id="${groupId}"]`);
    if (!container) return;

    const conditionCount = container.querySelectorAll('.condition-row').length;
    const conditionId = `${groupId}-cond-${conditionCount}`;

    const condDiv = document.createElement('div');
    condDiv.className = 'condition-row';
    condDiv.dataset.conditionId = conditionId;
    condDiv.dataset.mode = 'preset'; // 기본 모드: 프리셋

    condDiv.innerHTML = `
        <div class="cond-header">
            <select class="cond-indicator-select">
                ${getIndicatorOptions()}
            </select>
            <select class="cond-mode-select">
                <option value="preset">프리셋</option>
                <option value="manual">직접설정</option>
            </select>
        </div>
        <div class="preset-section" style="display:flex;">
            <select class="cond-preset-select">
                ${getPresetOptions('SMA')}
            </select>
            <div class="preset-params"></div>
        </div>
        <div class="manual-section" style="display:none;">
            <select class="cond-output" data-side="left">
                <option value="value">값</option>
            </select>
            <div class="cond-params" data-side="left"></div>
            <select class="cond-operator">
                ${getOperatorOptions()}
            </select>
            <select class="cond-compare-type">
                <option value="value">고정값</option>
                <option value="indicator">지표 비교</option>
            </select>
            <input type="number" class="cond-compare-value" placeholder="값 입력" step="any">
            <div class="cond-compare-indicator" style="display:none;">
                <select class="cond-indicator" data-side="right">
                    ${getIndicatorOptions()}
                </select>
                <select class="cond-output" data-side="right">
                    <option value="value">값</option>
                </select>
                <div class="cond-params" data-side="right"></div>
            </div>
        </div>
        <button type="button" class="btn-remove-condition" title="조건 삭제">&times;</button>
    `;

    container.appendChild(condDiv);

    // 이벤트 바인딩
    bindConditionEvents(condDiv);

    // 초기 프리셋 로드
    updatePresetSection(condDiv);
}

// 지표 옵션 생성
function getIndicatorOptions() {
    if (!indicatorRegistry) return '<option value="">로드 중...</option>';

    let options = '';
    const categories = {};

    // 카테고리별 그룹화
    for (const [key, ind] of Object.entries(indicatorRegistry)) {
        const cat = ind.category || '기타';
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push({ key, name: ind.name });
    }

    for (const [cat, indicators] of Object.entries(categories)) {
        options += `<optgroup label="${cat}">`;
        for (const ind of indicators) {
            options += `<option value="${ind.key}">${ind.name}</option>`;
        }
        options += '</optgroup>';
    }

    return options;
}

// 연산자 옵션 생성
function getOperatorOptions() {
    return getOperators().map(op =>
        `<option value="${op.value}">${op.label}</option>`
    ).join('');
}

// 조건 이벤트 바인딩 (프리셋/직접설정 모드 지원)
function bindConditionEvents(condDiv) {
    // 지표 선택 변경 (프리셋과 직접설정 모두 영향)
    const indicatorSelect = condDiv.querySelector('.cond-indicator-select');
    indicatorSelect?.addEventListener('change', () => {
        updatePresetSection(condDiv);
        updateManualSection(condDiv);
    });

    // 모드 변경 (프리셋 ↔ 직접설정)
    const modeSelect = condDiv.querySelector('.cond-mode-select');
    modeSelect?.addEventListener('change', () => {
        const mode = modeSelect.value;
        condDiv.dataset.mode = mode;
        const presetSection = condDiv.querySelector('.preset-section');
        const manualSection = condDiv.querySelector('.manual-section');
        if (mode === 'preset') {
            presetSection.style.display = 'flex';
            manualSection.style.display = 'none';
        } else {
            presetSection.style.display = 'none';
            manualSection.style.display = 'flex';
        }
    });

    // 프리셋 선택 변경
    const presetSelect = condDiv.querySelector('.cond-preset-select');
    presetSelect?.addEventListener('change', () => {
        renderPresetParams(condDiv);
    });

    // 직접설정 모드: 오른쪽 지표 변경
    const rightIndicator = condDiv.querySelector('.cond-compare-indicator .cond-indicator');
    rightIndicator?.addEventListener('change', () => {
        updateIndicatorParams(condDiv, 'right');
        updateIndicatorOutputs(condDiv, 'right');
    });

    // 직접설정 모드: 비교 타입 변경
    const compareType = condDiv.querySelector('.cond-compare-type');
    compareType?.addEventListener('change', () => {
        const isIndicator = compareType.value === 'indicator';
        condDiv.querySelector('.cond-compare-value').style.display = isIndicator ? 'none' : 'block';
        condDiv.querySelector('.cond-compare-indicator').style.display = isIndicator ? 'flex' : 'none';
    });

    // 삭제 버튼
    condDiv.querySelector('.btn-remove-condition')?.addEventListener('click', () => {
        const container = condDiv.parentElement;
        if (container.querySelectorAll('.condition-row').length > 1) {
            condDiv.remove();
        }
    });
}

// 프리셋 섹션 업데이트 (지표 변경 시)
function updatePresetSection(condDiv) {
    const indicatorKey = condDiv.querySelector('.cond-indicator-select')?.value;
    const presetSelect = condDiv.querySelector('.cond-preset-select');
    if (!presetSelect) return;

    presetSelect.innerHTML = getPresetOptions(indicatorKey);
    renderPresetParams(condDiv);
}

// 프리셋 파라미터 렌더링 (편집 가능한 파라미터 표시)
function renderPresetParams(condDiv) {
    const indicatorKey = condDiv.querySelector('.cond-indicator-select')?.value;
    const presetSelect = condDiv.querySelector('.cond-preset-select');
    const paramsDiv = condDiv.querySelector('.preset-params');
    if (!paramsDiv || !presetSelect) return;

    const presets = INDICATOR_PRESETS[indicatorKey] || [];
    const presetIdx = parseInt(presetSelect.value);
    const preset = presets[presetIdx];

    if (!preset) {
        paramsDiv.innerHTML = '';
        return;
    }

    // 프리셋의 파라미터를 편집 가능하게 표시
    const config = preset.config;
    const mainIndicator = indicatorRegistry?.[config.indicator];
    const compareIndicator = config.compare_indicator ? indicatorRegistry?.[config.compare_indicator] : null;

    let html = '';
    const hasMainParams = mainIndicator && mainIndicator.params && mainIndicator.params.length > 0;
    const hasCompareParams = compareIndicator && compareIndicator.params && compareIndicator.params.length > 0;
    const isSameIndicator = config.indicator === config.compare_indicator;

    // 1. 주 지표 파라미터 표시
    if (hasMainParams) {
        // 동일 지표 비교면 "단기" 라벨 추가
        const labelPrefix = (isSameIndicator && config.compare_type === 'indicator') ? '단기 ' : '';
        html += mainIndicator.params.map(p => `
            <label class="param-label">${labelPrefix}${p.label}
                <input type="number" class="preset-param-input" data-param="${p.key}"
                    value="${config.params?.[p.key] ?? p.default}" min="${p.min || ''}" max="${p.max || ''}" step="any">
            </label>
        `).join('');
    }

    // 2. 고정값 비교: 기준값 입력칸 표시
    if (config.compare_type === 'value' && config.compare_value !== undefined) {
        const thresholdLabel = getThresholdLabel(indicatorKey, config.operator, config.compare_value);
        html += `
            <label class="param-label">${thresholdLabel}
                <input type="number" class="preset-compare-value" data-param="compare_value"
                    value="${config.compare_value}" step="any">
            </label>
        `;
    }

    // 3. 지표 비교: 비교 지표 파라미터 표시
    if (config.compare_type === 'indicator' && hasCompareParams) {
        if (isSameIndicator) {
            // 동일 지표 비교 (예: SMA 20 vs SMA 50): "장기" 라벨로 두 번째 파라미터 표시
            html += compareIndicator.params.map(p => `
                <label class="param-label">장기 ${p.label}
                    <input type="number" class="preset-compare-param-input" data-param="${p.key}"
                        value="${config.compare_params?.[p.key] ?? p.default}" min="${p.min || ''}" max="${p.max || ''}" step="any">
                </label>
            `).join('');
        } else {
            // 다른 지표 비교 (예: PRICE vs SMA): 비교 지표명 + 파라미터
            const indName = compareIndicator.name?.split(' ')[0] || config.compare_indicator;
            html += compareIndicator.params.map(p => `
                <label class="param-label">${indName} ${p.label}
                    <input type="number" class="preset-compare-param-input" data-param="${p.key}"
                        value="${config.compare_params?.[p.key] ?? p.default}" min="${p.min || ''}" max="${p.max || ''}" step="any">
                </label>
            `).join('');
        }
    }

    paramsDiv.innerHTML = html;
}

// 기준값 라벨 생성
function getThresholdLabel(indicator, operator, value) {
    const labels = {
        'RSI': value >= 50 ? '과매수 기준' : '과매도 기준',
        'STOCH': value >= 50 ? '과매수 기준' : '과매도 기준',
        'CCI': value >= 0 ? '과매수 기준' : '과매도 기준',
        'ADX': '추세 기준',
        'MACD': '기준선',
        'SUPERTREND': '방향 기준',
    };
    return labels[indicator] || '기준값';
}

// 직접설정 섹션 업데이트 (지표 변경 시)
function updateManualSection(condDiv) {
    const indicatorKey = condDiv.querySelector('.cond-indicator-select')?.value;
    const indicator = indicatorRegistry?.[indicatorKey];
    if (!indicator) return;

    // 출력값 옵션 업데이트
    const outputSelect = condDiv.querySelector('.manual-section .cond-output[data-side="left"]');
    if (outputSelect) {
        outputSelect.innerHTML = indicator.outputs.map(o =>
            `<option value="${o}">${getOutputLabel(o)}</option>`
        ).join('');
    }

    // 파라미터 업데이트
    const paramsDiv = condDiv.querySelector('.manual-section .cond-params[data-side="left"]');
    if (paramsDiv) {
        paramsDiv.innerHTML = indicator.params.map(p => `
            <label class="param-label">${p.label}
                <input type="number" class="param-input" data-param="${p.key}"
                    value="${p.default}" min="${p.min || ''}" max="${p.max || ''}" step="any">
            </label>
        `).join('');
    }
}

// 지표 파라미터 업데이트 (직접설정 모드 - 오른쪽 비교 지표용)
function updateIndicatorParams(condDiv, side) {
    // 직접설정 모드에서 오른쪽(비교) 지표의 파라미터만 업데이트
    if (side !== 'right') return;

    const select = condDiv.querySelector('.cond-compare-indicator .cond-indicator');
    const paramsDiv = condDiv.querySelector('.cond-compare-indicator .cond-params');
    if (!select || !paramsDiv) return;

    const indicator = indicatorRegistry?.[select.value];
    if (!indicator) {
        paramsDiv.innerHTML = '';
        return;
    }

    paramsDiv.innerHTML = indicator.params.map(p => `
        <label class="param-label">${p.label}
            <input type="number" class="param-input" data-param="${p.key}"
                value="${p.default}" min="${p.min || ''}" max="${p.max || ''}" step="any">
        </label>
    `).join('');
}

// 출력값 한글 매핑
const OUTPUT_LABELS = {
    "value": "값",
    // MACD
    "macd": "MACD선",
    "signal": "시그널선",
    "histogram": "히스토그램",
    // Bollinger Bands
    "upper": "상단밴드",
    "middle": "중간밴드",
    "lower": "하단밴드",
    // Stochastic
    "k": "%K",
    "d": "%D",
    // ADX
    "adx": "ADX",
    "plus_di": "+DI",
    "minus_di": "-DI",
    // Supertrend
    "direction": "방향",
    // Ichimoku
    "tenkan": "전환선",
    "kijun": "기준선",
    "senkou_a": "선행스팬A",
    "senkou_b": "선행스팬B",
    "chikou": "후행스팬",
    // Price
    "open": "시가",
    "high": "고가",
    "low": "저가",
    "close": "종가",
    "volume": "거래량",
};

// 출력값 한글 라벨 가져오기
function getOutputLabel(output) {
    return OUTPUT_LABELS[output] || output;
}

// 지표 출력 업데이트 (직접설정 모드 - 오른쪽 비교 지표용)
function updateIndicatorOutputs(condDiv, side) {
    // 직접설정 모드에서 오른쪽(비교) 지표의 출력 옵션만 업데이트
    if (side !== 'right') return;

    const select = condDiv.querySelector('.cond-compare-indicator .cond-indicator');
    const outputSelect = condDiv.querySelector('.cond-compare-indicator .cond-output');
    if (!select || !outputSelect) return;

    const indicator = indicatorRegistry?.[select.value];
    if (!indicator) return;

    outputSelect.innerHTML = indicator.outputs.map(o =>
        `<option value="${o}">${getOutputLabel(o)}</option>`
    ).join('');
}

// 조건 빌더 리스너 설정
function setupConditionBuilderListeners() {
    // 진입 조건 그룹 추가 버튼
    document.getElementById('btn-add-entry-group')?.addEventListener('click', () => {
        addConditionGroup('entry');
    });

    // 청산 조건 그룹 추가 버튼
    document.getElementById('btn-add-exit-group')?.addEventListener('click', () => {
        addConditionGroup('exit');
    });
}

// 조건 수집 (프리셋/직접설정 모드 둘 다 지원)
function collectConditions(type) {
    const container = document.getElementById(`${type}-condition-groups`);
    if (!container) return { groups: [] };

    const groups = [];

    container.querySelectorAll('.condition-group').forEach(groupDiv => {
        const conditions = [];

        groupDiv.querySelectorAll('.condition-row').forEach(condDiv => {
            const mode = condDiv.dataset.mode || 'preset';

            if (mode === 'preset') {
                // 프리셋 모드: 선택된 프리셋 config 사용 (편집된 파라미터 반영)
                const indicatorKey = condDiv.querySelector('.cond-indicator-select')?.value;
                const presetSelect = condDiv.querySelector('.cond-preset-select');
                const presetIdx = parseInt(presetSelect?.value);
                const presets = INDICATOR_PRESETS[indicatorKey] || [];
                const preset = presets[presetIdx];

                if (preset && preset.config) {
                    const config = { ...preset.config };

                    // 사용자가 편집한 파라미터 적용
                    const editedParams = {};
                    condDiv.querySelectorAll('.preset-param-input').forEach(input => {
                        const key = input.dataset.param;
                        const val = parseFloat(input.value);
                        if (key && !isNaN(val)) editedParams[key] = val;
                    });

                    // params가 있으면 편집된 값으로 덮어쓰기
                    if (Object.keys(editedParams).length > 0) {
                        config.params = { ...config.params, ...editedParams };
                    }

                    // 사용자가 편집한 기준값(compare_value) 적용
                    const compareValueInput = condDiv.querySelector('.preset-compare-value');
                    if (compareValueInput) {
                        const val = parseFloat(compareValueInput.value);
                        if (!isNaN(val)) config.compare_value = val;
                    }

                    // 사용자가 편집한 비교 지표 파라미터 적용
                    const editedCompareParams = {};
                    condDiv.querySelectorAll('.preset-compare-param-input').forEach(input => {
                        const key = input.dataset.param;
                        const val = parseFloat(input.value);
                        if (key && !isNaN(val)) editedCompareParams[key] = val;
                    });
                    if (Object.keys(editedCompareParams).length > 0) {
                        config.compare_params = { ...config.compare_params, ...editedCompareParams };
                    }

                    conditions.push({
                        indicator: config.indicator,
                        output: config.output || 'value',
                        params: config.params || {},
                        operator: config.operator,
                        compare_type: config.compare_type,
                        compare_value: config.compare_value,
                        compare_indicator: config.compare_indicator,
                        compare_output: config.compare_output,
                        compare_params: config.compare_params,
                    });
                }
            } else {
                // 직접설정 모드
                const leftIndicator = condDiv.querySelector('.cond-indicator-select')?.value;
                const leftOutput = condDiv.querySelector('.manual-section .cond-output[data-side="left"]')?.value;
                const leftParams = {};
                condDiv.querySelectorAll('.manual-section .cond-params[data-side="left"] .param-input').forEach(input => {
                    const key = input.dataset.param;
                    const val = parseFloat(input.value);
                    if (key && !isNaN(val)) leftParams[key] = val;
                });

                const operator = condDiv.querySelector('.cond-operator')?.value;
                const compareType = condDiv.querySelector('.cond-compare-type')?.value;

                let compareValue = null;
                let compareIndicator = null;
                let compareOutput = null;
                let compareParams = null;

                if (compareType === 'value') {
                    compareValue = parseFloat(condDiv.querySelector('.cond-compare-value')?.value);
                } else {
                    compareIndicator = condDiv.querySelector('.cond-compare-indicator .cond-indicator')?.value;
                    compareOutput = condDiv.querySelector('.cond-compare-indicator .cond-output')?.value;
                    compareParams = {};
                    condDiv.querySelectorAll('.cond-compare-indicator .param-input').forEach(input => {
                        const key = input.dataset.param;
                        const val = parseFloat(input.value);
                        if (key && !isNaN(val)) compareParams[key] = val;
                    });
                }

                conditions.push({
                    indicator: leftIndicator,
                    output: leftOutput || 'value',
                    params: leftParams,
                    operator: operator,
                    compare_type: compareType,
                    compare_value: compareValue,
                    compare_indicator: compareIndicator,
                    compare_output: compareOutput,
                    compare_params: compareParams,
                });
            }
        });

        if (conditions.length > 0) {
            groups.push({
                conditions: conditions,
                logic: 'AND',
            });
        }
    });

    return { groups };
}

// 커스텀 백테스트 설정 수집
function collectCustomBacktestConfig() {
    // 자동완성으로 선택한 경우 dataset.selectedCode 사용, 아니면 input.value 사용
    const symbolInput = document.getElementById('custom-symbol');
    const symbolCode = symbolInput?.dataset?.selectedCode || symbolInput?.value || 'BTC-USDT';

    return {
        exchange: document.getElementById('custom-exchange')?.value || 'OKX',
        symbol: symbolCode,
        timeframe: document.getElementById('custom-timeframe')?.value || '1D',
        days: parseInt(document.getElementById('custom-days')?.value || '365'),
        initial_capital: parseFloat(document.getElementById('custom-initial-capital')?.value || '10000000'),
        strategy: {
            name: document.getElementById('custom-strategy-name')?.value || '내 전략',
            entry_rules: collectConditions('entry'),
            exit_rules: collectConditions('exit'),
            position_size_pct: parseFloat(document.getElementById('custom-position-size')?.value || '100'),
            stop_loss_pct: parseFloat(document.getElementById('custom-stop-loss')?.value) || null,
            take_profit_pct: parseFloat(document.getElementById('custom-take-profit')?.value) || null,
            commission_pct: parseFloat(document.getElementById('custom-commission')?.value || '0.015'),
        }
    };
}

// 커스텀 백테스트 실행
async function runCustomBacktest() {
    const config = collectCustomBacktestConfig();

    if (!config.exchange || !config.symbol) {
        showToast('거래소와 종목을 선택해주세요.', 'error');
        return;
    }

    if (config.strategy.entry_rules.groups.length === 0) {
        showToast('진입 조건을 최소 1개 이상 설정해주세요.', 'error');
        return;
    }

    if (config.strategy.exit_rules.groups.length === 0) {
        showToast('청산 조건을 최소 1개 이상 설정해주세요.', 'error');
        return;
    }

    // UI 상태 업데이트
    const btn = document.getElementById('btn-custom-run-backtest');
    const loadingEl = document.getElementById('custom-backtest-loading');
    const loadingMsgEl = document.getElementById('custom-backtest-loading-msg');
    const errorEl = document.getElementById('custom-backtest-error');
    const resultEl = document.getElementById('custom-backtest-result');

    const setLoadingMsg = (msg) => {
        if (loadingMsgEl) loadingMsgEl.textContent = msg;
    };

    if (btn) {
        btn.disabled = true;
        btn.textContent = '분석 중...';
        btn.classList.add('btn-loading');
    }
    if (loadingEl) loadingEl.style.display = 'block';
    if (errorEl) errorEl.style.display = 'none';
    if (resultEl) resultEl.style.display = 'none';

    try {
        // 1단계: 시세 데이터 준비
        setLoadingMsg('시세 데이터 준비 중...');

        // Tauri invoke 사용 (fetch 대신)
        const data = await invoke('run_custom_backtest', {
            exchange: config.exchange,
            symbol: config.symbol,
            timeframe: config.timeframe || '1D',
            days: config.days || 365,
            initialCapital: config.initial_capital || 10000000,
            strategy: config.strategy,
        });

        if (data.success) {
            displayCustomBacktestResult(data, config.exchange, config.symbol);
            showToast('백테스트 완료!', 'success');
        } else {
            if (errorEl) {
                errorEl.textContent = data.message || '백테스트 실패';
                errorEl.style.display = 'block';
            }
            showToast(data.message || '백테스트 실패', 'error');
        }
    } catch (e) {
        console.error('커스텀 백테스트 오류:', e);
        if (errorEl) {
            errorEl.textContent = '서버 연결 오류: ' + (e.message || e);
            errorEl.style.display = 'block';
        }
        showToast('서버 연결 오류', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '백테스트 실행';
            btn.classList.remove('btn-loading');
        }
        if (loadingEl) loadingEl.style.display = 'none';
    }
}

// 커스텀 백테스트 결과 표시 (MR/Trend와 동일 형식)
function displayCustomBacktestResult(data, exchange, symbol) {
    const resultEl = document.getElementById('custom-backtest-result');
    if (!resultEl) return;

    resultEl.style.display = 'block';
    const m = data.metrics || {};

    // 화폐 단위 결정
    const currency = getMrCurrency(exchange, symbol);

    // 5카드 업데이트
    const formatAmount = (val) => formatMrAmount(val, currency);

    document.getElementById('custom-stat-net-profit').innerHTML = `${formatAmount(m.net_profit || 0)}<br><small>(${(m.net_profit_pct || 0).toFixed(2)}%)</small>`;
    document.getElementById('custom-stat-trades').textContent = m.total_trades || 0;
    document.getElementById('custom-stat-winrate').textContent = `${(m.win_rate_pct || 0).toFixed(1)}%`;
    document.getElementById('custom-stat-pf').textContent = m.profit_factor >= 999 ? '∞' : (m.profit_factor || 0).toFixed(3);
    document.getElementById('custom-stat-mdd').textContent = `${(m.max_drawdown_pct || 0).toFixed(2)}%`;

    // 캔들 차트
    if (data.candles && data.candles.length > 0) {
        createCustomBacktestChart(data.candles, data.trades || [], exchange, symbol);
    }

    // 수익률 테이블
    renderCustomPerformanceTable(m, currency);

    // 거래 내역 테이블
    renderCustomTradesTable(data.trades || [], currency);
}

// 커스텀 캔들 차트 생성 (MR/Trend와 동일)
function createCustomBacktestChart(candles, trades, exchange, symbol) {
    const container = document.getElementById('custom-chart-container');
    if (!container || typeof LightweightCharts === 'undefined') return;

    // 기존 차트 제거
    if (customBacktestChart) {
        customBacktestChart.remove();
        customBacktestChart = null;
    }

    // 컨테이너 스타일 강제 적용 (무한 확장 방지)
    container.style.width = '100%';
    container.style.maxWidth = '100%';
    container.style.overflow = 'hidden';
    container.style.position = 'relative';

    // 부모 요소 너비 기준으로 차트 너비 계산
    const parentWidth = container.parentElement?.getBoundingClientRect().width || 800;
    const chartWidth = Math.min(Math.max(parentWidth - 40, 300), 1400);

    const chartOptions = {
        width: chartWidth,
        height: 400,
        layout: { background: { color: '#1e1e2f' }, textColor: '#d1d4dc' },
        grid: { vertLines: { color: '#2B2B43' }, horzLines: { color: '#2B2B43' } },
        crosshair: { mode: 1 },
        timeScale: {
            borderColor: '#485c7b',
            timeVisible: true,
            secondsVisible: false,
            fixLeftEdge: true,
            fixRightEdge: true,
            lockVisibleTimeRangeOnResize: true,
            tickMarkFormatter: (time) => {
                const date = new Date(time * 1000);
                const month = date.getMonth() + 1;
                const day = date.getDate();
                return `${month}/${day}`;
            },
        },
        rightPriceScale: { borderColor: '#485c7b' },
        localization: {
            dateFormat: 'yyyy-MM-dd',
            locale: 'ko-KR',
            timeFormatter: (time) => {
                const date = new Date(time * 1000);
                const y = date.getFullYear();
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            },
        },
        handleScale: { axisPressedMouseMove: true },
        handleScroll: { vertTouchDrag: false },
    };

    customBacktestChart = LightweightCharts.createChart(container, chartOptions);

    const candleSeries = customBacktestChart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
    });

    candleSeries.setData(candles);

    // 매수/매도 마커
    const markers = [];
    (trades || []).forEach(t => {
        if (t.timestamp) {
            markers.push({
                time: Math.floor(t.timestamp / 1000),
                position: t.action === 'buy' ? 'belowBar' : 'aboveBar',
                color: t.action === 'buy' ? '#26a69a' : '#ef5350',
                shape: t.action === 'buy' ? 'arrowUp' : 'arrowDown',
                text: t.action === 'buy' ? 'B' : 'S',
            });
        }
    });
    if (markers.length > 0) {
        candleSeries.setMarkers(markers.sort((a, b) => a.time - b.time));
    }

    // 전체 데이터가 화면에 맞게 표시되도록 fitContent 호출
    customBacktestChart.timeScale().fitContent();

    // 렌더링 완료 후 다시 fitContent (확실하게)
    requestAnimationFrame(() => {
        if (customBacktestChart) {
            customBacktestChart.timeScale().fitContent();
        }
    });

    // 리사이즈 핸들러
    const resizeObserver = new ResizeObserver((entries) => {
        if (customBacktestChart && entries[0]) {
            const newWidth = entries[0].contentRect.width;
            if (newWidth > 0 && newWidth < 2000) {
                customBacktestChart.applyOptions({ width: newWidth });
                customBacktestChart.timeScale().fitContent();
            }
        }
    });
    resizeObserver.observe(container);
}

// 커스텀 수익률 테이블 (MR/Trend와 동일 형식)
function renderCustomPerformanceTable(m, currency) {
    const tbody = document.querySelector('#custom-performance-table tbody');
    if (!tbody) return;

    const fmtAmt = (v) => formatMrAmount(v || 0, currency);
    const pnlColor = (v) => (Number(v) || 0) >= 0 ? '#22C55E' : '#EF4444';

    const row = (label, allAmt, allPct, buyAmt, buyPct, sellAmt, sellPct) => {
        const fPct = (v) => v != null ? `<br><span style="font-size:11px;color:${pnlColor(v)}">${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%</span>` : '';
        const cellColor = (v) => pnlColor(v);
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:${cellColor(allAmt)};">${fmtAmt(allAmt)}${fPct(allPct)}</td>
            <td style="text-align:right; color:${cellColor(buyAmt)};">${fmtAmt(buyAmt)}${fPct(buyPct)}</td>
            <td style="text-align:right; color:#6B7280;">${sellAmt != null && sellAmt !== 0 ? fmtAmt(sellAmt) : '—'}${sellPct != null && sellPct !== 0 ? fPct(sellPct) : ''}</td>
        </tr>`;
    };

    const simpleRow = (label, all, buy, sell) => {
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:#D1D5DB;">${all ?? '—'}</td>
            <td style="text-align:right; color:#D1D5DB;">${buy ?? '—'}</td>
            <td style="text-align:right; color:#6B7280;">${sell != null && sell !== 0 ? sell : '—'}</td>
        </tr>`;
    };

    tbody.innerHTML = [
        row('순손익', m.net_profit, m.net_profit_pct, m.buy_net_profit, m.buy_net_profit_pct, m.sell_net_profit, m.sell_net_profit_pct),
        row('총수익', m.gross_profit, m.gross_profit_pct, m.buy_gross_profit, m.buy_gross_profit_pct, m.sell_gross_profit, m.sell_gross_profit_pct),
        row('총손실', m.gross_loss ? -Math.abs(m.gross_loss) : 0, m.gross_loss_pct ? -Math.abs(m.gross_loss_pct) : 0,
            m.buy_gross_loss ? -Math.abs(m.buy_gross_loss) : 0, m.buy_gross_loss_pct ? -Math.abs(m.buy_gross_loss_pct) : 0, null, null),
        row('미실현 손익', m.unrealized_pnl, m.unrealized_pnl_pct, null, null, null, null),
        simpleRow('수익지수', formatProfitFactor(m.profit_factor), formatProfitFactor(m.profit_factor), '—'),
        simpleRow('수수료', fmtAmt(m.commission_paid), fmtAmt(m.buy_commission), '—'),
        simpleRow('기대수익', fmtAmt(m.expected_value), fmtAmt(m.expected_value), '—'),
        simpleRow('총 거래 수', m.total_trades || 0, m.buy_trades || 0, 0),
        simpleRow('수익 거래', m.winning_trades || 0, m.buy_winning || 0, 0),
        simpleRow('손실 거래', m.losing_trades || 0, m.buy_losing || 0, 0),
        simpleRow('승률', `${(m.win_rate_pct || 0).toFixed(1)}%`, `${(m.win_rate_pct || 0).toFixed(1)}%`, '—'),
        simpleRow('최대 연속 승리', m.max_consecutive_wins || 0, m.max_consecutive_wins || 0, 0),
        simpleRow('최대 연속 손실', m.max_consecutive_losses || 0, m.max_consecutive_losses || 0, 0),
    ].join('');
}

// 커스텀 거래 내역 테이블
function renderCustomTradesTable(trades, currency) {
    const tbody = document.querySelector('#custom-trades-table tbody');
    if (!tbody) return;

    const formatAmt = (v) => formatMrAmount(v || 0, currency);

    tbody.innerHTML = trades.map((t, idx) => {
        const typeClass = t.action === 'buy' ? 'trade-buy' : 'trade-sell';
        const pnlClass = t.pnl > 0 ? 'pnl-positive' : (t.pnl < 0 ? 'pnl-negative' : '');
        return `
            <tr>
                <td>${idx + 1}</td>
                <td class="${typeClass}">${t.type || t.action}</td>
                <td>${t.date || '-'}</td>
                <td>${(t.price || 0).toFixed(2)}</td>
                <td>${(t.qty || t.quantity || 0).toFixed(6)}</td>
                <td>${t.tranche || t.reason || '-'}</td>
                <td class="${pnlClass}">${t.pnl != null ? formatAmt(t.pnl) : '-'}</td>
                <td class="${pnlClass}">${t.pnl_pct != null ? t.pnl_pct.toFixed(2) + '%' : '-'}</td>
            </tr>
        `;
    }).join('');
}

// 커스텀 백테스트 버튼 이벤트
document.getElementById('btn-custom-run-backtest')?.addEventListener('click', runCustomBacktest);


// 백테스트 실행 이벤트 핸들러
document.getElementById('btn-trend-run-backtest')?.addEventListener('click', async () => {
    console.log('[Trend 백테스트] 시작');

    const cfg = collectTrendConfig();

    if (!cfg.exchange) cfg.exchange = 'OKX';
    if (!cfg.symbol) cfg.symbol = 'BTC-USDT';

    console.log('[Trend 백테스트] config:', JSON.stringify(cfg).substring(0, 300));

    // 로딩 표시
    const btn = document.getElementById('btn-trend-run-backtest');
    const loadingEl = document.getElementById('trend-backtest-loading');
    const loadingMsgEl = document.getElementById('trend-backtest-loading-msg');
    const errorEl = document.getElementById('trend-backtest-error');
    const resultEl = document.getElementById('trend-backtest-result');

    const setLoadingMsg = (msg) => {
        if (loadingMsgEl) loadingMsgEl.textContent = msg;
    };

    if (btn) {
        btn.disabled = true;
        btn.textContent = '준비 중...';
        btn.classList.add('btn-loading');
    }
    if (loadingEl) loadingEl.style.display = 'block';
    if (errorEl) errorEl.style.display = 'none';
    if (resultEl) resultEl.style.display = 'none';

    try {
        // 1단계: 캔들 프리로드 (시세 데이터 준비)
        setLoadingMsg('시세 데이터 준비 중...');
        console.log('[Trend 백테스트] 프리로드 시작');

        const preloadResult = await invoke('preload_candles', {
            accessToken: auth.accessToken || '',
            exchange: cfg.exchange,
            symbol: cfg.symbol,
            timeframe: cfg.signal_tf,
            days: cfg.days,
        });

        if (!preloadResult.success) {
            throw new Error(preloadResult.message || '시세 데이터 로드 실패');
        }

        console.log('[Trend 백테스트] 프리로드 완료:', preloadResult.candles, '봉,', preloadResult.time_sec, '초');

        // 2단계: 백테스트 실행
        setLoadingMsg('전략 분석 중...');
        if (btn) btn.textContent = '분석 중...';
        console.log('[Trend 백테스트] invoke 호출');

        const result = await invoke('run_trend_backtest', {
            accessToken: auth.accessToken || '',
            exchange: cfg.exchange,
            symbol: cfg.symbol,
            signalTf: cfg.signal_tf,
            exitTf: cfg.exit_tf,
            htfTf: cfg.htf_tf,
            days: cfg.days,
            initialCapital: cfg.initial_capital,
            cashUsePct: cfg.cash_use_pct,
            // 슈퍼트렌드
            stAtrLen: cfg.st_atr_len,
            stFactor: cfg.st_factor,
            // 피라미딩
            usePyramiding: cfg.use_pyramiding,
            maxPyrEntries: cfg.max_pyr_entries,
            pyrHighLen: cfg.pyr_high_len,
            pyrCooldown: cfg.pyr_cooldown,
            pyrRefillAfterSell: cfg.pyr_refill_after_sell,
            pyrWeights: cfg.pyr_weights,
            // 추세전환 전량매도
            useStExit: cfg.use_st_exit,
            // 부분익절 (TP1)
            useTp1: cfg.use_tp1,
            tp1Pct: cfg.tp1_pct,
            tp1SellPct: cfg.tp1_sell_pct,
            // 과매수구간 분할매도
            useSpoSplit: cfg.use_spo_split,
            sellTranches: cfg.sell_tranches,
            maxSellTranches: cfg.max_sell_tranches,
            afterMaxSell: cfg.after_max_sell,
            useProfitGate: cfg.use_profit_gate,
            // 손절
            stopType: cfg.stop_type,
            hardSlPct: cfg.hard_sl_pct,
            atrStopLen: cfg.atr_stop_len,
            atrStopMult: cfg.atr_stop_mult,
        });

        console.log('[Trend 백테스트] 결과:', JSON.stringify(result).substring(0, 300));

        if (result.success) {
            displayTrendBacktestResult(result);
            showToast('백테스트 완료', 'success');
        } else {
            const errorMsg = result.error || result.message || '백테스트 실패';
            if (errorEl) {
                errorEl.style.display = 'block';
                errorEl.innerHTML = `<span style="color:#EF4444;">${errorMsg}</span>`;
            }
            showToast(errorMsg, 'error');
        }
    } catch (error) {
        console.error('[Trend 백테스트] 에러:', error);
        const errorMsg = humanizeMrError(error);
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.innerHTML = `<span style="color:#EF4444;">${errorMsg}</span>`;
        }
        if (resultEl) resultEl.style.display = 'none';
        showToast(errorMsg, 'error');
    } finally {
        // 로딩 해제
        if (btn) {
            btn.disabled = false;
            btn.textContent = '백테스트 실행';
            btn.classList.remove('btn-loading');
        }
        if (loadingEl) loadingEl.style.display = 'none';
    }
});

// 하단 퀵 백테스트 버튼 (백테스트 아코디언 열고 실행)
document.getElementById('btn-trend-backtest-quick')?.addEventListener('click', () => {
    // 백테스트 아코디언 열기
    const backtestSection = document.getElementById('trend-section-backtest');
    if (backtestSection && !backtestSection.classList.contains('open')) {
        backtestSection.classList.add('open');
        const body = backtestSection.querySelector('.mr-accordion-body');
        const icon = backtestSection.querySelector('.mr-accordion-icon');
        if (body) body.style.display = 'block';
        if (icon) icon.textContent = '▼';
    }
    // 백테스트 실행 버튼 클릭
    document.getElementById('btn-trend-run-backtest')?.click();
});

// 종목 자동완성 연결 - initTrendSymbolAutocomplete()에서 처리

function displayTrendBacktestResult(result) {
    // 에러 표시
    const errorEl = document.getElementById('trend-backtest-error');
    const resultEl = document.getElementById('trend-backtest-result');
    if (!resultEl) return;

    if (!result.success) {
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.innerHTML = `<span style="color:#EF4444;">⚠️ ${result.error || result.message || '알 수 없는 오류'}</span>`;
        }
        resultEl.style.display = 'none';
        return;
    }

    if (errorEl) errorEl.style.display = 'none';
    resultEl.style.display = 'block';

    // 화폐 단위 결정 (MR과 동일)
    const exchange = document.getElementById('trend-exchange')?.value || 'OKX';
    const symbolInput = document.getElementById('trend-symbol');
    const symbol = symbolInput?.dataset?.selectedCode || symbolInput?.value || 'BTC-USDT';
    const currency = getMrCurrency(result.exchange || exchange, result.symbol || symbol);

    const m = result.metrics || {};
    const fmtAmt = (v) => formatMrAmount(v, currency);

    // null-safe 헬퍼
    const set = (id, value, color) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = value;
        if (color) el.style.color = color;
    };

    // 색상 헬퍼
    const pnlColor = (v) => (Number(v) || 0) >= 0 ? '#22C55E' : '#EF4444';

    // 메시지
    set('trend-bt-message', result.message || '');

    // ===== 상단 카드 5개 (트레이딩뷰 동일) =====
    // 1. 총 손익
    set('trend-bt-net-profit', fmtAmt(m.net_profit), pnlColor(m.net_profit));
    const netPct = m.net_profit_pct ?? 0;
    set('trend-bt-net-profit-pct', `${netPct > 0 ? '+' : ''}${netPct.toFixed(2)}%`, pnlColor(netPct));

    // 2. 최대 자본 감소
    set('trend-bt-mdd', fmtAmt(m.max_drawdown));
    const mddPct = m.max_drawdown_pct ?? 0;
    set('trend-bt-mdd-pct', `${mddPct.toFixed(2)}%`);

    // 3. 총 거래횟수
    set('trend-bt-total-trades', `${m.total_trades ?? 0}회`);

    // 4. 수익성 거래 (승률 + n/n)
    set('trend-bt-winrate', `${(m.win_rate_pct ?? 0).toFixed(1)}%`, pnlColor((m.win_rate_pct ?? 0) - 50));
    const wt = m.winning_trades ?? 0;
    const lt = m.losing_trades ?? 0;
    set('trend-bt-winrate-detail', `${wt}/${wt + lt}`);

    // 5. 수익지수
    set('trend-bt-profit-factor', formatProfitFactor(m.profit_factor));

    // ===== 수익률 테이블 (전체/매수/매도 3열) =====
    renderTrendPerformanceTable(m, currency, fmtAmt);

    // ===== 자산 추이 차트 (Y축 수익률%) =====
    if (result.equity_curve && result.equity_curve.length > 0) {
        drawTrendBacktestChart(result.equity_curve, m.initial_capital || 10000000, currency);
    }

    // ===== 캔들 차트 (TradingView Lightweight Charts) =====
    if (result.candles && result.candles.length > 0) {
        if (window.trendCandleChartInstance) {
            window.trendCandleChartInstance.remove();
        }
        window.trendCandleChartInstance = createBacktestCandleChart('trend-candle-chart', result.candles, result.trades);
    }

    // ===== 거래 내역 테이블 =====
    renderTrendTradesTable(result.trades || [], currency);
}

function renderTrendPerformanceTable(m, currency, fmtAmt) {
    const tbody = document.getElementById('trend-bt-perf-body');
    if (!tbody) return;

    const pnlColor = (v) => (Number(v) || 0) >= 0 ? '#22C55E' : '#EF4444';

    const row = (label, allAmt, allPct, buyAmt, buyPct, sellAmt, sellPct) => {
        const fPct = (v) => v != null ? `<br><span style="font-size:11px;color:${pnlColor(v)}">${v > 0 ? '+' : ''}${Number(v).toFixed(2)}%</span>` : '';
        const cellColor = (v) => pnlColor(v);
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:${cellColor(allAmt)};">${fmtAmt(allAmt)}${fPct(allPct)}</td>
            <td style="text-align:right; color:${cellColor(buyAmt)};">${fmtAmt(buyAmt)}${fPct(buyPct)}</td>
            <td style="text-align:right; color:#6B7280;">${sellAmt != null && sellAmt !== 0 ? fmtAmt(sellAmt) : '—'}${sellPct != null && sellPct !== 0 ? fPct(sellPct) : ''}</td>
        </tr>`;
    };

    const simpleRow = (label, all, buy, sell) => {
        return `<tr>
            <td style="color:#9CA3AF; font-weight:600;">${label}</td>
            <td style="text-align:right; color:#D1D5DB;">${all ?? '—'}</td>
            <td style="text-align:right; color:#D1D5DB;">${buy ?? '—'}</td>
            <td style="text-align:right; color:#6B7280;">${sell != null && sell !== 0 ? sell : '—'}</td>
        </tr>`;
    };

    tbody.innerHTML = [
        row('순손익', m.net_profit, m.net_profit_pct, m.buy_net_profit, m.buy_net_profit_pct, m.sell_net_profit, m.sell_net_profit_pct),
        row('총수익', m.gross_profit, m.gross_profit_pct, m.buy_gross_profit, m.buy_gross_profit_pct, m.sell_gross_profit, m.sell_gross_profit_pct),
        row('총손실', m.gross_loss ? -Math.abs(m.gross_loss) : 0, m.gross_loss_pct ? -Math.abs(m.gross_loss_pct) : 0,
            m.buy_gross_loss ? -Math.abs(m.buy_gross_loss) : 0, m.buy_gross_loss_pct ? -Math.abs(m.buy_gross_loss_pct) : 0, null, null),
        row('미실현 손익', m.unrealized_pnl, m.unrealized_pnl_pct, null, null, null, null),
        simpleRow('수익지수', formatProfitFactor(m.profit_factor), formatProfitFactor(m.buy_profit_factor), '—'),
        simpleRow('수수료', fmtAmt(m.commission_paid), fmtAmt(m.buy_commission), fmtAmt(m.sell_commission)),
        simpleRow('기대수익', fmtAmt(m.expected_value), fmtAmt(m.buy_expected_value), fmtAmt(m.sell_expected_value)),
    ].join('');
}

function renderTrendTradesTable(trades, currency) {
    const tbody = document.getElementById('trend-bt-trades-body');
    const countEl = document.getElementById('trend-bt-trade-count');
    if (!tbody) return;

    if (countEl) countEl.textContent = `총 ${trades.length}건`;

    if (trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:#6B7280;">거래 내역이 없습니다</td></tr>';
        return;
    }

    tbody.innerHTML = trades.map((t, idx) => {
        // 타입 (서버에서 이미 한글로 옴)
        const isBuy = (t.type === '매수' || t.action === 'buy' || t.action === 'BUY');
        const typeColor = isBuy ? '#3B82F6' : '#EF4444';
        const typeText = t.type || (isBuy ? '매수' : '매도');

        // 날짜 (서버에서 date 필드로 옴)
        const dateStr = t.date || '';

        // 가격
        const priceStr = t.price ? Number(t.price).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '-';

        // 수량
        const qtyStr = t.qty != null ? Number(t.qty).toFixed(6) : (t.quantity != null ? Number(t.quantity).toFixed(6) : '-');

        // 차수 (서버에서 tranche 필드로 이미 한글로 옴)
        const trancheText = t.tranche || '-';

        // 수익금 (금액) — formatMrAmountSigned 사용
        const pnlColor = (t.pnl || 0) >= 0 ? '#22C55E' : '#EF4444';
        const pnlAmtText = (t.pnl != null && !isBuy) ? formatMrAmountSigned(t.pnl, currency) : '-';

        // 수익률 (%)
        const pnlPctText = t.pnl_pct != null && !isBuy ? `${t.pnl_pct > 0 ? '+' : ''}${Number(t.pnl_pct).toFixed(2)}%` : '-';

        // 누적
        const cumColor = (t.cumulative_pnl || 0) >= 0 ? '#22C55E' : '#EF4444';
        const cumText = t.cumulative_pnl != null ? formatMrAmount(t.cumulative_pnl, currency) : '-';

        return `<tr>
            <td style="padding:6px 4px; color:#9CA3AF;">${t.no || idx + 1}</td>
            <td style="padding:6px 4px; color:${typeColor}; font-weight:600;">${typeText}</td>
            <td style="padding:6px 4px; color:#D1D5DB;">${dateStr}</td>
            <td style="padding:6px 4px; text-align:right; color:#E5E7EB;">${priceStr}</td>
            <td style="padding:6px 4px; text-align:right; color:#D1D5DB;">${qtyStr}</td>
            <td style="padding:6px 4px; color:#9CA3AF;">${trancheText}</td>
            <td style="padding:6px 4px; text-align:right; color:${pnlColor};">${pnlAmtText}</td>
            <td style="padding:6px 4px; text-align:right; color:${pnlColor};">${pnlPctText}</td>
            <td style="padding:6px 4px; text-align:right; color:${cumColor};">${cumText}</td>
        </tr>`;
    }).join('');
}

function drawTrendBacktestChart(equityCurve, initialCapital = 10000000, currency = 'USDT') {
    const canvas = document.getElementById('trend-backtest-chart');
    if (!canvas || !window.Chart) return;

    const ctx = canvas.getContext('2d');

    // 기존 차트 제거
    if (window.trendBacktestChart instanceof Chart) {
        window.trendBacktestChart.destroy();
    }

    // 수익률(%) 데이터 생성
    const pctData = equityCurve.map(p => {
        const pct = ((p.equity - initialCapital) / initialCapital) * 100;
        return { x: p.bar_index || 0, y: pct, equity: p.equity };
    });

    // gradient fill (수익=초록, 손실=빨강)
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    const lastPct = pctData.length > 0 ? pctData[pctData.length - 1].y : 0;
    if (lastPct >= 0) {
        gradient.addColorStop(0, 'rgba(34, 197, 94, 0.3)');
        gradient.addColorStop(1, 'rgba(34, 197, 94, 0)');
    } else {
        gradient.addColorStop(0, 'rgba(239, 68, 68, 0.3)');
        gradient.addColorStop(1, 'rgba(239, 68, 68, 0)');
    }

    window.trendBacktestChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: '수익률',
                data: pctData,
                borderColor: lastPct >= 0 ? '#22C55E' : '#EF4444',
                backgroundColor: gradient,
                fill: true,
                tension: 0.1,
                pointRadius: 0,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const pct = context.parsed.y;
                            const equity = context.raw.equity;
                            const pnl = equity - initialCapital;
                            return [
                                `수익률: ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`,
                                `손익: ${formatMrAmountSigned(pnl, currency)}`,
                                `자산: ${formatMrAmount(equity, currency)}`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    display: true,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#6B7280', maxTicksLimit: 10 }
                },
                y: {
                    display: true,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#6B7280',
                        callback: (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
                    }
                }
            }
        }
    });
}

// =====================================================
// 종목검색기 (Phase 7) - TradingView 스타일 칩 필터
// =====================================================

// 필터 정의 (35개 필터 - 프리셋 + 직접입력 + 파라미터 지원)
const FILTER_DEFINITIONS = {
    // ===== 기본정보 (7개) =====
    exchange: {
        label: '거래소',
        type: 'select',
        options: [
            { value: 'KOSPI', label: 'KOSPI' },
            { value: 'KOSDAQ', label: 'KOSDAQ' }
        ]
    },
    sector: {
        label: '업종',
        type: 'select',
        options: [
            { value: '반도체', label: '반도체' }, { value: '자동차', label: '자동차' },
            { value: '은행', label: '은행' }, { value: '제약', label: '제약' },
            { value: '바이오', label: '바이오' }, { value: '화학', label: '화학' },
            { value: '철강', label: '철강' }, { value: '건설', label: '건설' },
            { value: '유통', label: '유통' }, { value: '통신', label: '통신' },
            { value: '미디어', label: '미디어' }, { value: '식품', label: '식품' },
            { value: '전기전자', label: '전기전자' }, { value: '기계', label: '기계' },
            { value: 'IT서비스', label: 'IT서비스' }, { value: '게임', label: '게임' }
        ]
    },
    market_cap: {
        label: '시가총액',
        type: 'range',
        unit: '억원',
        presets: [
            { min: 100000, max: null, label: '초대형 (10조+)' },
            { min: 10000, max: 100000, label: '대형 (1조~10조)' },
            { min: 5000, max: 10000, label: '중형 (5천억~1조)' },
            { min: 1000, max: 5000, label: '소형 (1천억~5천억)' },
            { min: null, max: 1000, label: '초소형 (1천억 미만)' }
        ]
    },
    price: {
        label: '현재가',
        type: 'range',
        unit: '원',
        presets: [
            { min: null, max: 5000, label: '5천원 이하' },
            { min: 5000, max: 10000, label: '5천~1만원' },
            { min: 10000, max: 50000, label: '1만~5만원' },
            { min: 50000, max: 100000, label: '5만~10만원' },
            { min: 100000, max: null, label: '10만원 이상' }
        ]
    },
    volume: {
        label: '거래량',
        type: 'range',
        unit: '주',
        presets: [
            { min: 100000, max: null, label: '10만 이상' },
            { min: 500000, max: null, label: '50만 이상' },
            { min: 1000000, max: null, label: '100만 이상' },
            { min: 5000000, max: null, label: '500만 이상' }
        ]
    },
    foreign_ratio: {
        label: '외국인비율',
        type: 'range',
        unit: '%',
        presets: [
            { min: 30, max: null, label: '30% 이상' },
            { min: 20, max: 30, label: '20~30%' },
            { min: 10, max: 20, label: '10~20%' },
            { min: null, max: 10, label: '10% 미만' }
        ]
    },
    change_pct: {
        label: '등락률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 10, max: null, label: '+10% 이상' },
            { min: 5, max: null, label: '+5% 이상' },
            { min: 3, max: null, label: '+3% 이상' },
            { min: null, max: -3, label: '-3% 이하' },
            { min: null, max: -5, label: '-5% 이하' },
            { min: null, max: -10, label: '-10% 이하' }
        ]
    },

    // ===== 재무지표 (13개) - yfinance 기반 =====
    per: {
        label: 'PER',
        type: 'range',
        unit: '배',
        presets: [
            { min: null, max: 0, label: '적자' },
            { min: 0, max: 10, label: '저PER (0~10)' },
            { min: 10, max: 20, label: '적정 (10~20)' },
            { min: 20, max: 50, label: '고PER (20~50)' },
            { min: 50, max: null, label: '50 이상' }
        ]
    },
    pbr: {
        label: 'PBR',
        type: 'range',
        unit: '배',
        presets: [
            { min: null, max: 0.5, label: '저평가 (0~0.5)' },
            { min: 0.5, max: 1, label: '0.5~1' },
            { min: 1, max: 2, label: '적정 (1~2)' },
            { min: 2, max: 5, label: '2~5' },
            { min: 5, max: null, label: '5 이상' }
        ]
    },
    roe: {
        label: 'ROE',
        type: 'range',
        unit: '%',
        presets: [
            { min: 20, max: null, label: '우량 (20%+)' },
            { min: 15, max: 20, label: '양호 (15~20%)' },
            { min: 10, max: 15, label: '보통 (10~15%)' },
            { min: null, max: 10, label: '10% 미만' }
        ]
    },
    roa: {
        label: 'ROA',
        type: 'range',
        unit: '%',
        presets: [
            { min: 10, max: null, label: '우량 (10%+)' },
            { min: 5, max: 10, label: '양호 (5~10%)' },
            { min: null, max: 5, label: '5% 미만' }
        ]
    },
    operating_margin: {
        label: '영업이익률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 20, max: null, label: '고수익 (20%+)' },
            { min: 10, max: 20, label: '양호 (10~20%)' },
            { min: 5, max: 10, label: '보통 (5~10%)' },
            { min: null, max: 5, label: '저수익 (5% 미만)' }
        ]
    },
    gross_margin: {
        label: '매출총이익률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 50, max: null, label: '고마진 (50%+)' },
            { min: 30, max: 50, label: '양호 (30~50%)' },
            { min: 15, max: 30, label: '보통 (15~30%)' },
            { min: null, max: 15, label: '저마진 (15% 미만)' }
        ]
    },
    profit_margin: {
        label: '순이익률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 15, max: null, label: '고수익 (15%+)' },
            { min: 10, max: 15, label: '양호 (10~15%)' },
            { min: 5, max: 10, label: '보통 (5~10%)' },
            { min: null, max: 5, label: '5% 미만' }
        ]
    },
    debt_ratio: {
        label: '부채비율',
        type: 'range',
        unit: '%',
        presets: [
            { min: null, max: 50, label: '안정 (50% 미만)' },
            { min: 50, max: 100, label: '보통 (50~100%)' },
            { min: 100, max: 200, label: '주의 (100~200%)' },
            { min: 200, max: null, label: '위험 (200%+)' }
        ]
    },
    current_ratio: {
        label: '유동비율',
        type: 'range',
        unit: '배',
        presets: [
            { min: 2, max: null, label: '안정 (2배+)' },
            { min: 1.5, max: 2, label: '양호 (1.5~2배)' },
            { min: 1, max: 1.5, label: '보통 (1~1.5배)' },
            { min: null, max: 1, label: '주의 (1배 미만)' }
        ]
    },
    dividend_yield: {
        label: '배당수익률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 5, max: null, label: '고배당 (5%+)' },
            { min: 3, max: 5, label: '3~5%' },
            { min: 2, max: 3, label: '2~3%' },
            { min: 1, max: 2, label: '1~2%' }
        ]
    },
    revenue_growth: {
        label: '매출성장률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 50, max: null, label: '고성장 (50%+)' },
            { min: 20, max: 50, label: '성장 (20~50%)' },
            { min: 0, max: 20, label: '안정 (0~20%)' },
            { min: null, max: 0, label: '역성장' }
        ]
    },
    earnings_growth: {
        label: '이익성장률',
        type: 'range',
        unit: '%',
        presets: [
            { min: 50, max: null, label: '고성장 (50%+)' },
            { min: 20, max: 50, label: '성장 (20~50%)' },
            { min: 0, max: 20, label: '안정 (0~20%)' },
            { min: null, max: 0, label: '역성장' }
        ]
    },
    eps_growth: {
        label: 'EPS 성장률(컨센서스)',
        type: 'range',
        unit: '%',
        presets: [
            { min: 100, max: null, label: '100%+' },
            { min: 50, max: null, label: '50%+' },
            { min: 20, max: null, label: '20%+' },
            { min: null, max: 0, label: '역성장' }
        ]
    },

    // ===== 기술적지표 (12개) =====
    rsi: {
        label: 'RSI',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 14, unit: '일' }
        ],
        presets: [
            { min: 70, max: null, label: '과매수 (70+)' },
            { min: null, max: 30, label: '과매도 (30-)' },
            { min: 30, max: 70, label: '중립 (30~70)' }
        ]
    },
    sma: {
        label: '이동평균선',
        type: 'sma',
        multiple: true,
        maTypes: ['SMA', 'EMA', 'WMA'],
        conditions: [
            { value: 'above', label: '현재가가 위' },
            { value: 'below', label: '현재가가 아래' },
            { value: 'near', label: '근접 (±2%)' }
        ]
    },
    sma_cross: {
        label: '이평선교차',
        type: 'sma_cross',
        maTypes: ['SMA', 'EMA', 'WMA'],
        conditions: [
            { value: 'golden', label: '골든크로스 (단기 > 장기)' },
            { value: 'dead', label: '데드크로스 (단기 < 장기)' }
        ]
    },
    bollinger: {
        label: '볼린저밴드',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 20, unit: '일' },
            { key: 'mult', label: '승수', default: 2, unit: 'σ' }
        ],
        presets: [
            { value: 'upper', label: '상단 돌파' },
            { value: 'lower', label: '하단 돌파' },
            { value: 'middle', label: '중심선 부근' }
        ]
    },
    macd: {
        label: 'MACD',
        type: 'indicator',
        params: [
            { key: 'fast', label: '빠른선', default: 12, unit: '일' },
            { key: 'slow', label: '느린선', default: 26, unit: '일' },
            { key: 'signal', label: '시그널', default: 9, unit: '일' }
        ],
        presets: [
            { value: 'buy', label: '매수신호 (MACD > Signal)' },
            { value: 'sell', label: '매도신호 (MACD < Signal)' },
            { value: 'above_zero', label: '0선 위' },
            { value: 'below_zero', label: '0선 아래' }
        ]
    },
    stochastic: {
        label: '스토캐스틱',
        type: 'indicator',
        params: [
            { key: 'k_period', label: '%K', default: 14, unit: '일' },
            { key: 'd_period', label: '%D', default: 3, unit: '일' }
        ],
        presets: [
            { min: 80, max: null, label: '과매수 (80+)' },
            { min: null, max: 20, label: '과매도 (20-)' }
        ]
    },
    volume_surge: {
        label: '거래량급증',
        type: 'indicator',
        params: [
            { key: 'period', label: '기준기간', default: 20, unit: '일' }
        ],
        presets: [
            { min: 2, max: null, label: '2배 이상' },
            { min: 5, max: null, label: '5배 이상' },
            { min: 10, max: null, label: '10배 이상' }
        ],
        unit: '배'
    },
    w52_high: {
        label: '52주고가대비',
        type: 'range',
        unit: '%',
        presets: [
            { min: -5, max: 0, label: '신고가 근접 (0~5% 하락)' },
            { min: -10, max: -5, label: '5~10% 하락' },
            { min: -20, max: -10, label: '10~20% 하락' },
            { min: null, max: -20, label: '20%+ 하락' }
        ]
    },
    w52_low: {
        label: '52주저가대비',
        type: 'range',
        unit: '%',
        presets: [
            { min: 0, max: 5, label: '바닥 근접 (0~5% 상승)' },
            { min: 5, max: 10, label: '5~10% 상승' },
            { min: 10, max: 20, label: '10~20% 상승' },
            { min: 20, max: null, label: '20%+ 상승' }
        ]
    },
    atr: {
        label: 'ATR',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 14, unit: '일' }
        ],
        presets: [
            { value: 'high', label: '고변동 (3%+)' },
            { value: 'medium', label: '중변동 (1.5~3%)' },
            { value: 'low', label: '저변동 (1.5% 미만)' }
        ]
    },
    period_return: {
        label: '기간수익률',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: '1m', unit: '', options: [
                { value: '1w', label: '1주' },
                { value: '1m', label: '1개월' },
                { value: '3m', label: '3개월' },
                { value: '6m', label: '6개월' },
                { value: '1y', label: '1년' }
            ]}
        ],
        presets: [
            { min: 30, max: null, label: '+30% 이상' },
            { min: 20, max: 30, label: '+20~30%' },
            { min: 10, max: 20, label: '+10~20%' },
            { min: null, max: -10, label: '-10% 이하' },
            { min: null, max: -20, label: '-20% 이하' }
        ],
        unit: '%'
    }
};

// 재무 지표 — KR/US/ETF 공통 (13개) - yfinance 기반
const COMMON_FINANCIAL_FILTERS = {
    per: { ...FILTER_DEFINITIONS.per, category: 'financial' },
    pbr: { ...FILTER_DEFINITIONS.pbr, category: 'financial' },
    roe: { ...FILTER_DEFINITIONS.roe, category: 'financial' },
    roa: { ...FILTER_DEFINITIONS.roa, category: 'financial' },
    operating_margin: { ...FILTER_DEFINITIONS.operating_margin, category: 'financial' },
    gross_margin: { ...FILTER_DEFINITIONS.gross_margin, category: 'financial' },
    profit_margin: { ...FILTER_DEFINITIONS.profit_margin, category: 'financial' },
    debt_ratio: { ...FILTER_DEFINITIONS.debt_ratio, category: 'financial' },
    current_ratio: { ...FILTER_DEFINITIONS.current_ratio, category: 'financial' },
    dividend_yield: { ...FILTER_DEFINITIONS.dividend_yield, category: 'financial' },
    revenue_growth: { ...FILTER_DEFINITIONS.revenue_growth, category: 'financial' },
    earnings_growth: { ...FILTER_DEFINITIONS.earnings_growth, category: 'financial' },
    eps_growth: { ...FILTER_DEFINITIONS.eps_growth, category: 'financial' },
};

// 재무 지표 — 국내(KR) = 공통
const KR_FINANCIAL_FILTERS = { ...COMMON_FINANCIAL_FILTERS };

// 재무 지표 — 해외(US) = 공통
const US_FINANCIAL_FILTERS = { ...COMMON_FINANCIAL_FILTERS };

// 기술적 지표 — 국내/해외 공통 (16개: 기존 11 + 신규 5)
const COMMON_TECHNICAL_FILTERS = {
    // 기존 11개
    rsi: { ...FILTER_DEFINITIONS.rsi, category: 'technical' },
    sma: { ...FILTER_DEFINITIONS.sma, category: 'technical' },
    sma_cross: { ...FILTER_DEFINITIONS.sma_cross, category: 'technical' },
    bollinger: { ...FILTER_DEFINITIONS.bollinger, category: 'technical' },
    macd: { ...FILTER_DEFINITIONS.macd, category: 'technical' },
    stochastic: { ...FILTER_DEFINITIONS.stochastic, category: 'technical' },
    volume_surge: { ...FILTER_DEFINITIONS.volume_surge, category: 'technical' },
    w52_high: { ...FILTER_DEFINITIONS.w52_high, category: 'technical' },
    w52_low: { ...FILTER_DEFINITIONS.w52_low, category: 'technical' },
    atr: { ...FILTER_DEFINITIONS.atr, category: 'technical' },
    period_return: { ...FILTER_DEFINITIONS.period_return, category: 'technical' },
    // 신규 5개
    ichimoku: {
        label: '일목균형표',
        category: 'technical',
        type: 'indicator',
        params: [
            { key: 'tenkan', label: '전환선', default: 9, unit: '일' },
            { key: 'kijun', label: '기준선', default: 26, unit: '일' },
            { key: 'senkou_b', label: '선행스팬B', default: 52, unit: '일' }
        ],
        presets: [
            { value: 'above_cloud', label: '구름 위 (상승)' },
            { value: 'below_cloud', label: '구름 아래 (하락)' },
            { value: 'in_cloud', label: '구름 내 (횡보)' },
            { value: 'tenkan_above_kijun', label: '전환선 > 기준선' },
            { value: 'tenkan_below_kijun', label: '전환선 < 기준선' }
        ]
    },
    stoch_rsi: {
        label: 'Stoch RSI',
        category: 'technical',
        type: 'indicator',
        params: [
            { key: 'rsi_period', label: 'RSI기간', default: 14, unit: '일' },
            { key: 'stoch_period', label: 'Stoch기간', default: 14, unit: '일' },
            { key: 'k_period', label: '%K', default: 3, unit: '일' },
            { key: 'd_period', label: '%D', default: 3, unit: '일' }
        ],
        presets: [
            { min: null, max: 20, label: '과매도 (<20)' },
            { min: 80, max: null, label: '과매수 (>80)' }
        ]
    },
    adx: {
        label: 'ADX',
        category: 'technical',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 14, unit: '일' }
        ],
        presets: [
            { min: 25, max: null, label: '강한 추세 (25+)' },
            { min: 40, max: null, label: '매우 강한 추세 (40+)' },
            { min: null, max: 20, label: '약한 추세 (<20)' }
        ]
    },
    cci: {
        label: 'CCI',
        category: 'technical',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 20, unit: '일' }
        ],
        presets: [
            { min: 100, max: null, label: '과매수 (100+)' },
            { min: null, max: -100, label: '과매도 (-100↓)' },
            { min: -100, max: 100, label: '중립 (-100~100)' }
        ]
    },
    williams_r: {
        label: 'Williams %R',
        category: 'technical',
        type: 'indicator',
        params: [
            { key: 'period', label: '기간', default: 14, unit: '일' }
        ],
        presets: [
            { min: -20, max: 0, label: '과매수 (-20↑)' },
            { min: -100, max: -80, label: '과매도 (-80↓)' },
            { min: -80, max: -20, label: '중립' }
        ]
    }
};

// KR (국내) 필터 정의 — 재무 13개 + 기술 16개 전체 적용
const KR_FILTER_DEFINITIONS = {
    // ===== 기본정보 (7개) =====
    exchange: {
        label: '거래소',
        category: 'basic',
        type: 'select',
        options: [
            { value: 'KOSPI', label: 'KOSPI' },
            { value: 'KOSDAQ', label: 'KOSDAQ' }
        ]
    },
    sector: {
        label: '업종',
        category: 'basic',
        type: 'select',
        options: [
            { value: '반도체', label: '반도체' }, { value: '자동차', label: '자동차' },
            { value: '은행', label: '은행' }, { value: '제약', label: '제약' },
            { value: '바이오', label: '바이오' }, { value: '화학', label: '화학' },
            { value: '철강', label: '철강' }, { value: '건설', label: '건설' },
            { value: '유통', label: '유통' }, { value: '통신', label: '통신' },
            { value: '미디어', label: '미디어' }, { value: '식품', label: '식품' },
            { value: '전기전자', label: '전기전자' }, { value: '기계', label: '기계' },
            { value: 'IT서비스', label: 'IT서비스' }, { value: '게임', label: '게임' }
        ]
    },
    market_cap: {
        label: '시가총액',
        category: 'basic',
        type: 'range',
        unit: '억원',
        presets: [
            { min: 100000, max: null, label: '초대형 (10조+)' },
            { min: 10000, max: 100000, label: '대형 (1조~10조)' },
            { min: 5000, max: 10000, label: '중형 (5천억~1조)' },
            { min: 1000, max: 5000, label: '소형 (1천억~5천억)' },
            { min: null, max: 1000, label: '초소형 (1천억 미만)' }
        ]
    },
    price: {
        label: '현재가',
        category: 'basic',
        type: 'range',
        unit: '원',
        presets: [
            { min: null, max: 5000, label: '5천원 이하' },
            { min: 5000, max: 10000, label: '5천~1만원' },
            { min: 10000, max: 50000, label: '1만~5만원' },
            { min: 50000, max: 100000, label: '5만~10만원' },
            { min: 100000, max: null, label: '10만원 이상' }
        ]
    },
    volume: {
        label: '거래량',
        category: 'basic',
        type: 'range',
        unit: '주',
        presets: [
            { min: 100000, max: null, label: '10만 이상' },
            { min: 500000, max: null, label: '50만 이상' },
            { min: 1000000, max: null, label: '100만 이상' },
            { min: 5000000, max: null, label: '500만 이상' }
        ]
    },
    foreign_ratio: {
        label: '외국인비율',
        category: 'basic',
        type: 'range',
        unit: '%',
        presets: [
            { min: 30, max: null, label: '30% 이상' },
            { min: 20, max: 30, label: '20~30%' },
            { min: 10, max: 20, label: '10~20%' },
            { min: null, max: 10, label: '10% 미만' }
        ]
    },
    change_pct: {
        label: '등락률',
        category: 'basic',
        type: 'range',
        unit: '%',
        presets: [
            { min: 10, max: null, label: '+10% 이상' },
            { min: 5, max: null, label: '+5% 이상' },
            { min: 3, max: null, label: '+3% 이상' },
            { min: null, max: -3, label: '-3% 이하' },
            { min: null, max: -5, label: '-5% 이하' },
            { min: null, max: -10, label: '-10% 이하' }
        ]
    },
    // ===== 재무 지표 (13개) =====
    ...KR_FINANCIAL_FILTERS,
    // ===== 기술적 지표 (16개) =====
    ...COMMON_TECHNICAL_FILTERS
};

// US (해외) 필터 정의
const US_FILTER_DEFINITIONS = {
    sector: {
        label: '섹터',
        category: 'basic',
        type: 'select',
        options: [
            { value: 'Technology', label: 'Technology' },
            { value: 'Healthcare', label: 'Healthcare' },
            { value: 'Financial', label: 'Financial' },
            { value: 'Consumer Cyclical', label: 'Consumer Cyclical' },
            { value: 'Consumer Defensive', label: 'Consumer Defensive' },
            { value: 'Energy', label: 'Energy' },
            { value: 'Industrials', label: 'Industrials' },
            { value: 'Communication Services', label: 'Communication' },
            { value: 'Utilities', label: 'Utilities' },
            { value: 'Real Estate', label: 'Real Estate' },
            { value: 'Basic Materials', label: 'Materials' }
        ]
    },
    market_cap: {
        label: '시가총액',
        category: 'basic',
        type: 'range',
        unit: 'B$',
        presets: [
            { min: 200, max: null, label: 'Mega ($200B+)' },
            { min: 10, max: 200, label: 'Large ($10~200B)' },
            { min: 2, max: 10, label: 'Mid ($2~10B)' },
            { min: null, max: 2, label: 'Small (~$2B)' }
        ]
    },
    price: {
        label: '현재가',
        category: 'basic',
        type: 'range',
        unit: '$',
        presets: [
            { min: 100, max: null, label: '$100+' },
            { min: 50, max: 100, label: '$50~100' },
            { min: 10, max: 50, label: '$10~50' },
            { min: null, max: 10, label: '~$10' }
        ]
    },
    change_pct: {
        label: '등락률',
        category: 'basic',
        type: 'range',
        unit: '%',
        presets: [
            { min: 5, max: null, label: '+5% 이상' },
            { min: 3, max: null, label: '+3% 이상' },
            { min: null, max: -3, label: '-3% 이하' },
            { min: null, max: -5, label: '-5% 이하' }
        ]
    },
    volume: {
        label: '거래량',
        category: 'basic',
        type: 'range',
        unit: '',
        presets: [
            { min: 10000000, max: null, label: '10M+' },
            { min: 5000000, max: null, label: '5M+' },
            { min: 1000000, max: null, label: '1M+' }
        ]
    },
    per: {
        label: 'P/E',
        category: 'financial',
        type: 'range',
        unit: '',
        presets: [
            { min: 0, max: 15, label: 'Value (<15)' },
            { min: 15, max: 25, label: 'Fair (15~25)' },
            { min: 30, max: null, label: 'Growth (>30)' }
        ]
    },
    dividend_yield: {
        label: '배당수익률',
        category: 'financial',
        type: 'range',
        unit: '%',
        presets: [
            { min: 4, max: null, label: '4%+' },
            { min: 2, max: null, label: '2%+' },
            { min: 1, max: null, label: '1%+' }
        ]
    },
    // 재무 지표 — US는 Finviz 스크리너에서 제공 안 함
    ...US_FINANCIAL_FILTERS,
    // 기술적 지표 (16개)
    ...COMMON_TECHNICAL_FILTERS
};

// ETF 필터 정의
const ETF_FILTER_DEFINITIONS = {
    category: {
        label: '카테고리',
        category: 'basic',
        type: 'select',
        options: [
            { value: '인덱스', label: '인덱스' },
            { value: '해외', label: '해외' },
            { value: '섹터', label: '섹터' },
            { value: '레버리지/인버스', label: '레버리지/인버스' },
            { value: '채권', label: '채권' },
            { value: '원자재', label: '원자재' },
            { value: '통화', label: '통화' },
            { value: '테마', label: '테마' },
            { value: '기타', label: '기타' }
        ]
    },
    issuer: {
        label: '운용사',
        category: 'basic',
        type: 'select',
        options: [
            { value: '삼성자산운용', label: 'KODEX (삼성)' },
            { value: '미래에셋자산운용', label: 'TIGER (미래에셋)' },
            { value: 'KB자산운용', label: 'KBSTAR (KB)' },
            { value: '한국투자신탁운용', label: 'ACE (한투)' },
            { value: '한화자산운용', label: 'ARIRANG (한화)' },
            { value: '신한자산운용', label: 'SOL (신한)' },
            { value: 'NH-Amundi자산운용', label: 'HANARO (NH)' },
            { value: '키움투자자산운용', label: 'KOSEF (키움)' }
        ]
    },
    nav: {
        label: '순자산',
        category: 'basic',
        type: 'range',
        unit: '억원',
        presets: [
            { min: 10000, max: null, label: '1조 이상' },
            { min: 5000, max: null, label: '5천억 이상' },
            { min: 1000, max: null, label: '1천억 이상' },
            { min: null, max: 1000, label: '1천억 미만' }
        ]
    },
    price: {
        label: '현재가',
        category: 'basic',
        type: 'range',
        unit: '원',
        presets: [
            { min: 50000, max: null, label: '5만원+' },
            { min: 10000, max: 50000, label: '1~5만원' },
            { min: null, max: 10000, label: '1만원 미만' }
        ]
    },
    change_pct: {
        label: '등락률',
        category: 'basic',
        type: 'range',
        unit: '%',
        presets: [
            { min: 3, max: null, label: '+3% 이상' },
            { min: 1, max: null, label: '+1% 이상' },
            { min: null, max: -1, label: '-1% 이하' },
            { min: null, max: -3, label: '-3% 이하' }
        ]
    },
    volume: {
        label: '거래량',
        category: 'basic',
        type: 'range',
        unit: '',
        presets: [
            { min: 1000000, max: null, label: '100만+' },
            { min: 500000, max: null, label: '50만+' },
            { min: 100000, max: null, label: '10만+' }
        ]
    },
    // 기술적 지표 (16개 — 국내와 동일)
    ...COMMON_TECHNICAL_FILTERS
};

// 시장별 필터 정의 반환
function getFilterDefinitions(market) {
    if (market === 'us') return US_FILTER_DEFINITIONS;
    if (market === 'etf') return ETF_FILTER_DEFINITIONS;
    return KR_FILTER_DEFINITIONS;  // 국내: 재무 13개 + 기술 16개
}

let screenerState = {
    market: 'kr',
    sort: 'market_cap',
    order: 'desc',
    page: 1,
    perPage: 50,
    total: 0,
    activeFilters: {},      // { filterKey: { value, label } }
    selectedStock: null,    // 상세 패널용
    hasSearched: false      // 검색 실행 여부 (필터 적용 전에는 빈 상태)
};

async function loadScreener() {
    const restrictionEl = document.getElementById('screener-restriction');
    const contentEl = document.getElementById('screener-content');

    // Pro 이상 또는 admin 체크
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        if (restrictionEl) restrictionEl.style.display = 'flex';
        if (contentEl) contentEl.style.display = 'none';
        return;
    }
    if (restrictionEl) restrictionEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';

    // 이벤트 바인딩 (최초 1회)
    initScreenerEvents();

    // 통합 검색 초기화 (Phase 11)
    initUnifiedSearch();

    // 초기 상태: 빈 화면 표시 (자동 검색 제거)
    screenerState.hasSearched = false;
    showScreenerEmptyState();
}

// 빈 상태 표시
function showScreenerEmptyState() {
    const emptyState = document.getElementById('screener-empty-state');
    const table = document.getElementById('screener-table');
    const pagination = document.getElementById('screener-pagination');
    const countEl = document.getElementById('screener-result-count');

    if (emptyState) emptyState.style.display = 'flex';
    if (table) table.style.display = 'none';
    if (pagination) pagination.style.display = 'none';
    if (countEl) countEl.textContent = '';
}

// 결과 상태 표시
function showScreenerResultState() {
    const emptyState = document.getElementById('screener-empty-state');
    const table = document.getElementById('screener-table');
    const pagination = document.getElementById('screener-pagination');

    if (emptyState) emptyState.style.display = 'none';
    if (table) table.style.display = 'table';
    if (pagination) pagination.style.display = 'flex';
}

let screenerEventsInitialized = false;
function initScreenerEvents() {
    if (screenerEventsInitialized) return;
    screenerEventsInitialized = true;

    // 시장 탭 클릭
    document.querySelectorAll('.screener-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.screener-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            screenerState.market = tab.dataset.market;
            screenerState.page = 1;
            // 마켓 전환 시 정렬 키 리셋
            screenerState.sort = tab.dataset.market === 'etf' ? 'nav' : 'market_cap';
            screenerState.order = 'desc';
            screenerState.activeFilters = {};  // 필터도 리셋
            screenerState.hasSearched = false; // 마켓 전환 시 빈 상태로
            updateScreenerFiltersUI(screenerState.market);
            updateChipStates();
            showScreenerEmptyState();
        });
    });

    // 필터 칩 클릭 이벤트
    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            const filterKey = chip.dataset.filter;
            showFilterPopover(filterKey, chip);
        });
    });

    // 검색 버튼
    document.getElementById('btn-screener-search')?.addEventListener('click', () => {
        // 필터가 1개 이상 있어야 검색 실행
        if (Object.keys(screenerState.activeFilters).length === 0) {
            showNotification('필터를 1개 이상 설정해주세요', 'warning');
            return;
        }
        screenerState.page = 1;
        screenerState.hasSearched = true;
        searchScreener();
    });

    // 초기화 버튼
    document.getElementById('btn-screener-reset')?.addEventListener('click', () => {
        screenerState.activeFilters = {};
        screenerState.page = 1;
        screenerState.hasSearched = false;
        updateActiveFiltersUI();
        updateChipStates();
        showScreenerEmptyState();
    });

    // 모두 지우기 버튼
    document.getElementById('btn-clear-all-filters')?.addEventListener('click', () => {
        screenerState.activeFilters = {};
        screenerState.page = 1;
        screenerState.hasSearched = false;
        updateActiveFiltersUI();
        updateChipStates();
        showScreenerEmptyState();
    });

    // 팝오버 닫기 버튼
    document.getElementById('popover-close')?.addEventListener('click', hideFilterPopover);

    // 팝오버 적용 버튼
    document.getElementById('popover-apply')?.addEventListener('click', () => {
        applyPopoverFilter();
        hideFilterPopover();
    });

    // 팝오버 초기화 버튼
    document.getElementById('popover-clear')?.addEventListener('click', () => {
        const popover = document.getElementById('filter-popover');
        const filterKey = popover?.dataset?.currentFilter;
        if (filterKey) {
            removeFilter(filterKey);
            hideFilterPopover();
        }
    });

    // 팝오버 외부 클릭시 닫기
    document.addEventListener('click', (e) => {
        const popover = document.getElementById('filter-popover');
        if (popover && popover.style.display !== 'none') {
            if (!popover.contains(e.target) && !e.target.classList.contains('filter-chip')) {
                hideFilterPopover();
            }
        }
    });

    // 테이블 헤더 정렬
    document.querySelectorAll('#screener-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const sortKey = th.dataset.sort;
            if (screenerState.sort === sortKey) {
                screenerState.order = screenerState.order === 'desc' ? 'asc' : 'desc';
            } else {
                screenerState.sort = sortKey;
                screenerState.order = 'desc';
            }
            screenerState.page = 1;
            updateSortIcons();
            searchScreener();
        });
    });

    // 페이지네이션
    document.getElementById('btn-page-prev')?.addEventListener('click', () => {
        if (screenerState.page > 1) {
            screenerState.page--;
            searchScreener();
        }
    });

    document.getElementById('btn-page-next')?.addEventListener('click', () => {
        const maxPage = Math.ceil(screenerState.total / screenerState.perPage);
        if (screenerState.page < maxPage) {
            screenerState.page++;
            searchScreener();
        }
    });

    // 상세패널 닫기
    document.getElementById('panel-close-btn')?.addEventListener('click', () => {
        hideStockDetailPanel();
    });

    // ===== 프리셋 관리 이벤트 (Stage 3) =====

    // 프리셋 목록 로드
    loadScreenerPresets();

    // 프리셋 저장
    document.getElementById('btn-save-preset')?.addEventListener('click', saveScreenerPreset);

    // 프리셋 불러오기
    document.getElementById('btn-load-preset')?.addEventListener('click', loadSelectedPreset);

    // 프리셋 삭제
    document.getElementById('btn-delete-preset')?.addEventListener('click', deleteSelectedPreset);

    // 프리셋 선택 변경 시 자동 적용
    document.getElementById('preset-select')?.addEventListener('change', (e) => {
        if (e.target.value) {
            loadSelectedPreset();
        }
    });

    // 백테스트 실행 버튼
    document.getElementById('btn-run-backtest')?.addEventListener('click', runBacktestFromScreener);

    // 관심종목 추가 버튼
    document.getElementById('btn-add-to-watchlist')?.addEventListener('click', addToWatchlistFromScreener);
}

// 필터 팝오버 표시 (모든 타입 지원)
function showFilterPopover(filterKey, chipElement) {
    const popover = document.getElementById('filter-popover');
    const titleEl = document.getElementById('popover-title');
    const bodyEl = document.getElementById('popover-body');

    if (!popover || !titleEl || !bodyEl) return;

    const filterDefs = getFilterDefinitions(screenerState.market);
    const filterDef = filterDefs[filterKey];
    if (!filterDef) return;

    // 현재 필터 키 저장
    popover.dataset.currentFilter = filterKey;
    titleEl.textContent = filterDef.label;

    // 현재 값 가져오기
    const currentFilter = screenerState.activeFilters[filterKey];
    const currentMin = currentFilter?.min || '';
    const currentMax = currentFilter?.max || '';
    const currentParams = currentFilter?.params || {};

    let html = '';

    // ===== 타입별 팝오버 렌더링 =====
    if (filterDef.type === 'select') {
        // 단순 선택형
        html = '<div class="popover-options">';
        filterDef.options.forEach(opt => {
            const selected = currentFilter?.value === opt.value ? 'selected' : '';
            html += `<button class="popover-option ${selected}" data-value="${opt.value}">${opt.label}</button>`;
        });
        html += '</div>';

    } else if (filterDef.type === 'compare') {
        // 비교형 (BPS 등)
        html = '<div class="popover-radio-group">';
        filterDef.options.forEach(opt => {
            const checked = currentFilter?.value === opt.value ? 'checked' : '';
            html += `<label class="popover-radio"><input type="radio" name="compare" value="${opt.value}" ${checked}> ${opt.label}</label>`;
        });
        html += '</div>';

    } else if (filterDef.type === 'range') {
        // 범위형: 프리셋 + min/max 입력
        if (filterDef.presets) {
            html += '<div class="popover-presets"><span class="popover-presets-label">빠른 선택</span><div class="popover-preset-btns">';
            filterDef.presets.forEach((preset, idx) => {
                html += `<button class="popover-preset-btn" data-idx="${idx}" data-min="${preset.min ?? ''}" data-max="${preset.max ?? ''}">${preset.label}</button>`;
            });
            html += '</div></div>';
        }
        html += `<div class="popover-range-section"><span class="popover-range-label">직접 입력</span><div class="popover-range">`;
        html += `<input type="number" inputmode="decimal" id="popover-range-min" placeholder="최소" value="${currentMin}">`;
        html += '<span class="range-sep">~</span>';
        html += `<input type="number" inputmode="decimal" id="popover-range-max" placeholder="최대" value="${currentMax}">`;
        html += `<span class="range-unit">${filterDef.unit || ''}</span></div></div>`;

    } else if (filterDef.type === 'indicator') {
        // 지표형: 파라미터 + 프리셋/범위
        if (filterDef.params) {
            html += '<div class="popover-params">';
            filterDef.params.forEach(param => {
                const paramVal = currentParams[param.key] || param.default;
                if (param.options) {
                    // 드롭다운 파라미터 (기간 선택 등)
                    html += `<div class="popover-param"><label>${param.label}:</label><select id="popover-param-${param.key}">`;
                    param.options.forEach(opt => {
                        const sel = paramVal === opt.value ? 'selected' : '';
                        html += `<option value="${opt.value}" ${sel}>${opt.label}</option>`;
                    });
                    html += '</select></div>';
                } else {
                    // 숫자 입력 파라미터
                    html += `<div class="popover-param"><label>${param.label}:</label>`;
                    html += `<input type="number" id="popover-param-${param.key}" value="${paramVal}" style="width:60px;">`;
                    html += `<span class="param-unit">${param.unit || ''}</span></div>`;
                }
            });
            html += '</div>';
        }
        // 프리셋 (value 기반 또는 min/max 기반)
        if (filterDef.presets) {
            html += '<div class="popover-presets"><span class="popover-presets-label">조건</span><div class="popover-preset-btns">';
            filterDef.presets.forEach((preset, idx) => {
                if (preset.value !== undefined) {
                    html += `<button class="popover-preset-btn" data-value="${preset.value}">${preset.label}</button>`;
                } else {
                    html += `<button class="popover-preset-btn" data-idx="${idx}" data-min="${preset.min ?? ''}" data-max="${preset.max ?? ''}">${preset.label}</button>`;
                }
            });
            html += '</div></div>';
        }
        // min/max 범위가 필요한 지표는 직접 입력도 제공
        if (filterDef.presets?.some(p => p.min !== undefined || p.max !== undefined)) {
            html += `<div class="popover-range-section"><span class="popover-range-label">직접 입력</span><div class="popover-range">`;
            html += `<input type="number" inputmode="decimal" id="popover-range-min" placeholder="최소" value="${currentMin}">`;
            html += '<span class="range-sep">~</span>';
            html += `<input type="number" inputmode="decimal" id="popover-range-max" placeholder="최대" value="${currentMax}">`;
            html += `<span class="range-unit">${filterDef.unit || ''}</span></div></div>`;
        }

    } else if (filterDef.type === 'sma') {
        // 이동평균선: 종류 + 기간 + 조건
        const curType = currentParams.maType || 'SMA';
        const curPeriod = currentParams.period || 20;
        const curCond = currentFilter?.value || '';

        html += '<div class="popover-sma">';
        html += '<div class="popover-param"><label>종류:</label><select id="popover-sma-type">';
        filterDef.maTypes.forEach(t => {
            html += `<option value="${t}" ${curType === t ? 'selected' : ''}>${t}</option>`;
        });
        html += '</select></div>';
        html += `<div class="popover-param"><label>기간:</label><input type="number" id="popover-sma-period" value="${curPeriod}" style="width:60px;"><span class="param-unit">일</span></div>`;
        html += '<div class="popover-conditions"><span class="popover-presets-label">조건</span>';
        filterDef.conditions.forEach(c => {
            const checked = curCond === c.value ? 'checked' : '';
            html += `<label class="popover-radio"><input type="radio" name="sma-cond" value="${c.value}" ${checked}> ${c.label}</label>`;
        });
        html += '</div></div>';

    } else if (filterDef.type === 'sma_cross') {
        // 이평선 교차: 단기/장기 + 조건
        const curShortType = currentParams.shortType || 'SMA';
        const curShortPeriod = currentParams.shortPeriod || 20;
        const curLongType = currentParams.longType || 'SMA';
        const curLongPeriod = currentParams.longPeriod || 50;
        const curCond = currentFilter?.value || '';

        html += '<div class="popover-sma-cross">';
        html += '<div class="cross-row"><span class="cross-label">단기:</span>';
        html += '<select id="popover-short-type">';
        filterDef.maTypes.forEach(t => html += `<option value="${t}" ${curShortType === t ? 'selected' : ''}>${t}</option>`);
        html += '</select>';
        html += `<input type="number" id="popover-short-period" value="${curShortPeriod}" style="width:50px;"><span class="param-unit">일</span></div>`;

        html += '<div class="cross-row"><span class="cross-label">장기:</span>';
        html += '<select id="popover-long-type">';
        filterDef.maTypes.forEach(t => html += `<option value="${t}" ${curLongType === t ? 'selected' : ''}>${t}</option>`);
        html += '</select>';
        html += `<input type="number" id="popover-long-period" value="${curLongPeriod}" style="width:50px;"><span class="param-unit">일</span></div>`;

        html += '<div class="popover-conditions"><span class="popover-presets-label">조건</span>';
        filterDef.conditions.forEach(c => {
            const checked = curCond === c.value ? 'checked' : '';
            html += `<label class="popover-radio"><input type="radio" name="cross-cond" value="${c.value}" ${checked}> ${c.label}</label>`;
        });
        html += '</div></div>';
    }

    bodyEl.innerHTML = html;

    // ===== 이벤트 바인딩 =====
    // 프리셋 버튼 클릭 -> min/max 자동 채움
    bodyEl.querySelectorAll('.popover-preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            bodyEl.querySelectorAll('.popover-preset-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            // min/max 있으면 입력칸에 채움
            const minInput = document.getElementById('popover-range-min');
            const maxInput = document.getElementById('popover-range-max');
            if (minInput && btn.dataset.min !== undefined) minInput.value = btn.dataset.min;
            if (maxInput && btn.dataset.max !== undefined) maxInput.value = btn.dataset.max;
        });
    });

    // 단순 옵션 클릭
    bodyEl.querySelectorAll('.popover-option').forEach(opt => {
        opt.addEventListener('click', () => {
            bodyEl.querySelectorAll('.popover-option').forEach(o => o.classList.remove('selected'));
            opt.classList.add('selected');
        });
    });

    // 팝오버 위치 설정
    const chipRect = chipElement.getBoundingClientRect();
    popover.style.display = 'block';
    popover.style.left = `${chipRect.left}px`;
    popover.style.top = `${chipRect.bottom + 8}px`;

    const popoverRect = popover.getBoundingClientRect();
    if (popoverRect.right > window.innerWidth - 10) {
        popover.style.left = `${window.innerWidth - popoverRect.width - 10}px`;
    }
    if (popoverRect.bottom > window.innerHeight - 10) {
        popover.style.top = `${chipRect.top - popoverRect.height - 8}px`;
    }
}

// 팝오버 숨기기
function hideFilterPopover() {
    const popover = document.getElementById('filter-popover');
    if (popover) {
        popover.style.display = 'none';
        popover.dataset.currentFilter = '';
    }
}

// 팝오버에서 필터 적용 (모든 타입 지원)
function applyPopoverFilter() {
    const popover = document.getElementById('filter-popover');
    const filterKey = popover?.dataset?.currentFilter;
    if (!filterKey) return;

    const filterDefs = getFilterDefinitions(screenerState.market);
    const filterDef = filterDefs[filterKey];
    if (!filterDef) return;

    let filterData = { key: filterKey };

    if (filterDef.type === 'select') {
        const selectedOpt = document.querySelector('#popover-body .popover-option.selected');
        if (selectedOpt) {
            filterData.value = selectedOpt.dataset.value;
            filterData.label = selectedOpt.textContent;
            setFilterV2(filterKey, filterData);
        }

    } else if (filterDef.type === 'compare') {
        const selected = document.querySelector('#popover-body input[name="compare"]:checked');
        if (selected) {
            filterData.value = selected.value;
            const labelEl = selected.closest('label');
            filterData.label = labelEl ? labelEl.textContent.trim() : selected.value;
            setFilterV2(filterKey, filterData);
        }

    } else if (filterDef.type === 'range' || (filterDef.type === 'indicator' && filterDef.presets?.some(p => p.min !== undefined))) {
        const minVal = document.getElementById('popover-range-min')?.value;
        const maxVal = document.getElementById('popover-range-max')?.value;

        // 파라미터 수집 (indicator 타입)
        if (filterDef.params) {
            filterData.params = {};
            filterDef.params.forEach(param => {
                const el = document.getElementById(`popover-param-${param.key}`);
                if (el) filterData.params[param.key] = el.tagName === 'SELECT' ? el.value : parseFloat(el.value) || param.default;
            });
        }

        if (minVal || maxVal) {
            filterData.min = minVal ? parseFloat(minVal) : null;
            filterData.max = maxVal ? parseFloat(maxVal) : null;
            // 라벨 생성
            const unit = filterDef.unit || '';
            if (filterData.params?.period) {
                filterData.label = `${filterDef.label}(${filterData.params.period}): ${minVal || ''}~${maxVal || ''}${unit}`;
            } else {
                filterData.label = minVal && maxVal ? `${minVal}~${maxVal}${unit}` : minVal ? `${minVal}${unit}+` : `~${maxVal}${unit}`;
            }
            setFilterV2(filterKey, filterData);
        }

    } else if (filterDef.type === 'indicator' && filterDef.presets?.some(p => p.value !== undefined)) {
        // value 기반 프리셋 (볼린저, MACD, ATR 등)
        const selectedPreset = document.querySelector('#popover-body .popover-preset-btn.selected');
        if (selectedPreset && selectedPreset.dataset.value) {
            filterData.value = selectedPreset.dataset.value;
            filterData.label = selectedPreset.textContent;
            // 파라미터 수집
            if (filterDef.params) {
                filterData.params = {};
                filterDef.params.forEach(param => {
                    const el = document.getElementById(`popover-param-${param.key}`);
                    if (el) filterData.params[param.key] = el.tagName === 'SELECT' ? el.value : parseFloat(el.value) || param.default;
                });
                // 라벨에 파라미터 추가
                const paramStr = Object.entries(filterData.params).map(([k,v]) => v).join(',');
                filterData.label = `${filterDef.label}(${paramStr}): ${selectedPreset.textContent}`;
            }
            setFilterV2(filterKey, filterData);
        }

    } else if (filterDef.type === 'sma') {
        const maType = document.getElementById('popover-sma-type')?.value || 'SMA';
        const period = parseInt(document.getElementById('popover-sma-period')?.value) || 20;
        const condition = document.querySelector('#popover-body input[name="sma-cond"]:checked')?.value;

        if (condition) {
            const condLabel = filterDef.conditions.find(c => c.value === condition)?.label || condition;
            filterData.value = condition;
            filterData.params = { maType, period };
            filterData.label = `${maType}(${period}) ${condLabel.replace('현재가가 ', '')}`;

            // 다중 SMA 지원: 고유 키 생성
            const uniqueKey = `sma_${maType}_${period}`;
            setFilterV2(uniqueKey, filterData);
        }

    } else if (filterDef.type === 'sma_cross') {
        const shortType = document.getElementById('popover-short-type')?.value || 'SMA';
        const shortPeriod = parseInt(document.getElementById('popover-short-period')?.value) || 20;
        const longType = document.getElementById('popover-long-type')?.value || 'SMA';
        const longPeriod = parseInt(document.getElementById('popover-long-period')?.value) || 50;
        const condition = document.querySelector('#popover-body input[name="cross-cond"]:checked')?.value;

        if (condition) {
            const condLabel = condition === 'golden' ? '골든' : '데드';
            filterData.value = condition;
            filterData.params = { shortType, shortPeriod, longType, longPeriod };
            filterData.label = `${shortType}(${shortPeriod})×${longType}(${longPeriod}) ${condLabel}`;
            setFilterV2(filterKey, filterData);
        }
    }

    screenerState.page = 1;
    searchScreener();
}

// 새로운 필터 설정 함수 (V2 - 파라미터 지원)
function setFilterV2(key, filterData) {
    screenerState.activeFilters[key] = filterData;
    updateActiveFiltersUI();
    updateChipStates();
}

// 기존 setFilter를 setFilterV2로 래핑
function setFilter(key, value, label) {
    setFilterV2(key, { key, value, label });
}

// 필터 제거
function removeFilter(key) {
    delete screenerState.activeFilters[key];
    updateActiveFiltersUI();
    updateChipStates();
    screenerState.page = 1;

    // 모든 필터 제거 시 빈 상태로 복귀
    if (Object.keys(screenerState.activeFilters).length === 0) {
        screenerState.hasSearched = false;
        showScreenerEmptyState();
    } else {
        searchScreener();
    }
}

// 활성 필터 UI 업데이트
function updateActiveFiltersUI() {
    const container = document.getElementById('active-filters-chips');
    const clearAllBtn = document.getElementById('btn-clear-all-filters');

    if (!container) return;

    const filters = screenerState.activeFilters;
    const filterKeys = Object.keys(filters);

    if (filterKeys.length === 0) {
        container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">선택된 필터 없음</span>';
        if (clearAllBtn) clearAllBtn.style.display = 'none';
        return;
    }

    if (clearAllBtn) clearAllBtn.style.display = 'block';

    container.innerHTML = filterKeys.map(key => {
        const filter = filters[key];
        // V2 구조: filter.label 우선 사용
        const displayLabel = filter.label || `${key}: ${filter.value || ''}`;
        return `
            <span class="active-filter-chip" data-key="${key}">
                ${displayLabel}
                <span class="chip-remove" onclick="removeFilter('${key}')">&times;</span>
            </span>
        `;
    }).join('');
}

// 칩 상태 업데이트 (활성 필터가 있으면 하이라이트)
function updateChipStates() {
    document.querySelectorAll('.filter-chip').forEach(chip => {
        const filterKey = chip.dataset.filter;

        // 이평선 칩: sma_ 접두사로 시작하는 필터가 있는지 확인
        if (filterKey === 'sma') {
            const hasSmtFilter = Object.keys(screenerState.activeFilters).some(k => k.startsWith('sma_') && k !== 'sma_cross');
            chip.classList.toggle('active', hasSmtFilter);
        } else {
            const hasFilter = screenerState.activeFilters[filterKey];
            chip.classList.toggle('active', !!hasFilter);
        }
    });
}

function updateSortIcons() {
    document.querySelectorAll('#screener-table th.sortable').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (th.dataset.sort === screenerState.sort) {
            th.classList.add('active');
            if (icon) icon.textContent = screenerState.order === 'desc' ? '▼' : '▲';
        } else {
            th.classList.remove('active');
            if (icon) icon.textContent = '';
        }
    });
}

// 필터 수집 (activeFilters 기반 - V2 구조 지원)
function collectScreenerFilters() {
    const filters = {};

    for (const [key, filter] of Object.entries(screenerState.activeFilters)) {
        // SMA 다중 필터 (sma_SMA_20 형식)
        if (key.startsWith('sma_') && key !== 'sma_cross') {
            if (!filters.sma_filters) filters.sma_filters = [];
            filters.sma_filters.push({
                type: filter.params?.maType || 'SMA',
                period: filter.params?.period || 20,
                condition: filter.value
            });
            continue;
        }

        // 이평선 교차
        if (key === 'sma_cross') {
            filters.sma_cross = {
                shortType: filter.params?.shortType || 'SMA',
                shortPeriod: filter.params?.shortPeriod || 20,
                longType: filter.params?.longType || 'SMA',
                longPeriod: filter.params?.longPeriod || 50,
                condition: filter.value
            };
            continue;
        }

        // min/max 범위 필터
        if (filter.min !== undefined || filter.max !== undefined) {
            if (filter.min !== null) filters[`${key}_min`] = filter.min;
            if (filter.max !== null) filters[`${key}_max`] = filter.max;
            // 파라미터도 전송
            if (filter.params) {
                filters[`${key}_params`] = filter.params;
            }
            continue;
        }

        // 파라미터가 있는 지표 필터
        if (filter.params) {
            filters[key] = {
                value: filter.value,
                params: filter.params
            };
            continue;
        }

        // 단순 값 필터
        if (filter.value !== undefined) {
            filters[key] = filter.value;
        }
    }

    return filters;
}

async function searchScreener() {
    // 검색 실행 여부 체크 (필터 없이 첫 진입 시 빈 상태 유지)
    if (!screenerState.hasSearched) {
        showScreenerEmptyState();
        return;
    }

    const tbody = document.getElementById('screener-tbody');
    const countEl = document.getElementById('screener-result-count');

    // 결과 영역 표시
    showScreenerResultState();

    // 시장별 테이블 헤더 업데이트
    updateTableHeader(screenerState.market);

    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">검색 중...</td></tr>';
    }

    try {
        const filters = collectScreenerFilters();

        const data = await invokeWithTimeout('get_screener', {
            accessToken: auth.accessToken || '',
            market: screenerState.market,
            filters: JSON.stringify(filters),
            sort: screenerState.sort,
            order: screenerState.order,
            page: screenerState.page,
            perPage: screenerState.perPage
        }, 30000);

        if (data.message) {
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">${data.message}</td></tr>`;
            }
            if (countEl) countEl.textContent = '결과: 0건';
            return;
        }

        screenerState.total = data.total || 0;
        if (countEl) countEl.textContent = `결과: ${screenerState.total.toLocaleString()}건`;

        renderScreenerTable(data.items || []);
        updatePagination();

    } catch (err) {
        console.error('Screener search error:', err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">오류 발생: ${err.message || err}</td></tr>`;
        }
    }
}

// 시장별 테이블 헤더 업데이트
function updateTableHeader(market) {
    const thead = document.querySelector('#screener-table thead tr');
    if (!thead) return;

    if (market === 'kr') {
        thead.innerHTML = `
            <th data-sort="code" class="sortable">코드 <span class="sort-icon"></span></th>
            <th data-sort="name" class="sortable">종목명 <span class="sort-icon"></span></th>
            <th data-sort="price" class="sortable align-right">현재가 <span class="sort-icon"></span></th>
            <th data-sort="change_pct" class="sortable align-right">등락률 <span class="sort-icon"></span></th>
            <th data-sort="volume" class="sortable align-right">거래량 <span class="sort-icon"></span></th>
            <th data-sort="market_cap" class="sortable align-right active">시총 <span class="sort-icon">▼</span></th>
            <th data-sort="per" class="sortable align-right">PER <span class="sort-icon"></span></th>
            <th data-sort="rsi" class="sortable align-right">RSI <span class="sort-icon"></span></th>
        `;
    } else if (market === 'us') {
        thead.innerHTML = `
            <th data-sort="code" class="sortable">티커 <span class="sort-icon"></span></th>
            <th data-sort="name" class="sortable">종목명 <span class="sort-icon"></span></th>
            <th data-sort="sector" class="sortable">섹터 <span class="sort-icon"></span></th>
            <th data-sort="change_pct" class="sortable align-right">등락률 <span class="sort-icon"></span></th>
            <th data-sort="market_cap" class="sortable align-right active">시총 <span class="sort-icon">▼</span></th>
            <th colspan="3"></th>
        `;
    } else if (market === 'etf') {
        thead.innerHTML = `
            <th data-sort="code" class="sortable">코드 <span class="sort-icon"></span></th>
            <th data-sort="name" class="sortable">종목명 <span class="sort-icon"></span></th>
            <th data-sort="price" class="sortable align-right">현재가 <span class="sort-icon"></span></th>
            <th data-sort="change_pct" class="sortable align-right">등락률 <span class="sort-icon"></span></th>
            <th data-sort="volume" class="sortable align-right">거래량 <span class="sort-icon"></span></th>
            <th data-sort="nav" class="sortable align-right active">순자산 <span class="sort-icon">▼</span></th>
            <th data-sort="issuer" class="sortable">운용사 <span class="sort-icon"></span></th>
            <th data-sort="category" class="sortable">카테고리 <span class="sort-icon"></span></th>
        `;
    }

    // 헤더 정렬 이벤트 재바인딩
    document.querySelectorAll('#screener-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const sortKey = th.dataset.sort;
            if (screenerState.sort === sortKey) {
                screenerState.order = screenerState.order === 'desc' ? 'asc' : 'desc';
            } else {
                screenerState.sort = sortKey;
                screenerState.order = 'desc';
            }
            screenerState.page = 1;
            updateSortIcons();
            searchScreener();
        });
    });
}

// 시장별 필터 UI 전환
function updateScreenerFiltersUI(market) {
    const filtersEl = document.querySelector('.screener-filters-v2');
    const actionsEl = document.querySelector('.filter-actions-v2');
    const chipGroups = document.querySelector('.filter-chip-groups');

    if (!filtersEl) return;

    // 필터 컨테이너는 항상 표시
    filtersEl.style.display = 'block';
    if (actionsEl) actionsEl.style.display = 'flex';

    // 모든 시장: 동적 필터칩 생성 (KR/US/ETF 공통)
    if (chipGroups) {
        const filterDefs = getFilterDefinitions(market);
        const categories = {};

        // 카테고리별 필터 분류
        Object.entries(filterDefs).forEach(([key, def]) => {
            const cat = def.category || 'basic';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push({ key, label: def.label });
        });

        // 카테고리 라벨 매핑
        const catLabels = { basic: '기본', financial: '재무', technical: '기술' };

        // 카테고리 순서 고정: basic → financial → technical
        const catOrder = ['basic', 'financial', 'technical'];
        let html = '';
        catOrder.forEach(cat => {
            const filters = categories[cat];
            if (filters && filters.length > 0) {
                html += `
                    <div class="filter-chip-group">
                        <span class="chip-group-label">${catLabels[cat] || cat}</span>
                        <div class="chip-row">
                            ${filters.map(f => `<button class="filter-chip" data-filter="${f.key}">${f.label}</button>`).join('')}
                        </div>
                    </div>
                `;
            }
        });

        chipGroups.innerHTML = html;
    }

    // 필터 칩 이벤트 재바인딩
    rebindFilterChipEvents();
}

// 필터 칩 이벤트 바인딩 (시장 전환 시 재호출)
function rebindFilterChipEvents() {
    document.querySelectorAll('.filter-chip').forEach(chip => {
        // 기존 이벤트 제거를 위해 새 이벤트로 덮어쓰기
        chip.onclick = (e) => {
            const filterKey = chip.dataset.filter;
            showFilterPopover(filterKey, chip);
        };
    });
}

// 종목 상세 패널 표시 (panel- 접두사 ID 사용)
function showStockDetailPanel(stock) {
    const panel = document.getElementById('stock-detail-panel');
    if (!panel || !stock) return;

    screenerState.selectedStock = stock;

    // 기본 정보
    document.getElementById('panel-stock-name').textContent = stock.name || '-';
    document.getElementById('panel-stock-code').textContent = stock.code || '-';

    // 현재가
    const price = (stock.price || 0).toLocaleString();
    document.getElementById('panel-current-price').textContent = `${price}원`;

    // 등락률
    const changePct = stock.change_pct || 0;
    const changeEl = document.getElementById('panel-price-change');
    const changeStr = changePct > 0 ? `+${changePct.toFixed(2)}%` : `${changePct.toFixed(2)}%`;
    changeEl.textContent = changeStr;
    changeEl.className = 'detail-price-change ' + (changePct > 0 ? 'profit' : changePct < 0 ? 'loss' : '');

    // 기본 정보 그리드
    document.getElementById('panel-market-cap').textContent = stock.market_cap_str || formatMarketCap(stock.market_cap);
    document.getElementById('panel-volume').textContent = formatVolume(stock.volume || 0);
    document.getElementById('panel-w52-high').textContent = stock.high_52w ? stock.high_52w.toLocaleString() + '원' : '-';
    document.getElementById('panel-w52-low').textContent = stock.low_52w ? stock.low_52w.toLocaleString() + '원' : '-';

    // 재무 지표
    document.getElementById('panel-per').textContent = stock.per ? stock.per.toFixed(1) : '-';
    document.getElementById('panel-pbr').textContent = stock.pbr ? stock.pbr.toFixed(2) : '-';
    document.getElementById('panel-roe').textContent = stock.roe ? stock.roe.toFixed(1) + '%' : '-';
    document.getElementById('panel-dividend').textContent = stock.dividend_yield ? stock.dividend_yield.toFixed(2) + '%' : '-';

    // 기술적 지표
    document.getElementById('panel-rsi').textContent = stock.rsi ? stock.rsi.toFixed(0) : '-';
    document.getElementById('panel-macd').textContent = stock.macd_cross === 'buy' ? '매수' : stock.macd_cross === 'sell' ? '매도' : '-';
    document.getElementById('panel-bb').textContent = stock.bb_position === 'upper' ? '상단' : stock.bb_position === 'lower' ? '하단' : stock.bb_position === 'middle' ? '중심' : '-';
    document.getElementById('panel-vol-surge').textContent = stock.volume_surge ? stock.volume_surge.toFixed(1) + '배' : '-';

    // 이평선
    const smaFormat = (pos) => pos === 'above' ? '위' : pos === 'below' ? '아래' : pos === 'near' ? '근접' : '-';
    document.getElementById('panel-sma20').textContent = smaFormat(stock.sma20_position);
    document.getElementById('panel-sma50').textContent = smaFormat(stock.sma50_position);
    document.getElementById('panel-sma200').textContent = smaFormat(stock.sma200_position);
    document.getElementById('panel-sma-cross').textContent = stock.sma_cross === 'golden' ? '골든' : stock.sma_cross === 'dead' ? '데드' : '-';

    // 패널 표시
    panel.style.display = 'block';

    // 모바일에서는 바텀시트처럼 표시
    if (window.innerWidth <= 1024) {
        setTimeout(() => panel.classList.add('show'), 10);
    }
}

// 종목 상세 패널 숨기기
function hideStockDetailPanel() {
    const panel = document.getElementById('stock-detail-panel');
    if (!panel) return;

    if (window.innerWidth <= 1024) {
        panel.classList.remove('show');
        setTimeout(() => panel.style.display = 'none', 300);
    } else {
        panel.style.display = 'none';
    }
    screenerState.selectedStock = null;
}

function renderScreenerTable(items) {
    const tbody = document.getElementById('screener-tbody');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">검색 결과가 없습니다</td></tr>';
        return;
    }

    // 전역에서 접근 가능하도록 저장
    window._screenerItems = items;

    const market = screenerState.market;

    tbody.innerHTML = items.map((item, idx) => {
        const changePct = item.change_pct || 0;
        // 상승=빨강(change-up), 하락=파랑(change-down)
        const changeClass = changePct > 0 ? 'change-up' : changePct < 0 ? 'change-down' : '';
        const changeStr = changePct > 0 ? `+${changePct.toFixed(2)}%` : `${changePct.toFixed(2)}%`;

        if (market === 'us') {
            // US 마켓: 티커, 종목명, 섹터, 등락률, 시총
            const marketCap = item.market_cap_str || '-';
            return `
                <tr onclick="onScreenerRowClick(${idx})" style="cursor:pointer;">
                    <td class="code-cell">${item.code || '-'}</td>
                    <td class="name-cell">${item.name || '-'}</td>
                    <td>${item.sector || '-'}</td>
                    <td class="change-cell ${changeClass}">${changeStr}</td>
                    <td class="cap-cell">${marketCap}</td>
                    <td colspan="3"></td>
                </tr>
            `;
        } else if (market === 'etf') {
            // ETF 마켓: 코드, 종목명, 현재가, 등락률, 거래량, 순자산, 운용사, 카테고리
            const price = (item.price || 0).toLocaleString('ko-KR', { maximumFractionDigits: 0 });
            const volume = formatVolume(item.volume || 0);
            const nav = item.nav_str || '-';
            return `
                <tr onclick="onScreenerRowClick(${idx})" style="cursor:pointer;">
                    <td class="code-cell">${item.code || '-'}</td>
                    <td class="name-cell">${item.name || '-'}</td>
                    <td class="price-cell">${price}</td>
                    <td class="change-cell ${changeClass}">${changeStr}</td>
                    <td class="volume-cell">${volume}</td>
                    <td class="cap-cell">${nav}</td>
                    <td>${item.issuer || '-'}</td>
                    <td>${item.category || '-'}</td>
                </tr>
            `;
        } else {
            // KR 마켓 (기본): 코드, 종목명, 현재가, 등락률, 거래량, 시총, PER, RSI
            const price = (item.price || 0).toLocaleString('ko-KR', { maximumFractionDigits: 0 });
            const volume = formatVolume(item.volume || 0);
            const marketCap = item.market_cap_str || formatMarketCap(item.market_cap || 0);
            const per = item.per != null ? item.per.toFixed(1) : '-';
            const rsi = item.rsi != null ? item.rsi.toFixed(0) : '-';
            const rsiClass = item.rsi >= 70 ? 'change-down' : item.rsi <= 30 ? 'change-up' : '';

            return `
                <tr onclick="onScreenerRowClick(${idx})" style="cursor:pointer;">
                    <td class="code-cell">${item.code || '-'}</td>
                    <td class="name-cell">${item.name || '-'}</td>
                    <td class="price-cell">${price}</td>
                    <td class="change-cell ${changeClass}">${changeStr}</td>
                    <td class="volume-cell">${volume}</td>
                    <td class="cap-cell">${marketCap}</td>
                    <td class="num-cell">${per}</td>
                    <td class="num-cell ${rsiClass}">${rsi}</td>
                </tr>
            `;
        }
    }).join('');
}

// 테이블 행 클릭 핸들러 - 상세 모달 열기 (Phase 8-3)
function onScreenerRowClick(idx) {
    const items = window._screenerItems;
    if (!items || !items[idx]) return;

    const stock = items[idx];

    // 스크리너 상태 저장 (뒤로가기용)
    const screenerSection = document.querySelector('.page[data-page="screener"]');
    window._screenerState = {
        ...screenerState,
        scrollTop: screenerSection ? screenerSection.scrollTop : 0,
        fromScreener: true
    };

    // 마켓에 따른 exchange 결정
    let exchange = 'kis_kr';
    if (screenerState.market === 'us') {
        exchange = 'kis_us';
    } else if (screenerState.market === 'etf') {
        exchange = 'etf';  // ETF 전용 exchange
    }

    // 종목 상세 모달 열기
    openStockDetail(stock.code, exchange);

    // 뒤로가기 버튼 표시
    const backBtn = document.getElementById('stock-detail-back');
    if (backBtn) backBtn.style.display = 'flex';
}

// window에 onScreenerRowClick 노출 (인라인 onclick에서 사용)
window.onScreenerRowClick = onScreenerRowClick;

function formatMarketCap(cap) {
    if (!cap || cap <= 0) return '-';
    if (cap >= 1000000000000) return (cap / 1000000000000).toFixed(1) + '조';
    if (cap >= 100000000) return (cap / 100000000).toFixed(0) + '억';
    return cap.toLocaleString();
}

function updatePagination() {
    const maxPage = Math.ceil(screenerState.total / screenerState.perPage) || 1;
    const pageInfo = document.getElementById('screener-page-info');
    const prevBtn = document.getElementById('btn-page-prev');
    const nextBtn = document.getElementById('btn-page-next');

    if (pageInfo) pageInfo.textContent = `${screenerState.page} / ${maxPage}`;
    if (prevBtn) prevBtn.disabled = screenerState.page <= 1;
    if (nextBtn) nextBtn.disabled = screenerState.page >= maxPage;
}

// =====================================================
// 스크리너 프리셋 관리 (Phase 7 Stage 3)
// =====================================================

let screenerPresets = [];

async function loadScreenerPresets() {
    const select = document.getElementById('preset-select');
    if (!select) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/screener/presets?market=${screenerState.market}`, {
            credentials: 'include'
        });
        const data = await response.json();

        if (data.success && data.presets) {
            screenerPresets = data.presets;
            renderPresetSelect();
        }
    } catch (error) {
        console.error('[Screener] Failed to load presets:', error);
    }
}

function renderPresetSelect() {
    const select = document.getElementById('preset-select');
    if (!select) return;

    select.innerHTML = '<option value="">프리셋 선택...</option>';
    screenerPresets.forEach(preset => {
        const option = document.createElement('option');
        option.value = preset.id;
        option.textContent = preset.is_default ? `★ ${preset.name}` : preset.name;
        select.appendChild(option);
    });
}

async function saveScreenerPreset() {
    const nameInput = document.getElementById('preset-name-input');
    const name = nameInput?.value?.trim();

    if (!name) {
        showNotification('프리셋 이름을 입력하세요', 'warning');
        nameInput?.focus();
        return;
    }

    // 현재 필터 수집
    const filters = collectScreenerFilters();

    try {
        const response = await fetch(`${API_BASE_URL}/api/screener/presets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                name,
                market: screenerState.market,
                filters,
                sort_by: screenerState.sort,
                sort_order: screenerState.order
            })
        });

        const data = await response.json();
        if (data.success) {
            showNotification(`프리셋 "${name}" 저장 완료`, 'success');
            nameInput.value = '';
            await loadScreenerPresets();
        } else {
            showNotification(data.detail || '저장 실패', 'error');
        }
    } catch (error) {
        console.error('[Screener] Failed to save preset:', error);
        showNotification('프리셋 저장 실패', 'error');
    }
}

function loadSelectedPreset() {
    const select = document.getElementById('preset-select');
    const presetId = select?.value;

    if (!presetId) {
        showNotification('프리셋을 선택하세요', 'warning');
        return;
    }

    const preset = screenerPresets.find(p => p.id == presetId);
    if (!preset) return;

    // 필터 적용
    screenerState.activeFilters = {};

    if (preset.filters && typeof preset.filters === 'object') {
        Object.entries(preset.filters).forEach(([key, value]) => {
            if (value && (value.min != null || value.max != null || value.value != null || value.condition != null)) {
                // V2 포맷 또는 레거시 포맷 모두 처리
                const label = generateFilterLabel(key, value);
                screenerState.activeFilters[key] = { ...value, label };
            }
        });
    }

    // 정렬 적용
    if (preset.sort_by) screenerState.sort = preset.sort_by;
    if (preset.sort_order) screenerState.order = preset.sort_order;

    // UI 업데이트
    updateActiveFiltersUI();
    updateChipStates();
    updateSortIcons();

    // 검색 실행 (프리셋 선택은 자동 검색)
    screenerState.page = 1;
    screenerState.hasSearched = true;
    searchScreener();

    showNotification(`프리셋 "${preset.name}" 적용`, 'success');
}

async function deleteSelectedPreset() {
    const select = document.getElementById('preset-select');
    const presetId = select?.value;

    if (!presetId) {
        showNotification('삭제할 프리셋을 선택하세요', 'warning');
        return;
    }

    const preset = screenerPresets.find(p => p.id == presetId);
    if (!confirm(`프리셋 "${preset?.name}"을(를) 삭제하시겠습니까?`)) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/screener/presets/${presetId}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await response.json();
        if (data.success) {
            showNotification('프리셋 삭제 완료', 'success');
            await loadScreenerPresets();
        } else {
            showNotification(data.detail || '삭제 실패', 'error');
        }
    } catch (error) {
        console.error('[Screener] Failed to delete preset:', error);
        showNotification('프리셋 삭제 실패', 'error');
    }
}

function generateFilterLabel(key, value) {
    const filterDefs = getFilterDefinitions(screenerState.market);
    const def = filterDefs[key];
    if (!def) return key;

    if (value.label) return value.label;

    if (value.min != null && value.max != null) {
        return `${def.label}: ${value.min}~${value.max}`;
    } else if (value.min != null) {
        return `${def.label}: ${value.min}+`;
    } else if (value.max != null) {
        return `${def.label}: ~${value.max}`;
    } else if (value.value) {
        return `${def.label}: ${value.value}`;
    } else if (value.condition) {
        return `${def.label}: ${value.condition}`;
    }

    return def.label;
}

// 전략 연계: 백테스트 실행
function runBacktestFromScreener() {
    const stock = screenerState.selectedStock;
    if (!stock) {
        showNotification('종목을 먼저 선택하세요', 'warning');
        return;
    }

    // KIS_KR 거래소로 심볼 설정
    const exchange = stock.exchange === 'KOSDAQ' ? 'KIS_KR' : 'KIS_KR';
    const symbol = stock.code;

    // 백테스트 탭으로 이동하고 심볼 설정
    navigateTo('strategy-test');

    // 약간의 지연 후 심볼 입력
    setTimeout(() => {
        const exchangeSelect = document.getElementById('bt-exchange');
        const symbolInput = document.getElementById('bt-symbol');

        if (exchangeSelect) exchangeSelect.value = exchange;
        if (symbolInput) symbolInput.value = symbol;

        showNotification(`${stock.name} (${symbol}) 백테스트 준비 완료`, 'success');
    }, 300);
}

// 관심종목 추가 (추후 구현)
function addToWatchlistFromScreener() {
    const stock = screenerState.selectedStock;
    if (!stock) {
        showNotification('종목을 먼저 선택하세요', 'warning');
        return;
    }

    // TODO: 관심종목 기능 연동
    showNotification(`${stock.name} 관심종목 기능은 준비중입니다`, 'info');
}

// =====================================================
// Initialize App
// =====================================================
(async () => {
    console.log('BBooster PC App 시작');
    console.log('API 서버:', API_BASE_URL);

    const isAuthenticated = await initAuth();

    if (isAuthenticated) {
        checkServerConnection();
    }

    // 자동완성 초기화
    initAllAutocompletes();
    initPremiumStrategyAutocomplete();
})();

// Periodic status update
setInterval(() => {
    if (isConnected) {
        updateServerStatus(true);
    }
}, 5000);

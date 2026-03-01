// =====================================================
// BBooster API Utility
// Direct HTTP fetch for API calls (replacing Tauri invoke wrappers)
// =====================================================

import { API_BASE_URL } from './config.js';

const DEFAULT_TIMEOUT = 120000; // 120초 (Tauri와 동일)

/**
 * Fetch with timeout support
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        return response;
    } finally {
        clearTimeout(timeout);
    }
}

/**
 * GET request
 */
export async function apiGet(path, token = null, timeoutMs = DEFAULT_TIMEOUT) {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetchWithTimeout(
        `${API_BASE_URL}${path}`,
        { method: 'GET', headers },
        timeoutMs
    );

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API ${response.status}: ${errorText}`);
    }

    return response.json();
}

/**
 * POST request
 */
export async function apiPost(path, body = {}, token = null, timeoutMs = DEFAULT_TIMEOUT) {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetchWithTimeout(
        `${API_BASE_URL}${path}`,
        {
            method: 'POST',
            headers,
            body: JSON.stringify(body)
        },
        timeoutMs
    );

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API ${response.status}: ${errorText}`);
    }

    return response.json();
}

/**
 * PUT request
 */
export async function apiPut(path, body = {}, token = null, timeoutMs = DEFAULT_TIMEOUT) {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetchWithTimeout(
        `${API_BASE_URL}${path}`,
        {
            method: 'PUT',
            headers,
            body: JSON.stringify(body)
        },
        timeoutMs
    );

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API ${response.status}: ${errorText}`);
    }

    return response.json();
}

/**
 * DELETE request
 */
export async function apiDelete(path, token = null, timeoutMs = DEFAULT_TIMEOUT) {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetchWithTimeout(
        `${API_BASE_URL}${path}`,
        { method: 'DELETE', headers },
        timeoutMs
    );

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API ${response.status}: ${errorText}`);
    }

    return response.json();
}

// =====================================================
// API Endpoint Wrappers (기존 invoke 호환)
// =====================================================

// Auth
export const loginWithEmail = (email, password) =>
    apiPost('/api/auth/login', { email, password });

export const registerWithEmail = (email, password, name) =>
    apiPost('/api/auth/register', { email, password, name });

export const getUserInfo = (token) =>
    apiGet('/api/auth/me', token);

export const refreshAuthToken = (refreshToken) =>
    apiPost('/api/auth/refresh', { refresh_token: refreshToken });

export const verifyPassword = (token, password) =>
    apiPost('/api/auth/verify-password', { password }, token);

// Portfolio
export const getPortfolioSummary = (token) =>
    apiGet('/api/portfolio/summary', token);

export const getPortfolioProfitRate = (token, period = '1m') =>
    apiGet(`/api/portfolio/profit-rate?period=${period}`, token);

export const getPortfolioChart = (token, period = '1m') =>
    apiGet(`/api/portfolio/chart?period=${period}`, token);

export const getHoldings = (token) =>
    apiGet('/api/portfolio/holdings', token);

export const getTradeHistory = (token, limit = 50, offset = 0) =>
    apiGet(`/api/portfolio/trades?limit=${limit}&offset=${offset}`, token);

export const getAssetTrades = (token, assetId, limit = 50) =>
    apiGet(`/api/portfolio/assets/${assetId}/trades?limit=${limit}`, token);

export const getPortfolioHistory = (token, days = 30) =>
    apiGet(`/api/portfolio/history?days=${days}`, token);

// Accounts
export const getAccountsList = (token) =>
    apiGet('/api/accounts', token);

export const registerApiKey = (token, exchange, apiKey, apiSecret, passphrase = null, accountNumber = null) =>
    apiPost('/api/accounts/register', { exchange, api_key: apiKey, api_secret: apiSecret, passphrase, account_number: accountNumber }, token);

export const deleteApiKey = (token, accountId) =>
    apiDelete(`/api/accounts/${accountId}`, token);

export const testAccountConnection = (token, accountId) =>
    apiGet(`/api/accounts/${accountId}/test`, token);

// Strategies
export const getActiveStrategies = (token) =>
    apiGet('/api/strategies/active', token);

export const getStrategies = (token) =>
    apiGet('/api/strategies', token);

export const saveStrategy = (token, strategy) =>
    apiPost('/api/strategies', strategy, token);

export const toggleStrategy = (token, strategyId) =>
    apiPut(`/api/strategies/${strategyId}/toggle`, {}, token);

export const deleteStrategy = (token, strategyId) =>
    apiDelete(`/api/strategies/${strategyId}`, token);

export const toggleAsset = (token, assetId) =>
    apiPut(`/api/assets/${assetId}/toggle`, {}, token);

export const deleteAsset = (token, assetId) =>
    apiDelete(`/api/assets/${assetId}`, token);

export const createStrategyWithParams = (token, params) =>
    apiPost('/api/strategies/with-params', params, token);

export const saveSignalParams = (token, assetId, params) =>
    apiPost(`/api/assets/${assetId}/signal-params`, params, token);

export const createAsset = (token, asset) =>
    apiPost('/api/assets', asset, token);

// Emergency Stop
export const emergencyStop = (token) =>
    apiPost('/api/system/estop', { estop: true }, token);

// Webhook
export const getWebhookLogs = (token, limit = 20) =>
    apiGet(`/api/webhook/logs?limit=${limit}`, token);

export const getWebhookUrl = (token) =>
    apiGet('/api/webhook/url', token);

// Symbols
export const searchSymbols = (query, exchange = null, limit = 20) => {
    let url = `/api/search?q=${encodeURIComponent(query)}&limit=${limit}`;
    if (exchange) url += `&exchange=${exchange}`;
    return apiGet(url);
};

export const getSymbolDetail = (exchange, symbol) =>
    apiGet(`/api/symbols/${exchange}/${encodeURIComponent(symbol)}`);

export const getPopularSymbols = (exchange = null) => {
    let url = '/api/symbols/popular';
    if (exchange) url += `?exchange=${exchange}`;
    return apiGet(url);
};

export const searchStocks = (query, market = 'all') =>
    apiGet(`/api/search?q=${encodeURIComponent(query)}&market=${market}`);

export const aiSearchStock = (query) =>
    apiGet(`/api/search?q=${encodeURIComponent(query)}&limit=5`);

// Market Overview
export const getMarketOverview = (token) =>
    apiGet('/api/market/kr/overview', token);

export const getMarketUsOverview = (token) =>
    apiGet('/api/market/us/overview', token);

export const getMarketUsFull = (token) =>
    apiGet('/api/market/us/full', token);

export const getMarketUsTrendMaintain = (token) =>
    apiGet('/api/market/us/trend-maintain', token);

export const getMarketUsRanking = (token, sort = 'change', order = 'desc', limit = 50) =>
    apiGet(`/api/market/us/ranking?sort=${sort}&order=${order}&limit=${limit}`, token);

export const getMarketUsSectors = (token) =>
    apiGet('/api/market/us/sectors', token);

export const getMarketSectors = (token) =>
    apiGet('/api/market/kr/sectors', token);

export const getStockRanking = (token, market = 'KOSPI', sortBy = 'change', limit = 50) =>
    apiGet(`/api/market/kr/ranking?market=${market}&sort=${sortBy}&limit=${limit}`, token);

export const getFeaturedStocks = (token) =>
    apiGet('/api/market/kr/featured', token);

export const getMarketEvents = (token, days = 7) =>
    apiGet(`/api/market/events?days=${days}`, token);

export const getMarketTimeline = (token) =>
    apiGet('/api/market/kr/timeline', token);

export const getMarketSignal = (token) =>
    apiGet('/api/market/kr/signal', token);

export const getMarketBigPicture = (token) =>
    apiGet('/api/market/kr/big-picture', token);

export const getMarketSignalHistory = (token, days = 30) =>
    apiGet(`/api/market/kr/signal/history?days=${days}`, token);

export const getMarketBreadthData = (token, period = '3m') =>
    apiGet(`/api/market/kr/breadth?period=${period}`, token);

export const getMarketBreadthWithIndex = (token, period = '3m') =>
    apiGet(`/api/market/kr/breadth-index?period=${period}`, token);

export const getMarketTrendMaintain = (token) =>
    apiGet('/api/market/kr/trend-maintain', token);

export const getMarketSectorAnalysis = (token) =>
    apiGet('/api/market/kr/sector-analysis', token);

export const getMarketRsRanking = (token, market = 'ALL', limit = 100) =>
    apiGet(`/api/analysis/rs?market=${market}&limit=${limit}`, token);

export const getMarketSectorStocks = (token, sector, limit = 20) =>
    apiGet(`/api/market/kr/sector/${encodeURIComponent(sector)}/stocks?limit=${limit}`, token);

export const getMarketInvestorsData = (token, period = '1m') =>
    apiGet(`/api/market/kr/investors?period=${period}`, token);

export const getMarketTradingValueData = (token, period = '1m', type = 'foreign') =>
    apiGet(`/api/market/kr/trading-value?period=${period}&type=${type}`, token);

export const getMarketEtf = (token, sort = 'volume', limit = 50) =>
    apiGet(`/api/market/etf?sort=${sort}&limit=${limit}`, token);

export const getMarketCrypto = (token, sort = 'volume', limit = 50) =>
    apiGet(`/api/market/crypto?sort=${sort}&limit=${limit}`, token);

export const getAnalysisRs = (token, market = 'ALL', limit = 100) =>
    apiGet(`/api/analysis/rs?market=${market}&limit=${limit}`, token);

export const getAnalysisNewHigh = (token) =>
    apiGet('/api/analysis/new-high', token);

export const getAnalysisValuation = (token, market = 'ALL', sort = 'per', limit = 100) =>
    apiGet(`/api/analysis/valuation?market=${market}&sort=${sort}&limit=${limit}`, token);

// Screener
export const getScreener = (token, filters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
        if (value !== null && value !== undefined) {
            params.append(key, value);
        }
    });
    return apiGet(`/api/screener?${params.toString()}`, token);
};

// Stock Detail - KR
export const getStockFinancialSummary = (code) =>
    apiGet(`/api/stock/kr/${code}/financial-summary`);

export const getStockFinancialTrend = (code) =>
    apiGet(`/api/stock/kr/${code}/financial-trend`);

export const getStockCompany = (code) =>
    apiGet(`/api/stock/kr/${code}/company`);

export const getStockFinancialStatement = (code) =>
    apiGet(`/api/stock/kr/${code}/financial-statement`);

export const getStockNews = (code, limit = 20) =>
    apiGet(`/api/stock/kr/${code}/news?limit=${limit}`);

export const getStockDisclosures = (code, limit = 20) =>
    apiGet(`/api/stock/kr/${code}/disclosures?limit=${limit}`);

export const getStockConsensus = (code) =>
    apiGet(`/api/stock/kr/${code}/consensus`);

export const getStockChartKr = (code, period = '3m') =>
    apiGet(`/api/stock/kr/${code}/chart?period=${period}`);

export const getStockSummaryKr = (code) =>
    apiGet(`/api/stock/kr/${code}/summary`);

export const getStockFinancialsKr = (code, finType = 'annual') =>
    apiGet(`/api/stock/kr/${code}/financials?fin_type=${finType}`);

export const getStockNewsKr = (code, limit = 20) =>
    apiGet(`/api/stock/kr/${code}/news?limit=${limit}`);

export const getEpsRevisionHistory = (code) =>
    apiGet(`/api/stock/kr/${code}/eps-revision`);

export const getStockCompanyKr = (code) =>
    apiGet(`/api/stock/kr/${code}/company`);

export const getStockStatementKr = (code, periodType = 'annual') =>
    apiGet(`/api/stock/kr/${code}/statement?period_type=${periodType}`);

export const getInvestIndicatorsKr = (code) =>
    apiGet(`/api/stock/kr/${code}/invest-indicators`);

// Stock Detail - US
export const getStockSummaryUs = (ticker) =>
    apiGet(`/api/stock/us/${ticker}/summary`);

export const getStockChartUs = (ticker, period = '3m') =>
    apiGet(`/api/stock/us/${ticker}/chart?period=${period}`);

export const getStockNewsUs = (ticker, limit = 20) =>
    apiGet(`/api/stock/us/${ticker}/news?limit=${limit}`);

export const getStockFilingsUs = (ticker, limit = 30) =>
    apiGet(`/api/stock/us/${ticker}/filings?limit=${limit}`);

export const getStockAnalystUs = (ticker, limit = 30) =>
    apiGet(`/api/stock/us/${ticker}/analyst?limit=${limit}`);

export const getStockCompanyUs = (ticker) =>
    apiGet(`/api/stock/us/${ticker}/company`);

export const getStockFinancialsUs = (ticker) =>
    apiGet(`/api/stock/us/${ticker}/financials`);

export const getStockStatementUs = (ticker) =>
    apiGet(`/api/stock/us/${ticker}/statement`);

export const getInvestIndicatorsUs = (ticker) =>
    apiGet(`/api/stock/us/${ticker}/invest-indicators`);

// ETF Detail
export const getEtfSummary = (code) =>
    apiGet(`/api/etf/${code}/summary`);

export const getEtfChart = (code, period = '3m') =>
    apiGet(`/api/etf/${code}/chart?period=${period}`);

export const getEtfPerformance = (code) =>
    apiGet(`/api/etf/${code}/performance`);

// AI
export const getAiUsage = (token) =>
    apiGet('/api/ai/usage', token);

export const requestAiAnalysis = (token, params) =>
    apiPost('/api/ai/analyze', params, token);

export const checkAiStatus = (token, jobId) =>
    apiGet(`/api/ai/status/${jobId}`, token);

export const requestAiChat = (token, params) =>
    apiPost('/api/ai/chat', params, token);

export const getAiRecommendations = (token, market = 'kr') =>
    apiGet(`/api/ai/recommendations?market=${market}`, token);

// Watchlist
export const getWatchlistGroups = (token) =>
    apiGet('/api/watchlist/groups', token);

export const createWatchlistGroup = (token, name, description = '') =>
    apiPost('/api/watchlist/groups', { name, description }, token);

export const deleteWatchlistGroup = (token, groupId) =>
    apiDelete(`/api/watchlist/groups/${groupId}`, token);

export const getWatchlistItems = (token, groupId) =>
    apiGet(`/api/watchlist/groups/${groupId}/items`, token);

export const addWatchlistItem = (token, groupId, exchange, symbol) =>
    apiPost(`/api/watchlist/groups/${groupId}/items`, { exchange, symbol }, token);

export const removeWatchlistItem = (token, groupId, itemId) =>
    apiDelete(`/api/watchlist/groups/${groupId}/items/${itemId}`, token);

// Backtest
export const runBacktest = (token, params) =>
    apiPost('/api/backtest', params, token);

export const runMrBacktest = (token, params) =>
    apiPost('/api/backtest', { ...params, strategy_type: 'mr' }, token);

export const runTrendBacktest = (token, params) =>
    apiPost('/api/backtest', { ...params, strategy_type: 'trend' }, token);

export const runCustomBacktest = (token, params) =>
    apiPost('/api/backtest/custom', params, token);

export const preloadCandles = (token, exchange, symbol, timeframe, days) =>
    apiPost('/api/candles/preload', { exchange, symbol, timeframe, days }, token);

// Premium Strategy Engine
export const getPremiumConfigs = (token) =>
    apiGet('/api/premium/configs', token);

export const getPremiumConfig = (token, assetId) =>
    apiGet(`/api/premium/configs/${assetId}`, token);

export const createPremiumConfig = (token, config) =>
    apiPost('/api/premium/configs', config, token);

export const updatePremiumConfig = (token, assetId, config) =>
    apiPut(`/api/premium/configs/${assetId}`, config, token);

export const deletePremiumConfig = (token, assetId) =>
    apiDelete(`/api/premium/configs/${assetId}`, token);

export const getStrategyState = (token, assetId) =>
    apiGet(`/api/premium/strategy-state/${assetId}`, token);

export const resetStrategyState = (token, assetId) =>
    apiPost(`/api/premium/strategy-state/${assetId}/reset`, {}, token);

export const getSchedulerStatus = (token) =>
    apiGet('/api/premium/scheduler/status', token);

export const startScheduler = (token) =>
    apiPost('/api/premium/scheduler/start', {}, token);

export const stopSchedulerPremium = (token) =>
    apiPost('/api/premium/scheduler/stop', {}, token);

export const registerToScheduler = (token, assetId) =>
    apiPost(`/api/premium/scheduler/register/${assetId}`, {}, token);

export const triggerSignal = (token, assetId) =>
    apiPost(`/api/premium/trigger/${assetId}`, {}, token);

export const getSignalEvents = (token, assetId, limit = 50) =>
    apiGet(`/api/premium/events/${assetId}?limit=${limit}`, token);

// KIS Order Settings
export const saveKisOrderSettings = (token, settings) =>
    apiPost('/api/kis/order-settings', settings, token);

export const getKisOrderSettings = (token, accountId) =>
    apiGet(`/api/kis/order-settings/${accountId}`, token);

// Admin
export const adminGetUsers = (token, page = 1, limit = 50, search = '') =>
    apiGet(`/api/admin/users?page=${page}&limit=${limit}&search=${encodeURIComponent(search)}`, token);

export const adminUpdateUserPlan = (token, userId, plan) =>
    apiPut(`/api/admin/users/${userId}/plan`, { plan }, token);

export const adminGetSystemStatus = (token) =>
    apiGet('/api/admin/system-status', token);

export const adminGetStats = (token) =>
    apiGet('/api/admin/stats', token);

export const adminGetRecentUsers = (token) =>
    apiGet('/api/admin/recent-users', token);

// Exchange Rate
export const getExchangeRate = () =>
    apiGet('/api/exchange-rate');

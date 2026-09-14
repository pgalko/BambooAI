//--------------------
//  AUTHENTICATION MODULE
//--------------------

let authConfig = null;
let authService = null;
let isAuthenticationComplete = false;

const FATAL_AUTH_ERRORS = ['login_required', 'consent_required', 'invalid_grant', 'missing_refresh_token'];

async function initializeAuth() {
    console.log('Auth: Starting initialization...');
    
    const container = document.querySelector('.container');
    if (container) container.style.display = 'none';
    
    try {
        const response = await fetch('/api/auth/status');
        if (!response.ok) {
            throw new Error(`Failed to fetch auth config: ${response.status} ${response.statusText}`);
        }
        
        authConfig = await response.json();
        console.log('Auth: Config loaded:', authConfig);
        
        if (authConfig.mode === 'single') {
            // the self-hosted edition (docs/OSS_DESIGN.md D4): one person, the local identity the server
            // reports, no Auth0 SDK, no sign-in stage - straight to the workspace
            console.log('Auth: single-user mode as', authConfig.user && authConfig.user.name);
            completeAuthentication(authConfig.user || { sub: 'local|local', name: 'local' });
            return;
        }
        if (!authConfig.auth_enabled) {
            throw new Error('Authentication is required but not configured');
        }
        
        await initializeAuth0();
        
    } catch (error) {
        console.error('Auth: Failed to initialize:', error);
        showError('Unable to initialize authentication. Please refresh the page and try again.');
    }
}

async function initializeAuth0() {
    try {
        // One-time migration: clear stale tokens from old audience
        const migrationKey = 'auth_audience_migrated_v1';
        if (!localStorage.getItem(migrationKey)) {
            console.log('Auth: Clearing stale token cache for audience migration');
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('@@auth0')) localStorage.removeItem(key);
            });
            localStorage.setItem(migrationKey, 'true');
        }

        // Load Auth0 SDK
        const script = document.createElement('script');
        script.src = 'https://cdn.auth0.com/js/auth0-spa-js/2.1/auth0-spa-js.production.js';
        await new Promise((resolve, reject) => {
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
        
        authService = await window.auth0.createAuth0Client({
            domain: authConfig.auth0_domain,
            clientId: authConfig.auth0_client_id,
            authorizationParams: {
                redirect_uri: window.location.origin,
                scope: 'openid profile email offline_access',
                audience: authConfig.auth0_audience || undefined
            },
            cacheLocation: 'localstorage',
            useRefreshTokens: true
        });
        
        // Handle callback or check existing session
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('code') || urlParams.has('error')) {
            await handleAuth0Callback();
        } else {
            const isAuthenticated = await authService.isAuthenticated();
            if (isAuthenticated) {
                completeAuthentication(await authService.getUser());
            } else {
                showLoginScreen();
            }
        }
        
    } catch (error) {
        console.error('Auth: Auth0 initialization failed:', error);
        showError('Failed to initialize authentication: ' + error.message);
    }
}

async function handleAuth0Callback() {
    try {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('error')) {
            throw new Error(`Auth0 error: ${urlParams.get('error')} - ${urlParams.get('error_description')}`);
        }
        
        showProcessingMessage();
        await authService.handleRedirectCallback();
        window.history.replaceState({}, document.title, window.location.pathname);
        completeAuthentication(await authService.getUser());
        
    } catch (error) {
        console.error('Auth: Callback handling failed:', error);
        showError('Authentication failed: ' + error.message);
    }
}

// --- UI Screens ---

function createParticles() {
    const container = document.querySelector('.auth-floating-particles');
    if (!container) return;
    for (let i = 0; i < 30; i++) {
        const particle = document.createElement('div');
        particle.className = 'auth-particle';
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDelay = Math.random() * 20 + 's';
        particle.style.animationDuration = (20 + Math.random() * 15) + 's';
        container.appendChild(particle);
    }
}

function showAuthScreen(content) {
    const container = document.querySelector('.container');
    if (container) container.style.display = 'none';
    
    document.body.insertAdjacentHTML('beforeend', `
        <div id="authScreen" class="auth-screen">
            <div class="auth-background-animation">
                <div class="auth-floating-particles"></div>
            </div>
            <div class="auth-content">
                <div class="auth-logo">
                    <img src="/static/image/logo_light.svg" alt="BambooAI">
                    <span>Bamboo AI Lab</span>
                </div>
                <div class="auth-card">${content}</div>
            </div>
        </div>
    `);
    
    createParticles();
}

function showLoginScreen() {
    showAuthScreen(`
        <h2 class="auth-title">Welcome to BambooAI</h2>
        <p class="auth-subtitle">Please sign in to continue your data discovery journey</p>
        <div class="auth-waitlist-notice">
            <p>BambooAI is currently in limited access. If you don't have an account yet, you can join our waitlist at <a href="https://bambooai.io" target="_blank" class="auth-waitlist-link">bambooai.io</a></p>
        </div>
        <button onclick="startLogin()" class="auth-signin-button">Sign In</button>
    `);
}

function showProcessingMessage() {
    // the workspace gate's sign-in stage is the processing message (2026-09-09); the card is retired
    if (window.WorkspaceGate) { WorkspaceGate.stage('signin'); WorkspaceGate.show(); return; }
    showAuthScreen(`
        <h2 class="auth-title">Processing Authentication</h2>
        <div class="auth-spinner-container"><div class="auth-spinner"></div></div>
        <p class="auth-subtitle">Please wait while we complete your login...</p>
    `);
}

function showError(message) {
    showAuthScreen(`
        <div class="auth-error-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="15" y1="9" x2="9" y2="15"/>
                <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
        </div>
        <h2 class="auth-title">Authentication Error</h2>
        <p class="auth-error-message">${message}</p>
        <button onclick="location.reload()" class="auth-retry-button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23,4 23,10 17,10"/>
                <polyline points="1,20 1,14 7,14"/>
                <path d="M20.49,9A9,9,0,0,0,5.64,5.64L1,10m22,4L18.36,18.36A9,9,0,0,1,3.51,15"/>
            </svg>
            Try Again
        </button>
    `);
}

// --- Auth Actions ---

async function startLogin() {
    try {
        if (!authService) throw new Error('Auth0 client not initialized');
        await authService.loginWithRedirect();
    } catch (error) {
        console.error('Auth: Login failed:', error);
        showError('Login failed: ' + error.message);
    }
}

async function logout() {
    if (!authService) return;
    
    try {
        if (authConfig?.auth_enabled) {
            try {
                await window.authService.fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
            } catch (error) {
                console.warn('Auth: Server-side cleanup error:', error);
            }
        }
        
        await authService.logout({
            logoutParams: { returnTo: window.location.origin }
        });
    } catch (error) {
        console.error('Auth: Logout failed:', error);
        location.reload();
    }
}

// --- Session Management ---

function completeAuthentication(user = null) {
    if (!user) {
        showError('Authentication failed. Please try again.');
        return;
    }
    
    console.log('Auth: Completing authentication for user', user.email);
    
    const authScreen = document.getElementById('authScreen');
    if (authScreen) authScreen.remove();
    
    const container = document.querySelector('.container');
    if (container) container.style.display = 'flex';
    
    updateAuthUI(user);
    window.userSessionReady = initializeUserSession();      // the workspace start awaits this (v63)
    
    isAuthenticationComplete = true;
    
    if (typeof initializeAppAfterAuth === 'function') {
        initializeAppAfterAuth();
    }
}

async function initializeUserSession() {
    const buttons = {
        sweatstack: document.querySelector('.sweatstack-data-option'),
        intervals: document.querySelector('.intervals-data-option'),
        endura: document.querySelector('.endura-data-option')
    };
    
    try {
        const response = await window.authService.fetch('/api/user/initialize', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (buttons.sweatstack) {
                buttons.sweatstack.style.display = (data.sweatstack?.sweatstack_enabled && data.sweatstack?.sweatstack_authenticated) ? 'flex' : 'none';
            }
            if (buttons.intervals) {
                buttons.intervals.style.display = data.intervals?.intervals_enabled ? 'flex' : 'none';
            }
            if (buttons.endura) {
                buttons.endura.style.display = data.endura?.endura_enabled ? 'flex' : 'none';
            }
        } else {
            console.warn('Auth: Failed to initialize user session:', response.status);
            Object.values(buttons).forEach(b => { if (b) b.style.display = 'none'; });
        }
    } catch (error) {
        console.warn('Auth: Error initializing user session:', error);
        Object.values(buttons).forEach(b => { if (b) b.style.display = 'none'; });
    }
}

// --- Auth UI ---

function updateAuthUI(user) {
    const authContainer = document.getElementById('authContainer');
    if (!authContainer) return;

    const tooltip = user ? `Log out ${user.name || user.email}` : 'Log out';
    
    if (authConfig?.mode === 'single') {          // nobody to log out: the identity is the machine's
        authContainer.style.display = 'none';
        updateAuthLogoutButton(false, tooltip);
        return;
    }
    if (!authConfig?.auth_enabled) {
        authContainer.style.display = 'none';
        updateAuthLogoutButton(true, tooltip);
        return;
    }
    
    if (user) {
        authContainer.style.display = 'none';
        updateAuthLogoutButton(true, tooltip);
    } else {
        authContainer.innerHTML = `<button onclick="startLogin()" class="auth-button auth-login">Login</button>`;
        authContainer.style.display = 'block';
        updateAuthLogoutButton(false, tooltip);
    }
}

function updateAuthLogoutButton(isAuthenticated, tooltip = 'Log out') {
    const logoutButton = document.getElementById('authLogoutButton');
    if (!logoutButton) return;
    logoutButton.style.display = isAuthenticated ? 'flex' : 'none';
    if (isAuthenticated) logoutButton.setAttribute('data-tooltip', tooltip);
}

// --- Authenticated Fetch ---

async function authenticatedFetch(url, options = {}) {
    if (!(authConfig?.auth_enabled && authService)) {
        return fetch(url, options);
    }

    try {
        const token = await authService.getTokenSilently();
        options.headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
        return fetch(url, options);
    } catch (error) {
        console.warn('Auth: Token fetch failed:', error.error || error.message);

        if (FATAL_AUTH_ERRORS.includes(error.error)) {
            await authService.loginWithRedirect();
            throw new Error('Redirecting to login...');
        }

        // Transient error — retry once with fresh token
        try {
            const token = await authService.getTokenSilently({ cacheMode: 'off' });
            options.headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
            return fetch(url, options);
        } catch (retryError) {
            console.error('Auth: Retry failed:', retryError.error || retryError.message);
            if (FATAL_AUTH_ERRORS.includes(retryError.error)) {
                await authService.loginWithRedirect();
                throw new Error('Redirecting to login...');
            }
            throw retryError;
        }
    }
}

// --- Exports ---

window.logout = logout;

window.authService = {
    initialize: initializeAuth,
    isReady: () => isAuthenticationComplete,
    fetch: authenticatedFetch,
    getToken: async () => {
        if (authConfig?.auth_enabled && authService) {
            try { return await authService.getTokenSilently(); }
            catch { return null; }
        }
        return null;
    },
    getUser: async () => {
        if (authConfig?.auth_enabled && authService) {
            try {
                if (await authService.isAuthenticated()) return await authService.getUser();
            } catch { /* silent */ }
        }
        return null;
    }
};

document.addEventListener('DOMContentLoaded', function() {
    const btn = document.getElementById('authLogoutButton');
    if (btn) btn.addEventListener('click', logout);
});

console.log('Auth: Module loaded');
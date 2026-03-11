import './style.css'
import { renderLibrary } from './pages/library';
import { renderGamePage } from './pages/game';
import { mountAddGameModal } from './pages/add';
import { mountSettingsModal } from './pages/settings';
import { mountAuthModal } from './pages/auth';
import { mountAdminModal } from './pages/admin';
import { ApiError, api } from './api';
import { showConfirmDialog, showNotification } from './ui';

const app = document.querySelector<HTMLDivElement>('#app')!;

// Check if user is logged in
export function isLoggedIn(): boolean {
    return localStorage.getItem('auth_token') !== null;
}

// Global error handler for API errors
window.addEventListener('error', (e) => {
    if (e.error instanceof ApiError) {
        if (e.error.status === 401) {
            // Unauthorized - show login modal
            localStorage.removeItem('auth_token');
            mountAuthModal();
        } else {
            showNotification(e.error.message, 'error');
        }
    }
});

export { showNotification, showConfirmDialog };

// Global loading state
let loadingCount = 0;

export function showLoading() {
    loadingCount++;
    let loader = document.getElementById('global-loader');
    if (!loader) {
        loader = document.createElement('div');
        loader.id = 'global-loader';
        loader.className = 'global-loader';
        loader.innerHTML = '<div class="loader-spinner"></div>';
        document.body.appendChild(loader);
    }
    loader.classList.add('visible');
}

export function hideLoading() {
    loadingCount = Math.max(0, loadingCount - 1);
    if (loadingCount === 0) {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.remove('visible');
        }
    }
}

// Make showLoading/hideLoading available globally for API calls
(window as any).showLoading = showLoading;
(window as any).hideLoading = hideLoading;
(window as any).showNotification = showNotification;
(window as any).showConfirmDialog = showConfirmDialog;

// Load user info and update navbar
export async function loadUserInfo() {
    const userInfo = document.getElementById('userInfo');
    const usernameDisplay = document.getElementById('usernameDisplay');
    const adminBtn = document.getElementById('adminBtn');
    
    if (userInfo && usernameDisplay && isLoggedIn()) {
        try {
            const user = await api.getMe();
            usernameDisplay.textContent = user.username;
            userInfo.classList.remove('hidden');
            userInfo.classList.add('inline-flex');
            
            if (user.is_superadmin && adminBtn) {
                adminBtn.classList.remove('hidden');
                adminBtn.classList.add('inline-flex');
            }
            
            // Logout handler
            document.getElementById('logoutBtn')?.addEventListener('click', () => {
                api.logout();
                window.location.hash = '#auth';
            });
        } catch (e) {
            // Token invalid
            api.logout();
        }
    }
}

function router() {
    const hash = window.location.hash || (isLoggedIn() ? '#library' : '#auth');

    app.innerHTML = ''; // clear

    if (hash.startsWith('#auth')) {
        mountAuthModal();
    } else if (!isLoggedIn()) {
        mountAuthModal();
    } else if (hash === '#library') {
        renderLibrary(app);
    } else if (hash.startsWith('#game/')) {
        const id = parseInt(hash.replace('#game/', ''), 10);
        renderGamePage(app, id);
    } else {
        app.innerHTML = '<h1 class="text-3xl text-center mt-10 text-gray-500">404 - Page not found</h1>';
    }
}

// Global modal bindings
document.getElementById('addGameBtn')?.addEventListener('click', () => {
    mountAddGameModal();
});

document.getElementById('settingsBtn')?.addEventListener('click', () => {
    mountSettingsModal();
});

document.getElementById('adminBtn')?.addEventListener('click', () => {
    mountAdminModal();
});

// Watch for hash changes to simulate routing
window.addEventListener('hashchange', router);

// Start - check auth first
if (!isLoggedIn()) {
    mountAuthModal();
} else {
    loadUserInfo();
    router();
}

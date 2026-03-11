import './style.css'
import { renderLibrary } from './pages/library';
import { renderGamePage } from './pages/game';
import { mountAddGameModal } from './pages/add';
import { mountSettingsModal } from './pages/settings';
import { mountAuthModal } from './pages/auth';
import { mountAdminModal } from './pages/admin';
import { ApiError, api } from './api';

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

// Notification system
export function showNotification(message: string, type: 'success' | 'error' | 'info' = 'info') {
    const container = document.getElementById('notification-container') || createNotificationContainer();
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    
    const icons = {
        success: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>',
        error: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
        info: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
    };
    
    notification.innerHTML = `
        <div class="notification-icon">${icons[type]}</div>
        <div class="notification-message">${message}</div>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
    `;
    
    container.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.classList.add('notification-hide');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.className = 'notification-container';
    document.body.appendChild(container);
    return container;
}

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
            userInfo.classList.add('flex');
            
            if (user.is_superadmin && adminBtn) {
                adminBtn.classList.remove('hidden');
                adminBtn.classList.add('flex');
            }
            
            // Logout handler
            document.getElementById('logoutBtn')?.addEventListener('click', () => {
                api.logout();
                window.location.hash = '#auth';
                window.location.reload();
            });
        } catch (e) {
            // Token invalid
            api.logout();
        }
    }
}

function router() {
    const hash = window.location.hash || '#library';
    
    // Check auth status
    if (!isLoggedIn() && !hash.startsWith('#auth')) {
        mountAuthModal();
        return;
    }
    
    app.innerHTML = ''; // clear

    if (hash === '#library') {
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

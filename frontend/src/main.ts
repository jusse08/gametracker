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

function ensureAmbientBackground() {
    if (document.getElementById('gtAmbientBg')) {
        return;
    }

    const icons = [
        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="6" y1="11" x2="10" y2="11"></line><line x1="8" y1="9" x2="8" y2="13"></line><line x1="15" y1="12" x2="15.01" y2="12"></line><line x1="18" y1="10" x2="18.01" y2="10"></line><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59l-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258l-.017-.151A4 4 0 0 0 17.32 5z"></path></svg>`,
        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="7" y="2.5" width="10" height="19" rx="5"></rect><line x1="12" y1="7" x2="12" y2="10.5"></line></svg>`,
        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2.5"></rect><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M5.5 14h13"></path></svg>`
    ];

    const palette = ['#7ad0ff', '#8cd9ff', '#7bb8ff', '#97e4ff'];
    const layer = document.createElement('div');
    layer.id = 'gtAmbientBg';
    layer.className = 'gt-ambient-bg';

    for (let i = 0; i < 34; i++) {
        const item = document.createElement('span');
        item.className = 'gt-ambient-item';

        const size = 26 + Math.random() * 30;
        const duration = 11 + Math.random() * 18;
        const delay = -(Math.random() * duration);
        const drift = -26 + Math.random() * 52;
        const opacity = 0.2 + Math.random() * 0.24;
        const rotation = -180 + Math.random() * 360;
        const left = Math.random() * 100;
        const color = palette[Math.floor(Math.random() * palette.length)];

        item.style.left = `${left}%`;
        item.style.setProperty('--size', `${size}px`);
        item.style.setProperty('--dur', `${duration}s`);
        item.style.setProperty('--delay', `${delay}s`);
        item.style.setProperty('--drift', `${drift}px`);
        item.style.setProperty('--icon-opacity', opacity.toFixed(3));
        item.style.setProperty('--rot', `${rotation.toFixed(2)}deg`);
        item.style.color = color;
        item.innerHTML = icons[i % icons.length];
        layer.appendChild(item);
    }

    document.body.prepend(layer);
}

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
        app.innerHTML = '<h1 class="text-3xl text-center mt-8 text-gray-500">404 - Page not found</h1>';
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
ensureAmbientBackground();

if (!isLoggedIn()) {
    mountAuthModal();
} else {
    loadUserInfo();
    router();
}

import { api } from '../api';
import { showNotification } from '../main';

export function mountAuthModal() {
    const root = document.getElementById('modal-root')!;
    if (root.querySelector('.gt-modal-overlay')) {
        return;
    }

    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";

    const modal = document.createElement('div');
    modal.className = "gt-panel gt-modal-panel rounded-2xl w-full max-w-md shadow-2xl overflow-hidden";

    modal.innerHTML = `
        <div class="p-8 relative">
            <div class="text-center mb-8">
                <span class="gt-chip inline-flex mb-3">Secure Access</span>
                <h1 class="text-3xl font-bold mb-2">GameTracker</h1>
                <p class="text-slate-300/80">Вход в систему</p>
            </div>

            <!-- Login Form -->
            <form id="loginForm" class="space-y-4">
                <div>
                    <label class="block text-xs font-bold text-slate-300/80 uppercase tracking-widest mb-2">Имя пользователя</label>
                    <input type="text" id="loginUsername" class="gt-input" required>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-300/80 uppercase tracking-widest mb-2">Пароль</label>
                    <input type="password" id="loginPassword" class="gt-input" required>
                </div>
                <button type="submit" class="w-full gt-btn gt-btn-primary justify-center py-3">
                    Войти
                </button>
            </form>
        </div>
    `;

    overlay.appendChild(modal);
    root.appendChild(overlay);
    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        modal.classList.add('is-open');
    });

    document.getElementById('loginForm')!.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = (document.getElementById('loginUsername') as HTMLInputElement).value;
        const password = (document.getElementById('loginPassword') as HTMLInputElement).value;

        const btn = (e.currentTarget as HTMLFormElement).querySelector('button')!;
        const originalText = btn.textContent;
        btn.textContent = 'Вход...';
        btn.disabled = true;

        try {
            const result = await api.login(username, password);
            console.log('Login result:', result);
            // Явно сохраняем токен
            if (result.access_token) {
                localStorage.setItem('auth_token', result.access_token);
                console.log('Token saved:', localStorage.getItem('auth_token') ? 'YES' : 'NO');
            }
            showNotification('Успешный вход!', 'success');
            overlay.remove();
            window.location.hash = '#library';
            window.location.reload();
        } catch (err: any) {
            showNotification(err.message || 'Ошибка входа', 'error');
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });
}

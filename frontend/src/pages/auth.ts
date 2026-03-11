import { api } from '../api';
import { showNotification } from '../main';

export function mountAuthModal() {
    const root = document.getElementById('modal-root')!;

    const overlay = document.createElement('div');
    overlay.className = "fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4";

    const modal = document.createElement('div');
    modal.className = "bg-gray-800 rounded-2xl w-full max-w-md shadow-2xl border border-gray-700 overflow-hidden";

    modal.innerHTML = `
        <div class="p-8">
            <div class="text-center mb-8">
                <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400 mb-2">GameTracker</h1>
                <p class="text-gray-400">Вход в систему</p>
            </div>

            <!-- Login Form -->
            <form id="loginForm" class="space-y-4">
                <div>
                    <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Имя пользователя</label>
                    <input type="text" id="loginUsername" class="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none transition-all" required>
                </div>
                <div>
                    <label class="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Пароль</label>
                    <input type="password" id="loginPassword" class="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 outline-none transition-all" required>
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition-all">
                    Войти
                </button>
            </form>
        </div>
    `;

    overlay.appendChild(modal);
    root.appendChild(overlay);

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

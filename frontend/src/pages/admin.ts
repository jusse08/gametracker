import { api } from '../api';
import { showNotification } from '../ui';

export async function mountAdminModal() {
    const root = document.getElementById('modal-root')!;

    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";

    const modal = document.createElement('div');
    modal.className = "gt-panel gt-modal-panel rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col";

    modal.innerHTML = `
        <div class="px-6 py-4 border-b border-slate-600/40 flex justify-between items-center bg-slate-900/55 sticky top-0">
            <h2 class="text-xl font-bold text-white flex items-center gap-2">
                <svg class="w-5 h-5 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm14 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
                Админ Панель
            </h2>
            <button id="closeAdminBtn" class="text-slate-400 hover:text-white transition-colors">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>

        <div class="p-6 overflow-y-auto space-y-6">
            <!-- Create User Form -->
            <div class="gt-panel rounded-xl p-5">
                <h3 class="text-sm font-bold text-slate-300/80 uppercase tracking-widest mb-4">Создать пользователя</h3>
                <form id="createUserForm" class="flex gap-4 items-end" novalidate>
                    <div class="flex-1">
                        <label class="block text-xs text-slate-400 mb-1">Имя пользователя</label>
                        <input type="text" id="newUsername" class="gt-input" required>
                    </div>
                    <div class="flex-1">
                        <label class="block text-xs text-slate-400 mb-1">Пароль</label>
                        <input type="password" id="newPassword" class="gt-input" required minlength="6">
                    </div>
                    <button type="submit" class="gt-btn gt-btn-admin px-6 py-2 whitespace-nowrap">
                        Создать
                    </button>
                </form>
            </div>

            <!-- Users List -->
            <div>
                <h3 class="text-sm font-bold text-slate-300/80 uppercase tracking-widest mb-4">Список пользователей</h3>
                <div class="bg-slate-900/65 rounded-xl border border-slate-600/40 overflow-hidden">
                    <table class="w-full text-left font-mono">
                        <thead class="bg-slate-800/85 text-xs text-slate-300">
                            <tr>
                                <th class="px-4 py-3 font-medium">ID</th>
                                <th class="px-4 py-3 font-medium">Username</th>
                                <th class="px-4 py-3 font-medium">Роль</th>
                            </tr>
                        </thead>
                        <tbody id="usersTableBody" class="divide-y divide-slate-700/60 text-sm">
                            <tr>
                                <td colspan="3" class="px-4 py-8 text-center text-gray-500 text-sm">Loading users...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    overlay.appendChild(modal);
    root.appendChild(overlay);
    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        modal.classList.add('is-open');
    });

    const closeModal = () => {
        overlay.classList.remove('is-open');
        modal.classList.remove('is-open');
        setTimeout(() => overlay.remove(), 240);
    };

    document.getElementById('closeAdminBtn')!.addEventListener('click', closeModal);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    const tbody = document.getElementById('usersTableBody')!;

    const loadUsers = async () => {
        try {
            const users = await api.getUsers();
            tbody.innerHTML = '';
            
            if (users.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="px-4 py-8 text-center text-gray-500 text-sm">Нет пользователей</td></tr>';
                return;
            }

            users.forEach(u => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-slate-800/40 transition-colors';
                
                const roleBadge = u.is_superadmin 
                    ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-400/10 text-amber-300 border border-amber-400/25">Superadmin</span>'
                    : '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-cyan-400/10 text-cyan-200 border border-cyan-400/25">User</span>';

                tr.innerHTML = `
                    <td class="px-4 py-3 text-gray-500">#${u.id}</td>
                    <td class="px-4 py-3 text-gray-100">${u.username}</td>
                    <td class="px-4 py-3">${roleBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (e: any) {
            tbody.innerHTML = `<tr><td colspan="3" class="px-4 py-8 text-center text-red-400 text-sm">Ошибка: ${e.message}</td></tr>`;
        }
    };

    // Initial load
    loadUsers();

    // Create user handler
    document.getElementById('createUserForm')!.addEventListener('submit', async (e) => {
        e.preventDefault();
        const usernameInput = document.getElementById('newUsername') as HTMLInputElement;
        const passwordInput = document.getElementById('newPassword') as HTMLInputElement;
        const username = usernameInput.value.trim();
        const password = passwordInput.value;
        if (!username) {
            showNotification('Введите имя пользователя.', 'info');
            usernameInput.focus();
            return;
        }
        if (!password.trim()) {
            showNotification('Введите пароль.', 'info');
            passwordInput.focus();
            return;
        }
        if (password.length < 6) {
            showNotification('Пароль должен быть не короче 6 символов.', 'error');
            passwordInput.focus();
            return;
        }
        const btn = (e.currentTarget as HTMLFormElement).querySelector('button')!;
        
        const originalText = btn.textContent;
        btn.textContent = '...';
        btn.disabled = true;

        try {
            await api.adminCreateUser(username, password);
            showNotification('Пользователь успешно создан', 'success');
            usernameInput.value = '';
            passwordInput.value = '';
            await loadUsers();
        } catch (err: any) {
            showNotification(err.message || 'Ошибка создания пользователя', 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });
}

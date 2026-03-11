import { api } from '../api';
import { showNotification } from '../main';

export async function mountAdminModal() {
    const root = document.getElementById('modal-root')!;

    const overlay = document.createElement('div');
    overlay.className = "fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4";

    const modal = document.createElement('div');
    modal.className = "bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl border border-gray-700 overflow-hidden max-h-[90vh] flex flex-col";

    modal.innerHTML = `
        <div class="px-6 py-4 border-b border-gray-700 flex justify-between items-center bg-gray-800/50 sticky top-0">
            <h2 class="text-xl font-bold text-white flex items-center gap-2">
                <svg class="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm14 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
                Админ Панель
            </h2>
            <button id="closeAdminBtn" class="text-gray-400 hover:text-white transition-colors">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>

        <div class="p-6 overflow-y-auto space-y-6">
            <!-- Create User Form -->
            <div class="bg-gray-900/50 rounded-xl p-5 border border-gray-700">
                <h3 class="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">Создать пользователя</h3>
                <form id="createUserForm" class="flex gap-4 items-end">
                    <div class="flex-1">
                        <label class="block text-xs text-gray-500 mb-1">Имя пользователя</label>
                        <input type="text" id="newUsername" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:ring-2 focus:ring-purple-500 outline-none transition-all" required>
                    </div>
                    <div class="flex-1">
                        <label class="block text-xs text-gray-500 mb-1">Пароль</label>
                        <input type="password" id="newPassword" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:ring-2 focus:ring-purple-500 outline-none transition-all" required minlength="6">
                    </div>
                    <button type="submit" class="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded-lg font-medium transition-colors whitespace-nowrap">
                        Создать
                    </button>
                </form>
            </div>

            <!-- Users List -->
            <div>
                <h3 class="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">Список пользователей</h3>
                <div class="bg-gray-900 rounded-xl border border-gray-700 overflow-hidden">
                    <table class="w-full text-left font-mono">
                        <thead class="bg-gray-800 text-xs text-gray-400">
                            <tr>
                                <th class="px-4 py-3 font-medium">ID</th>
                                <th class="px-4 py-3 font-medium">Username</th>
                                <th class="px-4 py-3 font-medium">Роль</th>
                            </tr>
                        </thead>
                        <tbody id="usersTableBody" class="divide-y divide-gray-800 text-sm">
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

    document.getElementById('closeAdminBtn')!.addEventListener('click', () => {
        overlay.remove();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
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
                tr.className = 'hover:bg-gray-800/50 transition-colors';
                
                const roleBadge = u.is_superadmin 
                    ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">Superadmin</span>'
                    : '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20">User</span>';

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
        const btn = (e.currentTarget as HTMLFormElement).querySelector('button')!;
        
        const originalText = btn.textContent;
        btn.textContent = '...';
        btn.disabled = true;

        try {
            await api.adminCreateUser(usernameInput.value, passwordInput.value);
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

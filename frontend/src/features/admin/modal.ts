import { api } from '../../shared/api';
import { showConfirmDialog, showInputDialog, showNotification } from '../../shared/ui';

export async function mountAdminModal() {
    const root = document.getElementById('modal-root')!;

    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";

    const modal = document.createElement('div');
    modal.className = "gt-panel gt-modal-panel rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col";

    modal.innerHTML = `
        <div class="gt-modal-header">
            <h2 class="gt-modal-title">
                <svg class="w-5 h-5 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm14 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"></path></svg>
                Админ Панель
            </h2>
            <button id="closeAdminBtn" class="gt-modal-close">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>

        <div class="gt-modal-section overflow-y-auto flex-grow min-h-0 gt-stack-md">
            <!-- Create User Form -->
            <div class="gt-panel rounded-xl p-5 gt-stack-md">
                <h3 class="text-sm font-bold text-slate-300/80 uppercase tracking-widest">Создать пользователя</h3>
                <form id="createUserForm" class="flex gap-4 items-end" novalidate>
                    <div class="flex-1">
                        <label class="gt-label mb-1">Имя пользователя</label>
                        <input type="text" id="newUsername" class="gt-input" required>
                    </div>
                    <div class="flex-1">
                        <label class="gt-label mb-1">Пароль</label>
                        <input type="password" id="newPassword" class="gt-input" required minlength="6">
                    </div>
                    <button type="submit" class="gt-btn gt-btn-admin gt-btn-md px-6 whitespace-nowrap">
                        Создать
                    </button>
                </form>
            </div>

            <!-- Users List -->
            <div class="gt-stack-md">
                <h3 class="text-sm font-bold text-slate-300/80 uppercase tracking-widest">Список пользователей</h3>
                <div class="gt-table-shell">
                    <table class="gt-table font-mono">
                        <thead>
                            <tr>
                                <th class="px-4 py-3 font-medium">ID</th>
                                <th class="px-4 py-3 font-medium">Username</th>
                                <th class="px-4 py-3 font-medium">Роль</th>
                                <th class="px-4 py-3 font-medium">Действия</th>
                            </tr>
                        </thead>
                        <tbody id="usersTableBody" class="text-sm">
                            <tr>
                                <td colspan="4" class="px-4 py-8 text-center text-gray-500 text-sm">Loading users...</td>
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
        window.removeEventListener('keydown', onKeyDown);
        overlay.classList.remove('is-open');
        modal.classList.remove('is-open');
        setTimeout(() => overlay.remove(), 240);
    };

    const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
            closeModal();
        }
    };

    window.addEventListener('keydown', onKeyDown);

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
                tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-8 text-center text-gray-500 text-sm">Нет пользователей</td></tr>';
                return;
            }

            users.forEach(u => {
                const tr = document.createElement('tr');
                
                const roleBadge = u.is_superadmin 
                    ? '<span class="gt-badge gt-badge-warning">Superadmin</span>'
                    : '<span class="gt-badge gt-badge-info">User</span>';
                const actionCell = u.is_superadmin
                    ? '<span class="inline-flex w-full justify-end text-xs text-slate-500">Недоступно</span>'
                    : `
                        <div class="flex w-full items-center justify-between gap-2">
                            <button class="reset-user-password-btn gt-btn gt-btn-sm px-3 py-1.5" data-id="${u.id}" data-username="${encodeURIComponent(u.username)}">Сменить пароль</button>
                            <button class="delete-user-btn gt-icon-btn gt-icon-btn-danger" type="button" title="Удалить пользователя" aria-label="Удалить пользователя" data-id="${u.id}" data-username="${encodeURIComponent(u.username)}">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            </button>
                        </div>
                    `;

                tr.innerHTML = `
                    <td class="px-4 py-3 text-gray-500">#${u.id}</td>
                    <td class="px-4 py-3 text-gray-100">${u.username}</td>
                    <td class="px-4 py-3">${roleBadge}</td>
                    <td class="px-4 py-3">${actionCell}</td>
                `;
                tbody.appendChild(tr);
            });

            tbody.querySelectorAll<HTMLButtonElement>('.reset-user-password-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const userId = Number(btn.dataset.id || '0');
                    const username = decodeURIComponent(btn.dataset.username || 'пользователя');
                    if (!userId) return;

                    const password = await showInputDialog({
                        title: 'Смена пароля',
                        message: `Введите новый пароль для ${username}.`,
                        placeholder: 'Минимум 6 символов',
                        confirmText: 'Сохранить',
                        cancelText: 'Отмена'
                    });

                    if (password === null) return;
                    if (password.length < 6) {
                        showNotification('Пароль должен быть не короче 6 символов.', 'error');
                        return;
                    }

                    const originalText = btn.textContent;
                    btn.textContent = '...';
                    btn.disabled = true;
                    try {
                        await api.adminUpdateUserPassword(userId, password);
                        showNotification(`Пароль для ${username} обновлён.`, 'success');
                    } catch (err: any) {
                        showNotification(err.message || 'Ошибка смены пароля.', 'error');
                    } finally {
                        btn.textContent = originalText;
                        btn.disabled = false;
                    }
                });
            });

            tbody.querySelectorAll<HTMLButtonElement>('.delete-user-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const userId = Number(btn.dataset.id || '0');
                    const username = decodeURIComponent(btn.dataset.username || 'пользователя');
                    if (!userId) return;

                    const shouldDelete = await showConfirmDialog({
                        title: 'Удалить пользователя?',
                        message: `Удалить пользователя ${username}? Это действие необратимо.`,
                        confirmText: 'Удалить',
                        cancelText: 'Отмена',
                        danger: true
                    });
                    if (!shouldDelete) return;

                    const originalHtml = btn.innerHTML;
                    btn.innerHTML = '...';
                    btn.disabled = true;
                    try {
                        await api.adminDeleteUser(userId);
                        showNotification(`Пользователь ${username} удалён.`, 'success');
                        await loadUsers();
                    } catch (err: any) {
                        showNotification(err.message || 'Ошибка удаления пользователя.', 'error');
                    } finally {
                        btn.innerHTML = originalHtml;
                        btn.disabled = false;
                    }
                });
            });
        } catch (e: any) {
            tbody.innerHTML = `<tr><td colspan="4" class="px-4 py-8 text-center text-red-400 text-sm">Ошибка: ${e.message}</td></tr>`;
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

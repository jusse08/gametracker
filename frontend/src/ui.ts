type NotificationType = 'success' | 'error' | 'info';

interface ConfirmDialogOptions {
    title?: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    danger?: boolean;
}

interface InputDialogOptions {
    title?: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    placeholder?: string;
    initialValue?: string;
}

export function showNotification(message: string, type: NotificationType = 'info') {
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
        <div class="notification-message"></div>
        <button class="notification-close" type="button" aria-label="Закрыть уведомление">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
    `;
    const messageEl = notification.querySelector('.notification-message');
    if (messageEl) {
        messageEl.textContent = message;
    }

    notification.querySelector('.notification-close')?.addEventListener('click', () => {
        notification.remove();
    });

    container.appendChild(notification);

    setTimeout(() => {
        notification.classList.add('notification-hide');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

export function showConfirmDialog(options: ConfirmDialogOptions): Promise<boolean> {
    const root = document.getElementById('modal-root') || document.body;
    const overlay = document.createElement('div');
    overlay.className = 'gt-modal-overlay';

    const panel = document.createElement('div');
    panel.className = 'gt-panel gt-modal-panel rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden';

    const title = options.title || 'Подтверждение';
    const confirmText = options.confirmText || 'Подтвердить';
    const cancelText = options.cancelText || 'Отмена';
    const confirmBtnClass = options.danger
        ? 'gt-btn-danger'
        : 'gt-btn-primary';

    panel.innerHTML = `
        <div class="gt-modal-header">
            <h3 id="confirmDialogTitle" class="gt-modal-title text-lg"></h3>
        </div>
        <div id="confirmDialogMessage" class="p-5 text-sm text-slate-200/90 leading-relaxed"></div>
        <div class="p-5 pt-0 flex justify-end gap-2">
            <button type="button" class="gt-btn gt-btn-secondary">${cancelText}</button>
            <button type="button" class="gt-btn ${confirmBtnClass}">${confirmText}</button>
        </div>
    `;

    const titleEl = panel.querySelector<HTMLElement>('#confirmDialogTitle');
    const messageEl = panel.querySelector<HTMLElement>('#confirmDialogMessage');
    if (titleEl) {
        titleEl.textContent = title;
    }
    if (messageEl) {
        messageEl.textContent = options.message;
    }

    overlay.appendChild(panel);
    root.appendChild(overlay);

    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        panel.classList.add('is-open');
    });

    return new Promise((resolve) => {
        let done = false;
        const cleanup = (value: boolean) => {
            if (done) return;
            done = true;

            window.removeEventListener('keydown', onKeyDown);
            overlay.classList.remove('is-open');
            panel.classList.remove('is-open');
            setTimeout(() => overlay.remove(), 240);
            resolve(value);
        };

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                cleanup(false);
            }
            if (event.key === 'Enter') {
                cleanup(true);
            }
        };

        window.addEventListener('keydown', onKeyDown);
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) {
                cleanup(false);
            }
        });

        const [cancelBtn, confirmBtn] = panel.querySelectorAll('button');
        cancelBtn?.addEventListener('click', () => cleanup(false));
        confirmBtn?.addEventListener('click', () => cleanup(true));
    });
}

export function showInputDialog(options: InputDialogOptions): Promise<string | null> {
    const root = document.getElementById('modal-root') || document.body;
    const overlay = document.createElement('div');
    overlay.className = 'gt-modal-overlay';

    const panel = document.createElement('div');
    panel.className = 'gt-panel gt-modal-panel rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden';

    const title = options.title || 'Введите значение';
    const confirmText = options.confirmText || 'Сохранить';
    const cancelText = options.cancelText || 'Отмена';

    panel.innerHTML = `
        <div class="gt-modal-header">
            <h3 id="inputDialogTitle" class="gt-modal-title text-lg"></h3>
        </div>
        <div class="p-5 space-y-3">
            <p id="inputDialogMessage" class="text-sm text-slate-200/90 leading-relaxed"></p>
            <input id="inputDialogField" type="text" class="gt-input text-sm" />
        </div>
        <div class="p-5 pt-0 flex justify-end gap-2">
            <button type="button" class="gt-btn gt-btn-secondary">${cancelText}</button>
            <button type="button" class="gt-btn gt-btn-primary">${confirmText}</button>
        </div>
    `;

    const titleEl = panel.querySelector<HTMLElement>('#inputDialogTitle');
    const messageEl = panel.querySelector<HTMLElement>('#inputDialogMessage');
    const inputEl = panel.querySelector<HTMLInputElement>('#inputDialogField');
    if (titleEl) {
        titleEl.textContent = title;
    }
    if (messageEl) {
        messageEl.textContent = options.message;
    }
    if (inputEl) {
        inputEl.placeholder = options.placeholder || '';
        inputEl.value = options.initialValue || '';
    }

    overlay.appendChild(panel);
    root.appendChild(overlay);

    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        panel.classList.add('is-open');
        inputEl?.focus();
        inputEl?.select();
    });

    return new Promise((resolve) => {
        let done = false;
        const cleanup = (value: string | null) => {
            if (done) return;
            done = true;

            window.removeEventListener('keydown', onKeyDown);
            overlay.classList.remove('is-open');
            panel.classList.remove('is-open');
            setTimeout(() => overlay.remove(), 240);
            resolve(value);
        };

        const submit = () => {
            const value = inputEl?.value.trim() || '';
            if (!value) {
                inputEl?.focus();
                return;
            }
            cleanup(value);
        };

        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                cleanup(null);
            }
            if (event.key === 'Enter') {
                submit();
            }
        };

        window.addEventListener('keydown', onKeyDown);
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) {
                cleanup(null);
            }
        });

        const [cancelBtn, confirmBtn] = panel.querySelectorAll('button');
        cancelBtn?.addEventListener('click', () => cleanup(null));
        confirmBtn?.addEventListener('click', submit);
    });
}

function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.className = 'notification-container';
    document.body.appendChild(container);
    return container;
}

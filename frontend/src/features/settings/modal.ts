import { api } from '../../shared/api';
import { showConfirmDialog, showNotification } from '../../shared/ui';

function escapeHtml(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatDate(value?: string): string {
    if (!value) return '—';
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return '—';
    return dt.toLocaleString('ru-RU');
}

export async function mountSettingsModal() {
    const root = document.getElementById('modal-root')!;
    const settings = await api.getSettings();

    let currentPairCode = '';

    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";
    overlay.id = "settingsModal";

    const panel = document.createElement('div');
    panel.className = "gt-panel gt-modal-panel w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col";

    panel.innerHTML = `
            <div class="gt-modal-header">
                <h2 class="gt-modal-title">
                    <svg class="w-6 h-6 text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Настройки
                </h2>
                <button id="closeSettingsBtn" class="gt-modal-close">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>

            <div class="gt-modal-section gt-stack-md overflow-y-auto flex-grow min-h-0">
                <section class="gt-stack-md">
                    <h3 class="text-lg font-semibold text-white flex items-center gap-2">
                        <img src="/icons/steam.svg" alt="Steam" class="w-5 h-5 object-contain" />
                        Steam
                    </h3>
                    <form id="steamForm" class="gt-stack-md" novalidate>
                        <div>
                            <label class="gt-label">Steam Web API Key</label>
                            <input type="password" id="steamApiKey" class="gt-input text-sm" placeholder="Ваш API Key..." value="${escapeHtml(settings.steam_api_key || '')}">
                            <p class="gt-help">Получить можно на <a href="https://steamcommunity.com/dev/apikey" target="_blank" class="text-cyan-300 underline">steamcommunity.com/dev/apikey</a></p>
                        </div>

                        <div>
                            <label class="gt-label">Ссылка на профиль Steam</label>
                            <input type="url" id="steamProfileUrl" class="gt-input text-sm" placeholder="https://steamcommunity.com/id/username/" value="${escapeHtml(settings.steam_profile_url || '')}">
                            <p class="gt-help">Убедитесь, что профиль <b>открыт</b> в настройках приватности Steam.</p>
                        </div>

                        <div class="pt-2">
                            <button type="submit" class="w-full gt-btn gt-btn-primary gt-btn-lg justify-center">
                                Сохранить настройки Steam
                            </button>
                        </div>
                    </form>
                </section>

                <section class="border-t border-slate-600/45 pt-6 gt-stack-md">
                    <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <svg class="w-5 h-5 text-lime-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                        GameTracker Агент
                    </h3>

                    <div class="gt-surface-card gt-stack-sm">
                        <p class="text-sm text-slate-300">Скачайте агент, сгенерируйте одноразовый код и введите его в окне агента. Код живет 10 минут.</p>
                        <div class="text-base font-mono text-cyan-100 bg-slate-950/80 border border-cyan-700/40 rounded-lg px-3 py-2 tracking-widest" id="agentPairCodeValue">------</div>
                        <p class="text-xs text-slate-400" id="agentPairCodeExpires">Код не сгенерирован</p>
                        <div class="flex flex-col sm:flex-row gap-2">
                            <button id="generatePairCodeBtn" class="gt-btn justify-center border-cyan-300/40 bg-cyan-300/16 hover:bg-cyan-300/24">Сгенерировать код</button>
                            <button id="copyPairCodeBtn" class="gt-btn justify-center">Скопировать код</button>
                        </div>
                    </div>

                    <div class="gt-surface-card gt-stack-sm">
                        <button id="downloadAgentBtn" class="w-full sm:w-auto gt-btn justify-center gap-2 border-lime-300/40 bg-lime-300/20 hover:bg-lime-300/25">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                            Скачать агент (.exe)
                        </button>
                    </div>

                    <div class="gt-surface-card gt-stack-sm">
                        <p class="text-sm text-slate-300">Подключенные устройства агента:</p>
                        <div id="agentDevices" class="gt-stack-sm text-sm text-slate-300"></div>
                    </div>
                </section>
            </div>
    `;

    overlay.appendChild(panel);
    root.appendChild(overlay);
    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        panel.classList.add('is-open');
    });

    const close = () => {
        window.removeEventListener('keydown', onKeyDown);
        overlay.classList.remove('is-open');
        panel.classList.remove('is-open');
        setTimeout(() => overlay.remove(), 240);
    };

    const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
            close();
        }
    };

    window.addEventListener('keydown', onKeyDown);

    document.getElementById('closeSettingsBtn')?.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    const setPairCodeDisplay = (code: string, expiresAt: string) => {
        currentPairCode = code;
        const codeEl = document.getElementById('agentPairCodeValue');
        const expiresEl = document.getElementById('agentPairCodeExpires');
        if (codeEl) codeEl.textContent = code || '------';
        if (expiresEl) {
            expiresEl.textContent = code
                ? `Действует до ${formatDate(expiresAt)}`
                : 'Код не сгенерирован';
        }
    };

    const renderDevices = async () => {
        const box = document.getElementById('agentDevices');
        if (!box) return;
        box.innerHTML = '<div class="text-xs text-slate-400">Загрузка...</div>';
        try {
            const devices = await api.getAgentDevices();
            if (devices.length === 0) {
                box.innerHTML = '<div class="text-xs text-slate-400">Устройств пока нет</div>';
                return;
            }

            box.innerHTML = devices.map((device) => {
                const safeId = escapeHtml(device.device_id);
                const safeName = escapeHtml(device.device_name);
                const revoked = !!device.revoked_at;
                const status = revoked ? 'Отключено' : 'Активно';
                const statusClass = revoked ? 'text-rose-300' : 'text-emerald-300';
                return `
                    <div class="border border-slate-700/60 rounded-lg px-3 py-2 gt-stack-sm">
                        <div class="flex items-center justify-between gap-2">
                            <div>
                                <div class="font-semibold">${safeName}</div>
                                <div class="text-xs font-mono text-slate-400">${safeId}</div>
                            </div>
                            <div class="text-xs ${statusClass}">${status}</div>
                        </div>
                        <div class="text-xs text-slate-400">Последняя активность: ${formatDate(device.last_seen_at)}</div>
                        <div class="text-xs text-slate-400">Refresh до: ${formatDate(device.refresh_expires_at)}</div>
                        ${revoked ? '' : `<button class="gt-btn gt-btn-sm border-rose-300/40 bg-rose-300/12 hover:bg-rose-300/20 revoke-device-btn" data-device-id="${safeId}">Отключить устройство</button>`}
                    </div>
                `;
            }).join('');

            box.querySelectorAll<HTMLButtonElement>('.revoke-device-btn').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    const deviceId = btn.dataset.deviceId || '';
                    if (!deviceId) return;
                    const confirmed = await showConfirmDialog({
                        title: 'Отключить устройство?',
                        message: `Отключить агент ${deviceId}?`,
                        confirmText: 'Отключить',
                        cancelText: 'Отмена',
                        danger: true,
                    });
                    if (!confirmed) return;

                    const prev = btn.textContent;
                    btn.textContent = '...';
                    btn.disabled = true;
                    try {
                        await api.revokeAgentDevice(deviceId);
                        showNotification('Устройство отключено', 'success');
                        await renderDevices();
                    } catch (err: any) {
                        showNotification(err.message || 'Не удалось отключить устройство', 'error');
                        btn.textContent = prev;
                        btn.disabled = false;
                    }
                });
            });
        } catch (err: any) {
            box.innerHTML = `<div class="text-xs text-rose-300">${escapeHtml(err.message || 'Ошибка загрузки устройств')}</div>`;
        }
    };

    document.getElementById('steamForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const apiKey = (document.getElementById('steamApiKey') as HTMLInputElement).value;
        const profileUrlInput = document.getElementById('steamProfileUrl') as HTMLInputElement;
        const profileUrl = profileUrlInput.value.trim();
        if (profileUrl) {
            try {
                new URL(profileUrl);
            } catch {
                showNotification('Введите корректную ссылку на профиль Steam.', 'error');
                profileUrlInput.focus();
                return;
            }
        }

        const btn = (e.currentTarget as HTMLFormElement).querySelector('button')!;
        const originalText = btn.innerHTML;
        btn.innerHTML = 'Сохранение...';
        btn.disabled = true;

        try {
            await api.updateSettings({
                steam_api_key: apiKey,
                steam_profile_url: profileUrl
            });
            showNotification('Настройки Steam сохранены', 'success');
            close();
        } catch (err: any) {
            showNotification(err.message || 'Ошибка при сохранении настроек', 'error');
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    });

    document.getElementById('downloadAgentBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('downloadAgentBtn') as HTMLButtonElement;
        const originalText = btn.innerHTML;
        btn.innerHTML = 'Загрузка...';
        btn.disabled = true;

        try {
            const blob = await api.downloadAgent();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'GameTrackerAgent.exe';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            showNotification('Агент загружен!', 'success');
        } catch (err: any) {
            showNotification(err.message || 'Ошибка загрузки агента', 'error');
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    });

    document.getElementById('generatePairCodeBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('generatePairCodeBtn') as HTMLButtonElement;
        const originalText = btn.textContent;
        btn.textContent = 'Генерация...';
        btn.disabled = true;
        try {
            const data = await api.createAgentPairCode();
            setPairCodeDisplay(data.pair_code, data.expires_at);
            showNotification('Код подключения сгенерирован', 'success');
        } catch (err: any) {
            showNotification(err.message || 'Не удалось сгенерировать код', 'error');
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    });

    document.getElementById('copyPairCodeBtn')?.addEventListener('click', async () => {
        if (!currentPairCode) {
            showNotification('Сначала сгенерируйте код', 'info');
            return;
        }
        try {
            await navigator.clipboard.writeText(currentPairCode);
            showNotification('Код скопирован', 'success');
        } catch {
            showNotification('Не удалось скопировать код', 'error');
        }
    });

    setPairCodeDisplay('', '');
    await renderDevices();
}

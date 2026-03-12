import { api } from '../api';
import { showNotification } from '../ui';

export async function mountSettingsModal() {
    const root = document.getElementById('modal-root')!;
    const settings = await api.getSettings();
    const agentTokenResponse = await api.getAgentToken();
    let currentAgentToken = agentTokenResponse.agent_token;

    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";
    overlay.id = "settingsModal";

    const panel = document.createElement('div');
    panel.className = "gt-panel gt-modal-panel w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto";

    panel.innerHTML = `
            <div class="gt-modal-header sticky">
                <h2 class="gt-modal-title">
                    <svg class="w-6 h-6 text-cyan-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Настройки
                </h2>
                <button id="closeSettingsBtn" class="gt-modal-close">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>

            <div class="p-6 space-y-6">
                <!-- Steam Settings -->
                <section>
                    <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <svg class="w-5 h-5 text-cyan-300" fill="currentColor" viewBox="0 0 24 24"><path d="M11.979 0C5.668 0 .511 4.995.022 11.267l4.457 6.671a2.543 2.543 0 011.797-.726c.322 0 .627.061.91.168l2.954-4.431c-.012-.156-.02-.313-.02-.473 0-2.206 1.79-3.996 3.996-3.996.21 0 .414.02.615.052L16.588 5.73C15.19 2.64 12.136 0 8.5 0h3.479zM7.5 9.044c-1.655 0-2.996 1.341-2.996 2.996 0 1.654 1.341 2.996 2.996 2.996 1.654 0 2.996-1.342 2.996-2.996 0-1.655-1.342-2.996-2.996-2.996zm8.486 11.444l4.99-7.485c.596-.894.954-1.967.954-3.125 0-3.037-2.463-5.5-5.5-5.5-.43 0-.847.054-1.248.152l-2.78 4.17c.14.41.22.846.22 1.302 0 2.206-1.79 3.996-3.996 3.996-.456 0-.892-.08-1.302-.22l-4.17 2.78c-.098.401-.152.818-.152 1.248 0 3.037 2.463 5.5 5.5 5.5 1.158 0 2.231-.358 3.125-.954l-1.64-1.864z"/></svg>
                        Steam
                    </h3>
                    <form id="steamForm" class="space-y-4" novalidate>
                        <div>
                            <label class="gt-label">Steam Web API Key</label>
                            <input type="password" id="steamApiKey" class="gt-input text-sm" placeholder="Ваш API Key..." value="${settings.steam_api_key || ''}">
                            <p class="gt-help">Получить можно на <a href="https://steamcommunity.com/dev/apikey" target="_blank" class="text-cyan-300 underline">steamcommunity.com/dev/apikey</a></p>
                        </div>

                        <div>
                            <label class="gt-label">Ссылка на профиль Steam</label>
                            <input type="url" id="steamProfileUrl" class="gt-input text-sm" placeholder="https://steamcommunity.com/id/username/" value="${settings.steam_profile_url || ''}">
                            <p class="gt-help">Убедитесь, что профиль <b>открыт</b> в настройках приватности Steam.</p>
                        </div>

                        <div class="pt-2">
                            <button type="submit" class="w-full gt-btn gt-btn-primary gt-btn-lg justify-center">
                                Сохранить настройки Steam
                            </button>
                        </div>
                    </form>
                </section>

                <!-- Agent Settings -->
                <section class="border-t border-slate-600/45 pt-6">
                    <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                        <svg class="w-5 h-5 text-lime-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                        GameTracker Агент
                    </h3>
                    
                    <div class="mb-4 gt-surface-card">
                        <p class="text-sm text-slate-300 mb-3">Агент отслеживает запущенные игры и автоматически фиксирует время в разделе "Библиотека". Настройка исполняемого файла доступна только в карточке конкретной игры.</p>
                        <button id="downloadAgentBtn" class="w-full sm:w-auto gt-btn justify-center gap-2 border-lime-300/40 bg-lime-300/20 hover:bg-lime-300/25">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                            Скачать агент (.exe)
                        </button>
                    </div>

                    <div class="gt-surface-card">
                        <p class="text-sm text-slate-300 mb-2">Токен агента (используется для авторизации агента от вашего аккаунта):</p>
                        <div class="text-xs font-mono text-slate-200 bg-slate-950/80 border border-slate-700 rounded-lg px-3 py-2 break-all" id="agentTokenValue">${currentAgentToken}</div>
                        <div class="mt-3 flex flex-col sm:flex-row gap-2">
                            <button id="copyAgentTokenBtn" class="gt-btn justify-center">Скопировать токен</button>
                            <button id="rotateAgentTokenBtn" class="gt-btn justify-center border-amber-300/40 bg-amber-300/10 hover:bg-amber-300/20">Пересоздать токен</button>
                        </div>
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

    // Bindings
    const close = () => {
        overlay.classList.remove('is-open');
        panel.classList.remove('is-open');
        setTimeout(() => overlay.remove(), 240);
    };

    document.getElementById('closeSettingsBtn')?.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    // Steam form
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

    // Download agent
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

    document.getElementById('copyAgentTokenBtn')?.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(currentAgentToken);
            showNotification('Токен скопирован', 'success');
        } catch {
            showNotification('Не удалось скопировать токен', 'error');
        }
    });

    document.getElementById('rotateAgentTokenBtn')?.addEventListener('click', async () => {
        const btn = document.getElementById('rotateAgentTokenBtn') as HTMLButtonElement;
        const originalText = btn.innerHTML;
        btn.innerHTML = 'Обновление...';
        btn.disabled = true;

        try {
            const data = await api.rotateAgentToken();
            currentAgentToken = data.agent_token;
            const tokenEl = document.getElementById('agentTokenValue');
            if (tokenEl) {
                tokenEl.textContent = currentAgentToken;
            }
            showNotification('Токен пересоздан. Обновите токен в агенте.', 'success');
        } catch (err: any) {
            showNotification(err.message || 'Не удалось пересоздать токен', 'error');
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    });

}

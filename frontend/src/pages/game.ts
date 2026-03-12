import { api, type QuestCategory } from '../api';
import { showConfirmDialog, showNotification } from '../ui';

function escapeHtml(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function statusLabel(status: string): string {
    if (status === 'playing') return 'Играю';
    if (status === 'backlog') return 'Запланировано';
    if (status === 'completed') return 'Пройдено';
    if (status === 'deferred') return 'Отложено';
    return status;
}

async function openQuestActionsModal(gameId: number, onDataChanged: () => Promise<void>) {
    const root = document.getElementById('modal-root');
    if (!root) {
        showNotification('Модальное окно недоступно.', 'error');
        return;
    }

    const categories = await api.getChecklistCategories(gameId);
    let activeMode: 'task' | 'category' | 'wiki' = categories.length > 0 ? 'task' : 'category';

    const overlay = document.createElement('div');
    overlay.className = 'gt-modal-overlay is-open';
    const modal = document.createElement('div');
    modal.className = 'gt-panel gt-modal-panel is-open rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden';
    overlay.appendChild(modal);
    root.appendChild(overlay);

    const closeModal = () => {
        overlay.classList.remove('is-open');
        modal.classList.remove('is-open');
        setTimeout(() => overlay.remove(), 220);
    };

    const renderBody = () => {
        const hasCategories = categories.length > 0;
        const categoryOptions = categories
            .map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`)
            .join('');

        modal.innerHTML = `
            <div class="p-5 border-b border-gray-700/60 flex items-center justify-between bg-gray-900/65">
                <h3 class="text-lg font-bold text-white">Добавить в квесты</h3>
                <button id="questModalCloseBtn" class="text-gray-400 hover:text-white text-xl leading-none">×</button>
            </div>
            <div class="p-5 space-y-4">
                <div class="grid grid-cols-3 gap-2">
                    <button data-mode="task" class="quest-mode-btn px-3 py-2 rounded-lg text-sm border ${activeMode === 'task' ? 'border-emerald-400/70 bg-emerald-500/20 text-emerald-200' : 'border-gray-700 bg-gray-900 text-gray-300'}">Задача</button>
                    <button data-mode="category" class="quest-mode-btn px-3 py-2 rounded-lg text-sm border ${activeMode === 'category' ? 'border-indigo-400/70 bg-indigo-500/20 text-indigo-200' : 'border-gray-700 bg-gray-900 text-gray-300'}">Категория</button>
                    <button data-mode="wiki" class="quest-mode-btn px-3 py-2 rounded-lg text-sm border ${activeMode === 'wiki' ? 'border-blue-400/70 bg-blue-500/20 text-blue-200' : 'border-gray-700 bg-gray-900 text-gray-300'}">Импорт Wiki</button>
                </div>

                <div id="questModeTask" class="${activeMode === 'task' ? '' : 'hidden'} space-y-3">
                    ${!hasCategories ? '<div class="text-xs text-amber-300 bg-amber-900/20 border border-amber-700/40 px-3 py-2 rounded-lg">Сначала создайте хотя бы одну категорию.</div>' : ''}
                    <input id="questModalTaskTitle" type="text" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Новая задача / миссия..." ${hasCategories ? '' : 'disabled'}>
                    <div class="flex gap-2">
                        <select id="questModalTaskCategory" class="flex-grow bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500" ${hasCategories ? '' : 'disabled'}>
                            ${categoryOptions}
                        </select>
                        <button id="questModalCreateTaskBtn" class="bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/40 px-4 py-2.5 rounded-lg text-sm font-medium ${hasCategories ? '' : 'opacity-50 cursor-not-allowed'}" ${hasCategories ? '' : 'disabled'}>Добавить</button>
                    </div>
                </div>

                <div id="questModeCategory" class="${activeMode === 'category' ? '' : 'hidden'} space-y-3">
                    <input id="questModalCategoryName" type="text" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Название категории...">
                    <button id="questModalCreateCategoryBtn" class="bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30 border border-indigo-500/40 px-4 py-2.5 rounded-lg text-sm font-medium">Создать категорию</button>
                </div>

                <div id="questModeWiki" class="${activeMode === 'wiki' ? '' : 'hidden'} space-y-3">
                    <input id="questModalWikiUrl" type="url" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500" placeholder="Ссылка на Wiki (URL)...">
                    <button id="questModalImportWikiBtn" class="bg-blue-600/20 text-blue-300 hover:bg-blue-600/30 border border-blue-500/40 px-4 py-2.5 rounded-lg text-sm font-medium">Импортировать</button>
                </div>
            </div>
        `;

        modal.querySelector('#questModalCloseBtn')?.addEventListener('click', closeModal);
        modal.querySelectorAll('.quest-mode-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const mode = (btn as HTMLButtonElement).dataset.mode as 'task' | 'category' | 'wiki';
                activeMode = mode;
                renderBody();
            });
        });

        modal.querySelector('#questModalCreateTaskBtn')?.addEventListener('click', async () => {
            const titleInput = modal.querySelector<HTMLInputElement>('#questModalTaskTitle');
            const categoryInput = modal.querySelector<HTMLSelectElement>('#questModalTaskCategory');
            if (!titleInput || !categoryInput) return;
            const title = titleInput.value.trim();
            const category = categoryInput.value.trim();
            if (!title) {
                titleInput.focus();
                showNotification('Введите название задачи.', 'info');
                return;
            }
            if (!category) {
                showNotification('Выберите категорию.', 'info');
                return;
            }
            try {
                await api.createChecklistItem(gameId, { title, category });
                titleInput.value = '';
                await onDataChanged();
                showNotification('Задача добавлена', 'success');
                titleInput.focus();
            } catch (err: any) {
                showNotification(err.message || 'Не удалось добавить задачу.', 'error');
            }
        });

        modal.querySelector('#questModalCreateCategoryBtn')?.addEventListener('click', async () => {
            const nameInput = modal.querySelector<HTMLInputElement>('#questModalCategoryName');
            if (!nameInput) return;
            const name = nameInput.value.trim();
            if (!name) {
                nameInput.focus();
                showNotification('Введите название категории.', 'info');
                return;
            }
            try {
                await api.createChecklistCategory(gameId, name);
                nameInput.value = '';
                await onDataChanged();
                showNotification('Категория создана', 'success');
                const refreshed = await api.getChecklistCategories(gameId);
                categories.splice(0, categories.length, ...refreshed);
                activeMode = 'task';
                renderBody();
            } catch (err: any) {
                showNotification(err.message || 'Не удалось создать категорию.', 'error');
            }
        });

        modal.querySelector('#questModalImportWikiBtn')?.addEventListener('click', async () => {
            const urlInput = modal.querySelector<HTMLInputElement>('#questModalWikiUrl');
            if (!urlInput) return;
            const wikiUrl = urlInput.value.trim();
            if (!wikiUrl) {
                urlInput.focus();
                showNotification('Введите ссылку на Wiki.', 'info');
                return;
            }
            try {
                new URL(wikiUrl);
            } catch {
                showNotification('Введите корректный URL.', 'error');
                urlInput.focus();
                return;
            }
            try {
                await api.importWikiChecklist(gameId, wikiUrl);
                await onDataChanged();
                showNotification('Импорт из Wiki завершен', 'success');
                const refreshed = await api.getChecklistCategories(gameId);
                categories.splice(0, categories.length, ...refreshed);
                renderBody();
            } catch (err: any) {
                showNotification(err.message || 'Ошибка при импорте из Wiki', 'error');
            }
        });
    };

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeModal();
        }
    });

    renderBody();
}

export async function renderGamePage(container: HTMLElement, gameId: number) {
    container.innerHTML = `
        <div class="flex items-center justify-center min-h-[50vh]">
            <div class="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
        </div>
    `;

    try {
        let game = await api.getGame(gameId);
        const cover = game.cover_url || 'https://via.placeholder.com/300x400/1f2937/4b5563?text=Нет+обложки';
        const syncTypeLabel = game.sync_type === 'steam' ? 'Steam' : 'Non-Steam';
        const syncTypeBadgeClass = game.sync_type === 'steam'
            ? 'bg-sky-500/15 text-sky-300 border border-sky-400/30'
            : 'bg-emerald-500/15 text-emerald-300 border border-emerald-400/30';
        const achievementsTitle = game.sync_type === 'steam' ? 'Достижения Steam' : 'Синхронизация через агент';
        const achievementsAction = game.sync_type === 'steam'
            ? `
                            <button id="syncAchievementsBtn" class="bg-gray-700/80 hover:bg-gray-600 text-xs px-3 py-1.5 rounded-lg text-white transition-colors flex items-center gap-1.5 border border-gray-600">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                <span class="hidden sm:inline">Синхронизировать ачивки</span>
                            </button>
            `
            : `
                            <span class="text-xs text-gray-500 bg-gray-900/70 border border-gray-700 rounded-lg px-3 py-1.5">Steam-синк отключен</span>
            `;
        const sessionsAction = game.sync_type === 'steam'
            ? `
                            <button id="syncSteamManualBtn" class="bg-gray-700/80 hover:bg-gray-600 text-xs px-3 py-1.5 rounded-lg text-white transition-colors flex items-center gap-1.5 border border-gray-600">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                <span class="hidden sm:inline">Ручная синхронизация Steam</span>
                            </button>
            `
            : '';
        const agentPanel = `
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50">
                        <div class="flex items-start justify-between gap-4 mb-4">
                            <div>
                                <h2 class="text-xl font-bold flex items-center gap-2">
                                    <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                                    Настройка агента
                                </h2>
                                <p class="text-sm text-gray-400 mt-1">Укажите полный путь к exe-файлу. Агент ведет реальные игровые сессии для Steam и Non-Steam игр.</p>
                            </div>
                            <span class="text-xs text-gray-500 bg-gray-900/70 border border-gray-700 rounded-lg px-3 py-1.5">${game.launch_path ? `PATH: ${game.launch_path}` : 'Путь не задан'}</span>
                        </div>
                        <div class="flex flex-col sm:flex-row gap-3">
                            <input id="agentLaunchPathInput" type="text" value="${game.launch_path || ''}" placeholder="C:\\Games\\Game\\game.exe" class="flex-grow bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all placeholder-gray-500">
                            <button id="saveAgentConfigBtn" class="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-3 rounded-xl transition-colors">Сохранить путь</button>
                            <button id="testAgentBtn" class="bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-3 rounded-xl transition-colors">Проверить агент</button>
                        </div>
                    </div>
            `;
        
        container.innerHTML = `
            <!-- Top Hero Banner -->
            <div class="relative w-full h-64 md:h-80 lg:h-96 rounded-3xl overflow-hidden mb-8 shadow-2xl ring-1 ring-white/10 group">
                <!-- Blurred background image -->
                <div class="absolute inset-0 z-0">
                    <img src="${cover}" class="w-full h-full object-cover opacity-30 blur-xl scale-110 object-top" />
                </div>
                <!-- Gradient overlay -->
                <div class="absolute inset-0 z-10 bg-gradient-to-t from-gray-900 via-gray-900/80 to-transparent"></div>
                
                <div class="absolute inset-0 z-20 flex items-end p-6 md:p-10">
                    <div class="flex flex-col md:flex-row items-start md:items-end gap-6 w-full">
                        <!-- Cover Image shadow-drop -->
                        <div class="w-32 md:w-48 lg:w-56 aspect-[3/4] rounded-xl overflow-hidden shadow-[0_20px_40px_rgba(0,0,0,0.6)] ring-1 ring-white/20 shrink-0 transform group-hover:-translate-y-2 transition-transform duration-500">
                            <img src="${cover}" alt="${game.title}" class="w-full h-full object-cover" />
                        </div>
                        
                        <div class="flex-grow pb-2 w-full">
                            <div class="flex justify-between items-start w-full">
                                <div>
                                    <div class="flex flex-wrap gap-2 mb-3">
                                        <span class="bg-blue-600/20 text-blue-400 border border-blue-500/30 text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide backdrop-blur-sm">
                                            ${statusLabel(game.status)}
                                        </span>
                                        <span class="${syncTypeBadgeClass} text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide backdrop-blur-sm">${syncTypeLabel}</span>
                                    </div>
                                    <h1 class="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-2 tracking-tight drop-shadow-lg">${game.title}</h1>
                                    <div class="flex flex-wrap items-center gap-2 mt-2">
                                        ${(game.genres || []).map((genre) => `<span class="text-[10px] px-2 py-1 rounded-full bg-gray-900/70 border border-gray-700 text-gray-300">${escapeHtml(genre)}</span>`).join('')}
                                        ${(game.genres || []).length === 0 ? '<span class="text-[11px] text-gray-400">Жанры не найдены</span>' : ''}
                                    </div>
                                </div>
                                <div class="hidden md:flex flex-col items-end backdrop-blur-md bg-black/30 p-4 rounded-2xl border border-white/10 shadow-xl">
                                    <span class="text-gray-400 text-sm font-medium mb-1">Сыграно времени</span>
                                    <span class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400"><span id="playtimeHero">${(game.total_playtime_minutes / 60).toFixed(1)}</span> <span class="text-xl text-gray-500 font-normal">часов</span></span>
                                    <div id="ratingStarsDesktop" class="mt-3 flex items-center gap-1">
                                        ${[1, 2, 3, 4, 5].map((star) => `
                                            <button type="button" class="rate-star text-lg ${star <= (game.personal_rating || 0) ? 'text-amber-300' : 'text-gray-600 hover:text-amber-200'}" data-value="${star}" title="Оценка ${star} из 5">★</button>
                                        `).join('')}
                                    </div>
                                    <div class="mt-4 flex gap-2 w-full">
                                        <button id="playGameBtn" class="flex-grow bg-white/10 hover:bg-white/20 text-white transition-colors border border-white/10 px-4 py-2 rounded-lg text-sm flex items-center justify-center gap-2">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                            Играть
                                        </button>
                                        <button id="deleteGameBtn" class="bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 px-3 py-2 rounded-lg transition-all" title="Удалить игру">
                                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Content Grid Layout -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 pb-12">
                <!-- Main Content (Left, spans 2) -->
                <div class="lg:col-span-2 space-y-8">
                    ${agentPanel}
                    <!-- Progress Section -->
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50">
                        <div class="flex justify-between items-center mb-6">
                            <h2 class="text-2xl font-bold flex items-center gap-2">
                                <svg class="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                Квесты и миссии
                            </h2>
                            <button id="openQuestActionsBtn" class="w-9 h-9 rounded-lg border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 text-xl leading-none transition-colors" title="Добавить задачу или категорию">+</button>
                        </div>

                        <div class="space-y-4 mb-8">
                            <div>
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-sm text-gray-300">Прогресс</span>
                                    <span id="questProgressText" class="text-xs font-medium text-gray-400 bg-gray-900 px-2.5 py-1 rounded-full border border-gray-700">0%</span>
                                </div>
                                <div class="w-full bg-gray-900 rounded-full h-3 overflow-hidden border border-gray-800">
                                    <div id="questProgressBar" class="bg-gradient-to-r from-emerald-500 to-green-400 h-3 rounded-full transition-all duration-1000 w-[0%]"></div>
                                </div>
                            </div>
                        </div>

                        <div id="checklistContainer">
                            <div class="animate-pulse h-10 bg-gray-700/50 rounded w-full mb-2"></div>
                            <div class="animate-pulse h-10 bg-gray-700/50 rounded w-full"></div>
                        </div>
                    </div>

                    ${game.sync_type === 'steam' ? `
                    <!-- Achievements Section -->
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50 flex flex-col min-h-[250px] relative overflow-hidden group">
                        <div class="absolute inset-0 bg-gradient-to-br from-blue-900/10 to-purple-900/10 z-0"></div>
                        <div class="relative z-10 flex justify-between items-center mb-6">
                            <h3 class="text-xl font-bold text-gray-300 flex items-center gap-2">
                                <svg class="w-6 h-6 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"></path></svg>
                                ${achievementsTitle}
                            </h3>
                            ${achievementsAction}
                        </div>
                        <div class="relative z-10 mb-5">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-sm text-gray-300">Прогресс достижений</span>
                                <span id="achievementProgressText" class="text-xs font-medium text-gray-400 bg-gray-900 px-2.5 py-1 rounded-full border border-gray-700">0%</span>
                            </div>
                            <div class="w-full bg-gray-900 rounded-full h-3 overflow-hidden border border-gray-800">
                                <div id="achievementProgressBar" class="bg-gradient-to-r from-amber-500 to-yellow-400 h-3 rounded-full transition-all duration-1000 w-[0%]"></div>
                            </div>
                        </div>
                        <div id="achievementsContainer" class="relative z-10 grid grid-cols-2 sm:grid-cols-3 gap-4 overflow-y-auto max-h-[300px] pr-2 scrollbar-thin scrollbar-thumb-gray-700">
                            <!-- empty / loaded content -->
                            <div class="animate-pulse h-20 bg-gray-700/30 rounded-xl col-span-2 sm:col-span-3"></div>
                        </div>
                    </div>
                    ` : ''}
                </div>

                <!-- Sidebar (Right) -->
                <div class="space-y-6">
                    <!-- Mobile actions (hidden on md) -->
                    <div class="md:hidden flex gap-3 mb-6">
                        <div class="bg-gray-800 border border-gray-700 p-4 rounded-xl flex-1 text-center">
                            <div class="text-gray-400 text-sm mb-1">Сыграно</div>
                            <div id="playtimeMobile" class="text-xl font-bold">${(game.total_playtime_minutes / 60).toFixed(1)} ч.</div>
                            <div id="ratingStarsMobile" class="mt-2 flex items-center justify-center gap-1">
                                ${[1, 2, 3, 4, 5].map((star) => `
                                    <button type="button" class="rate-star text-base ${star <= (game.personal_rating || 0) ? 'text-amber-300' : 'text-gray-600 hover:text-amber-200'}" data-value="${star}" title="Оценка ${star} из 5">★</button>
                                `).join('')}
                            </div>
                        </div>
                        <div class="flex gap-2 flex-1">
                            <button id="playGameBtnMobile" class="bg-blue-600 text-white rounded-xl flex-grow font-medium flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20">
                                Играть
                            </button>
                            <button id="deleteGameBtnMobile" class="bg-red-500/10 text-red-400 border border-red-500/20 p-4 rounded-xl">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            </button>
                        </div>
                    </div>

                    <!-- History Section -->
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50 flex flex-col">
                        <div class="flex justify-between items-center mb-4 gap-2 pb-4 border-b border-gray-700/50">
                            <h2 class="text-xl font-bold flex items-center gap-2">
                                <svg class="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                История сессий
                            </h2>
                            ${sessionsAction}
                        </div>
                        <div id="sessionsContainer" class="space-y-3 max-h-[300px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-gray-700">
                             <div class="animate-pulse h-12 bg-gray-700/30 rounded-lg"></div>
                        </div>
                    </div>

                    <!-- Notes Section -->
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50 h-[600px] flex flex-col">
                        <h2 class="text-xl font-bold mb-4 flex items-center gap-2 pb-4 border-b border-gray-700/50">
                            <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                            Дневник / Заметки
                        </h2>
                        
                        <div id="notesContainer" class="flex-grow overflow-y-auto pr-2 space-y-4 mb-4 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent">
                            <div class="animate-pulse h-20 bg-gray-700/30 rounded-xl mb-3"></div>
                        </div>

                        <form id="addNoteForm" class="mt-auto relative" novalidate>
                            <textarea id="newNoteText" rows="3" class="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all placeholder-gray-500 resize-none pb-12" placeholder="Добавьте мысль, решение загадки..." required></textarea>
                            <button type="submit" class="absolute bottom-3 right-3 bg-blue-600 hover:bg-blue-500 text-white p-2 rounded-lg transition-colors">
                                <svg class="w-4 h-4" transform="rotate(45)" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        `;

        await Promise.all([
            loadChecklists(gameId),
            game.sync_type === 'steam' ? loadAchievements(gameId) : Promise.resolve(),
            loadNotes(gameId),
            loadHistory(gameId),
            updateProgressBar(gameId)
        ]);

        // Bindings
        document.getElementById('openQuestActionsBtn')?.addEventListener('click', async () => {
            try {
                await openQuestActionsModal(gameId, async () => {
                    await loadChecklists(gameId);
                    await updateProgressBar(gameId);
                });
            } catch (err: any) {
                showNotification(err?.message || 'Не удалось открыть окно действий.', 'error');
            }
        });

        document.getElementById('syncAchievementsBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = 'Загрузка...';
            try {
                const results = await api.syncSteamAchievements(gameId);
                if (results.length === 0) {
                    const settings = await api.getSettings();
                    if (!settings.steam_api_key || !settings.steam_user_id) {
                        showNotification('Сначала настройте Steam API Key и профиль в Настройках.', 'info');
                    } else {
                        showNotification('Не удалось получить достижения. Убедитесь, что ваш профиль Steam открыт (Public), или у игры нет достижений.', 'error');
                    }
                }

                await loadAchievements(gameId);
                await updateProgressBar(gameId);
            } catch (err) {
                showNotification('Ошибка при синхронизации со Steam. Проверьте настройки API Key и доступ к интернету.', 'error');
            } finally {
                btn.innerHTML = originalHTML;
            }
        });

        document.getElementById('syncSteamManualBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = 'Синхронизация...';
            btn.disabled = true;
            try {
                const result = await api.syncSteamManual(gameId);
                const updatedGame = await api.getGame(gameId);
                const heroEl = document.getElementById('playtimeHero');
                const mobileEl = document.getElementById('playtimeMobile');
                const playtimeHours = (updatedGame.total_playtime_minutes / 60).toFixed(1);

                if (heroEl) heroEl.innerText = playtimeHours;
                if (mobileEl) mobileEl.innerText = `${playtimeHours} ч.`;

                await loadHistory(gameId);
                if (result.added_minutes > 0) {
                    showNotification(`Добавлено ${result.added_minutes} мин. из Steam`, 'success');
                } else {
                    showNotification('Новых минут в Steam не найдено', 'info');
                }
            } catch (err) {
                showNotification('Ошибка ручной синхронизации Steam.', 'error');
            } finally {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });

        document.getElementById('saveAgentConfigBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const input = document.getElementById('agentLaunchPathInput') as HTMLInputElement;
            const launchPath = input.value.trim();

            if (!launchPath) {
                showNotification('Введите путь к exe-файлу.', 'info');
                return;
            }

            const originalText = btn.textContent;
            btn.textContent = 'Сохранение...';
            btn.disabled = true;
            try {
                await api.configureAgent(gameId, launchPath, true);
                await renderGamePage(container, gameId);
            } catch (err: any) {
                showNotification(err.message || 'Ошибка настройки агента.', 'error');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });

        document.getElementById('testAgentBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const originalText = btn.textContent;
            btn.textContent = 'Проверка...';
            btn.disabled = true;

            try {
                const result = await api.testAgentPing(gameId);
                showNotification(result.message, result.ok ? 'success' : 'info');
                const updatedGame = await api.getGame(gameId);
                const heroEl = document.getElementById('playtimeHero');
                const mobileEl = document.getElementById('playtimeMobile');
                const playtimeHours = (updatedGame.total_playtime_minutes / 60).toFixed(1);

                if (heroEl) heroEl.innerText = playtimeHours;
                if (mobileEl) mobileEl.innerText = `${playtimeHours} ч.`;

                await loadHistory(gameId);
            } catch (err: any) {
                showNotification(err.message || 'Ошибка проверки связи с агентом.', 'error');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });

        container.querySelectorAll('.rate-star').forEach((starBtn) => {
            starBtn.addEventListener('click', async (e) => {
                const value = Number((e.currentTarget as HTMLElement).getAttribute('data-value') || '0');
                if (!value || value < 1 || value > 5) return;
                try {
                    game = await api.updateGame(gameId, { personal_rating: value });
                    const currentRating = game.personal_rating || 0;
                    container.querySelectorAll('.rate-star').forEach((btn) => {
                        const button = btn as HTMLButtonElement;
                        const buttonValue = Number(button.getAttribute('data-value') || '0');
                        button.classList.toggle('text-amber-300', buttonValue <= currentRating);
                        button.classList.toggle('text-gray-600', buttonValue > currentRating);
                    });
                    showNotification(`Оценка: ${value} из 5`, 'success');
                } catch (err: any) {
                    showNotification(err.message || 'Не удалось сохранить оценку.', 'error');
                }
            });
        });

        document.getElementById('addNoteForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const textInput = document.getElementById('newNoteText') as HTMLTextAreaElement;
            const noteText = textInput.value.trim();
            if (!noteText) {
                showNotification('Введите текст заметки.', 'info');
                textInput.focus();
                return;
            }
            await api.createNote(gameId, { text: noteText });
            textInput.value = '';
            loadNotes(gameId);
        });

        const deleteHandler = async () => {
            const confirmed = await showConfirmDialog({
                title: 'Удалить игру?',
                message: `Вы уверены, что хотите полностью удалить игру "${game.title}"? Это действие необратимо и удалит все заметки и прогресс.`,
                confirmText: 'Удалить',
                cancelText: 'Отмена',
                danger: true
            });
            if (!confirmed) {
                return;
            }

            try {
                await api.deleteGame(gameId);
                window.location.hash = '#library';
            } catch (err) {
                showNotification('Ошибка при удалении игры', 'error');
            }
        };

        document.getElementById('deleteGameBtn')?.addEventListener('click', deleteHandler);
        document.getElementById('deleteGameBtnMobile')?.addEventListener('click', deleteHandler);

        const playHandler = async () => {
            if (game.sync_type === 'steam') {
                if (!game.steam_app_id) {
                    showNotification('Для этой Steam-игры не указан App ID.', 'error');
                    return;
                }

                const steamRunUrl = `steam://run/${game.steam_app_id}`;
                window.location.href = steamRunUrl;
                showNotification('Отправлена команда запуска в Steam.', 'info');
                return;
            }

            try {
                const result = await api.requestAgentLaunch(gameId);
                showNotification(result.message, 'success');
            } catch (err: any) {
                showNotification(err.message || 'Не удалось отправить команду запуска агенту.', 'error');
            }
        };

        document.getElementById('playGameBtn')?.addEventListener('click', playHandler);
        document.getElementById('playGameBtnMobile')?.addEventListener('click', playHandler);

    } catch (e) {
        container.innerHTML = `<div class="text-center py-20 text-red-400"><h1>Игра не найдена</h1><a href="#library" class="text-blue-400 underline mt-4 block">В библиотеку</a></div>`;
    }
}

async function loadChecklists(gameId: number) {
    const [list, categories] = await Promise.all([
        api.getChecklist(gameId),
        api.getChecklistCategories(gameId)
    ]);
    const container = document.getElementById('checklistContainer')!;
    container.innerHTML = '';
    hydrateChecklistCategoryOptions(categories);

    // Grouping by category
    const groups: { [key: string]: typeof list } = {};
    list.forEach(item => {
        const cat = item.category || 'Общее';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(item);
    });

    categories.forEach((category) => {
        if (!groups[category.name]) {
            groups[category.name] = [];
        }
    });

    if (Object.keys(groups).length === 0) {
        container.innerHTML = '<div class="text-gray-500 text-center py-4 text-sm bg-gray-900/50 rounded-lg">Список задач пуст</div>';
        return;
    }

    // Render each group
    Object.keys(groups).sort().forEach(cat => {
        const items = groups[cat];
        const completedCount = items.filter(i => i.completed).length;
        const percent = items.length === 0 ? 0 : Math.round((completedCount / items.length) * 100);
        const safeCategory = escapeHtml(cat);
        
        const catEl = document.createElement('details');
        catEl.className = "mb-3 group/cat bg-gray-900/40 rounded-xl border border-gray-800/50 overflow-hidden open:border-emerald-500/30 transition-all";
        // Open by default if some are unchecked, or if it's the only category
        if (completedCount < items.length || Object.keys(groups).length === 1) {
            catEl.open = true;
        }

        catEl.innerHTML = `
            <summary class="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-800/50 transition-colors list-none select-none group/sum">
                <div class="flex items-center gap-3">
                    <svg class="w-4 h-4 text-emerald-500 group-open/cat:rotate-90 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path></svg>
                    <span class="font-bold text-sm uppercase tracking-wider text-gray-300">${safeCategory}</span>
                    <span class="text-[10px] bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full font-mono">${completedCount}/${items.length}</span>
                </div>
                <div class="flex items-center gap-4">
                    <div class="hidden sm:block h-1.5 w-24 bg-gray-800 rounded-full overflow-hidden border border-gray-700/50">
                        <div class="h-full bg-emerald-500 transition-all duration-500" style="width: ${percent}%"></div>
                    </div>
                    <span class="text-[10px] font-bold text-gray-600 w-8 text-right">${percent}%</span>
                    <button data-cat="${safeCategory}" class="rename-cat-btn p-1.5 text-gray-600 hover:text-blue-400 opacity-0 group-hover/sum:opacity-100 transition-opacity" title="Переименовать категорию">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                    </button>
                    <button data-cat="${safeCategory}" class="delete-cat-btn p-1.5 text-gray-600 hover:text-red-400 opacity-0 group-hover/sum:opacity-100 transition-opacity ml-2" title="Удалить всю категорию">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                </div>
            </summary>
            <div class="p-4 pt-0 space-y-2 border-t border-gray-800/30 mt-1">
                ${items.length === 0 ? '<div class="text-xs text-gray-500 italic py-2">В категории пока нет задач</div>' : items.map(item => `
                    <div class="flex items-center gap-3 p-3 rounded-lg transition-all group/item ${item.completed ? 'bg-gray-900/40 text-gray-500 opacity-60' : 'bg-gray-800/60 border border-gray-700/50 hover:border-gray-600'}">
                        <div class="relative flex items-center shrink-0">
                            <input type="checkbox" ${item.completed ? 'checked' : ''} data-id="${item.id}" class="checklist-box w-5 h-5 bg-gray-950 border-2 border-gray-700 rounded cursor-pointer appearance-none checked:bg-emerald-600 checked:border-emerald-600 transition-colors">
                            <svg class="w-3.5 h-3.5 text-white absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none opacity-0 ${item.completed ? 'opacity-100' : ''}" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round"></path></svg>
                        </div>
                        <span class="${item.completed ? 'line-through decoration-gray-600' : ''} text-sm flex-grow">${escapeHtml(item.title)}</span>
                        <button data-id="${item.id}" class="delete-item-btn p-1 text-gray-600 hover:text-red-400 opacity-0 group-hover/item:opacity-100 transition-opacity" title="Удалить задачу">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
        container.appendChild(catEl);
    });

    // Checkbox events
    container.querySelectorAll('.checklist-box').forEach(box => {
        box.addEventListener('change', async (e) => {
            const el = e.target as HTMLInputElement;
            const id = parseInt(el.getAttribute('data-id')!);
            await api.completeChecklistItem(id, el.checked);
            await loadChecklists(gameId);
            updateProgressBar(gameId);
        });
    });

    // Category delete events
    container.querySelectorAll('.rename-cat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const oldName = (e.currentTarget as HTMLButtonElement).getAttribute('data-cat') || '';
            if (!oldName) return;
            const newName = window.prompt(`Новое имя для категории "${oldName}":`, oldName);
            if (!newName || !newName.trim() || newName.trim() === oldName) return;
            try {
                await api.renameChecklistCategory(gameId, oldName, newName.trim());
                await loadChecklists(gameId);
            } catch (err: any) {
                showNotification(err.message || 'Не удалось переименовать категорию.', 'error');
            }
        });
    });

    container.querySelectorAll('.delete-cat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const el = e.currentTarget as HTMLButtonElement;
            const cat = el.getAttribute('data-cat')!;
            const confirmed = await showConfirmDialog({
                title: 'Удалить категорию?',
                message: `Удалить ВСЕ задачи в категории "${cat}"?`,
                confirmText: 'Удалить всё',
                cancelText: 'Отмена',
                danger: true
            });
            if (confirmed) {
                await api.deleteChecklistCategory(gameId, cat);
                await loadChecklists(gameId);
                updateProgressBar(gameId);
            }
        });
    });

    // Delete events
    container.querySelectorAll('.delete-item-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const el = e.currentTarget as HTMLButtonElement;
            const id = parseInt(el.getAttribute('data-id')!);
            const confirmed = await showConfirmDialog({
                title: 'Удалить задачу?',
                message: 'Удалить эту задачу?',
                confirmText: 'Удалить',
                cancelText: 'Отмена',
                danger: true
            });
            if (confirmed) {
                await api.deleteChecklistItem(id);
                await loadChecklists(gameId);
                updateProgressBar(gameId);
            }
        });
    });
}

function hydrateChecklistCategoryOptions(categories: QuestCategory[]) {
    const categorySelect = document.getElementById('newTaskCategory') as HTMLSelectElement | null;
    if (!categorySelect) return;
    const sorted = [...categories].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    categorySelect.innerHTML = '';
    sorted.forEach((category) => {
        const option = document.createElement('option');
        option.value = category.name;
        option.textContent = category.name;
        categorySelect.appendChild(option);
    });
}

async function loadNotes(gameId: number) {
    const container = document.getElementById('notesContainer')!;
    try {
        const notes = await api.getNotes(gameId);
        container.innerHTML = '';

    if (notes.length === 0) {
         container.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-gray-500 opacity-70 mt-10">
                <svg class="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                <span class="text-sm">Нет записей</span>
            </div>
         `;
         return;
    }

    notes.forEach(note => {
        const date = new Date(note.created_at).toLocaleDateString('ru-RU', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const el = document.createElement('div');
        el.className = "bg-gray-900 p-4 rounded-xl border border-gray-800 shadow-sm relative group";
        el.innerHTML = `
            <div class="text-xs text-blue-400/70 font-medium mb-2">${date}</div>
            <div class="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">${note.text}</div>
            <button data-id="${note.id}" class="delete-note-btn absolute top-3 right-3 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
        `;
        container.appendChild(el);
    });

    container.querySelectorAll('.delete-note-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const el = e.currentTarget as HTMLButtonElement;
            const id = parseInt(el.getAttribute('data-id')!);
            const confirmed = await showConfirmDialog({
                title: 'Удалить заметку?',
                message: 'Удалить эту заметку?',
                confirmText: 'Удалить',
                cancelText: 'Отмена',
                danger: true
            });
            if (confirmed) {
                try {
                    await api.deleteNote(id);
                    await loadNotes(gameId);
                } catch (err) {
                    showNotification('Ошибка при удалении заметки', 'error');
                }
            }
        });
    });
    } catch (err) {
        console.error('Failed to load notes:', err);
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full text-red-400 opacity-70 mt-10">
                <svg class="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                <span class="text-sm">Ошибка загрузки заметок</span>
            </div>
        `;
    }
}

async function loadAchievements(gameId: number) {
    const [game, achievements] = await Promise.all([
        api.getGame(gameId),
        api.getAchievements(gameId)
    ]);
    const container = document.getElementById('achievementsContainer');
    if (!container) {
        return;
    }
    container.innerHTML = '';

    if (game.sync_type !== 'steam') {
        container.innerHTML = '<div class="col-span-2 sm:col-span-3 text-gray-500 text-center py-6 text-sm bg-gray-900/50 rounded-xl border border-gray-800">Для Non-Steam игр Steam-достижения недоступны.</div>';
        return;
    }

    if (achievements.length === 0) {
        container.innerHTML = '<div class="col-span-2 sm:col-span-3 text-gray-500 text-center py-6 text-sm bg-gray-900/50 rounded-xl border border-gray-800">Достижения не синхронизированы</div>';
        return;
    }
    
    achievements.forEach(ach => {
        const el = document.createElement('div');
        const completedOpacity = ach.completed ? 'opacity-100 border-yellow-500/50' : 'opacity-40 grayscale border-gray-700/50';
        el.className = `bg-gray-900/80 overflow-hidden flex flex-col items-center p-3 rounded-xl border transition-all ${completedOpacity}`;
        
        el.innerHTML = `
            <div class="w-12 h-12 rounded-lg bg-black mb-2 flex items-center justify-center overflow-hidden border border-gray-800 shrink-0">
                ${ach.icon_url ? `<img src="${ach.icon_url}" class="w-full h-full object-cover">` : `<svg class="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"></path></svg>`}
            </div>
            <div class="text-center w-full">
                <div class="text-[11px] font-bold text-gray-300 leading-tight mb-0.5 line-clamp-2" title="${ach.name}">${ach.name}</div>
                ${ach.completed ? '<div class="text-[9px] text-yellow-500 uppercase tracking-widest font-bold">Получено</div>' : ''}
            </div>
        `;
        container.appendChild(el);
    });
}

async function updateProgressBar(gameId: number) {
    const [game, checklists, achievements] = await Promise.all([
        api.getGame(gameId),
        api.getChecklist(gameId),
        api.getAchievements(gameId)
    ]);

    const questTotal = checklists.length;
    const questCompleted = checklists.filter(c => c.completed).length;
    const questPercent = questTotal === 0 ? 0 : Math.round((questCompleted / questTotal) * 100);

    const isSteamSync = game.sync_type === 'steam';
    const achievementTotal = isSteamSync ? achievements.length : 0;
    const achievementCompleted = isSteamSync ? achievements.filter(a => a.completed).length : 0;
    const achievementPercent = achievementTotal === 0 ? 0 : Math.round((achievementCompleted / achievementTotal) * 100);

    const questTextEl = document.getElementById('questProgressText');
    const questBarEl = document.getElementById('questProgressBar');
    const achievementTextEl = document.getElementById('achievementProgressText');
    const achievementBarEl = document.getElementById('achievementProgressBar');

    if (questTextEl) questTextEl.innerText = `${questPercent}%`;
    if (questBarEl) questBarEl.style.width = `${questPercent}%`;

    if (achievementTextEl) achievementTextEl.innerText = `${achievementPercent}%`;
    if (achievementBarEl) {
        achievementBarEl.style.width = `${achievementPercent}%`;
        achievementBarEl.style.opacity = '1';
    }
}

async function loadHistory(gameId: number) {
    const sessions = await api.getSessions(gameId);
    const container = document.getElementById('sessionsContainer')!;
    container.innerHTML = '';

    if (sessions.length === 0) {
        container.innerHTML = '<div class="text-gray-500 text-xs text-center py-4 italic">Нет истории сессий</div>';
        return;
    }

    sessions.forEach(session => {
        const date = new Date(session.started_at).toLocaleDateString('ru-RU', { month: 'short', day: 'numeric' });
        const time = new Date(session.started_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        const isSteamManual = session.source === 'steam_manual_sync' || session.source === 'steam_sync';
        const isAgent = session.source === 'agent';
        
        const el = document.createElement('div');
        el.className = "flex items-center justify-between p-3 bg-gray-900/60 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors group";
        
        const sourceIcon = isSteamManual
            ? '<svg class="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>'
            : '<svg class="w-3 h-3 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path></svg>';

        el.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-lg bg-gray-800 flex items-center justify-center border border-gray-700 group-hover:bg-gray-700 transition-colors">
                    ${sourceIcon}
                </div>
                <div>
                    <div class="text-[11px] font-bold text-gray-400 uppercase tracking-wider">${date} <span class="text-gray-600 ml-1 opacity-50 font-normal lowercase">${time}</span></div>
                    <div class="text-xs text-gray-200 font-medium">
                        ${isSteamManual ? 'Ручная синхронизация Steam' : (isAgent ? 'Сессия через агент' : `Сессия (${session.source})`)}
                    </div>
                </div>
            </div>
            <div class="text-right">
                <div class="text-[10px] text-gray-500 font-bold mb-0.5">+${session.duration_minutes} мин.</div>
                <div class="text-[9px] px-1.5 py-0.5 rounded bg-black/40 text-gray-600 border border-gray-800 font-bold uppercase tracking-tight capitalize">${isAgent ? 'агент' : (isSteamManual ? 'ручной sync' : session.source)}</div>
            </div>
        `;
        container.appendChild(el);
    });
}

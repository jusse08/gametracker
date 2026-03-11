import { api } from '../api';

export async function renderGamePage(container: HTMLElement, gameId: number) {
    container.innerHTML = `
        <div class="flex items-center justify-center min-h-[50vh]">
            <div class="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
        </div>
    `;

    try {
        const game = await api.getGame(gameId);
        const cover = game.cover_url || 'https://via.placeholder.com/300x400/1f2937/4b5563?text=Нет+обложки';
        const syncTypeLabel = game.sync_type === 'steam' ? 'Steam' : 'Агент';
        const syncTypeBadgeClass = game.sync_type === 'steam'
            ? 'bg-sky-500/15 text-sky-300 border border-sky-400/30'
            : 'bg-emerald-500/15 text-emerald-300 border border-emerald-400/30';
        const achievementsTitle = game.sync_type === 'steam' ? 'Достижения Steam' : 'Синхронизация через агент';
        const achievementsAction = game.sync_type === 'steam'
            ? `
                            <button id="syncSteamBtn" class="bg-gray-700/80 hover:bg-gray-600 text-xs px-3 py-1.5 rounded-lg text-white transition-colors flex items-center gap-1.5 border border-gray-600">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                <span class="hidden sm:inline">Синхронизировать</span>
                            </button>
            `
            : `
                            <span class="text-xs text-gray-500 bg-gray-900/70 border border-gray-700 rounded-lg px-3 py-1.5">Steam-синк отключен</span>
            `;
        const agentPanel = game.sync_type === 'agent'
            ? `
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50">
                        <div class="flex items-start justify-between gap-4 mb-4">
                            <div>
                                <h2 class="text-xl font-bold flex items-center gap-2">
                                    <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
                                    Настройка агента
                                </h2>
                                <p class="text-sm text-gray-400 mt-1">Укажите имя процесса для отслеживания этой игры.</p>
                            </div>
                            <span class="text-xs text-gray-500 bg-gray-900/70 border border-gray-700 rounded-lg px-3 py-1.5">${game.exe_name ? `EXE: ${game.exe_name}` : 'EXE не задан'}</span>
                        </div>
                        <div class="flex flex-col sm:flex-row gap-3">
                            <input id="agentExeNameInput" type="text" value="${game.exe_name || ''}" placeholder="game.exe" class="flex-grow bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all placeholder-gray-500">
                            <button id="saveAgentConfigBtn" class="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-3 rounded-xl transition-colors">Сохранить exe</button>
                            <button id="testAgentBtn" class="bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-3 rounded-xl transition-colors">Проверить агент</button>
                        </div>
                    </div>
            `
            : '';
        
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
                                            ${game.status === 'playing' ? 'Играю' : game.status === 'backlog' ? 'Запланировано' : game.status === 'completed' ? 'Пройдено' : game.status}
                                        </span>
                                        <span class="${syncTypeBadgeClass} text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide backdrop-blur-sm">${syncTypeLabel}</span>
                                    </div>
                                    <h1 class="text-4xl md:text-5xl lg:text-6xl font-bold text-white mb-2 tracking-tight drop-shadow-lg">${game.title}</h1>
                                </div>
                                <div class="hidden md:flex flex-col items-end backdrop-blur-md bg-black/30 p-4 rounded-2xl border border-white/10 shadow-xl">
                                    <span class="text-gray-400 text-sm font-medium mb-1">Сыграно времени</span>
                                    <span class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400"><span id="playtimeHero">${(game.total_playtime_minutes / 60).toFixed(1)}</span> <span class="text-xl text-gray-500 font-normal">часов</span></span>
                                    <div class="mt-4 flex gap-2 w-full">
                                        <button class="flex-grow bg-white/10 hover:bg-white/20 text-white transition-colors border border-white/10 px-4 py-2 rounded-lg text-sm flex items-center justify-center gap-2">
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
                                Прогресс выполнения
                            </h2>
                        </div>

                        <div class="space-y-4 mb-8">
                            <div>
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-sm text-gray-300">Квесты</span>
                                    <span id="questProgressText" class="text-xs font-medium text-gray-400 bg-gray-900 px-2.5 py-1 rounded-full border border-gray-700">0%</span>
                                </div>
                                <div class="w-full bg-gray-900 rounded-full h-3 overflow-hidden border border-gray-800">
                                    <div id="questProgressBar" class="bg-gradient-to-r from-emerald-500 to-green-400 h-3 rounded-full transition-all duration-1000 w-[0%]"></div>
                                </div>
                            </div>

                            ${game.sync_type === 'steam' ? `
                            <div>
                                <div class="flex items-center justify-between mb-2">
                                    <span class="text-sm text-gray-300">Ачивки</span>
                                    <span id="achievementProgressText" class="text-xs font-medium text-gray-400 bg-gray-900 px-2.5 py-1 rounded-full border border-gray-700">0%</span>
                                </div>
                                <div class="w-full bg-gray-900 rounded-full h-3 overflow-hidden border border-gray-800">
                                    <div id="achievementProgressBar" class="bg-gradient-to-r from-amber-500 to-yellow-400 h-3 rounded-full transition-all duration-1000 w-[0%]"></div>
                                </div>
                            </div>
                            ` : ''}
                        </div>

                        <div id="checklistContainer">
                            <div class="animate-pulse h-10 bg-gray-700/50 rounded w-full mb-2"></div>
                            <div class="animate-pulse h-10 bg-gray-700/50 rounded w-full"></div>
                        </div>

                        <!-- Add Task Form -->
                        <form id="addChecklistForm" class="mt-4 flex gap-2 pt-4 border-t border-gray-700/50">
                            <input type="text" id="newTaskTitle" class="flex-grow bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all placeholder-gray-500" placeholder="Новая задача / миссия..." required>
                            <button type="submit" class="bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 border border-emerald-500/30 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors">
                                Добавить
                            </button>
                        </form>

                        <!-- Import Wiki Form -->
                        <form id="importWikiForm" class="mt-2 flex gap-2">
                            <input type="url" id="wikiUrlInput" class="flex-grow bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all placeholder-gray-500" placeholder="Импорт задач из Wiki (URL)..." required>
                            <button type="submit" class="bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 border border-blue-500/30 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap">
                                <span class="hidden sm:inline">Импорт с </span>Wiki
                            </button>
                        </form>
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
                        </div>
                        <div class="flex gap-2 flex-1">
                            <button class="bg-blue-600 text-white rounded-xl flex-grow font-medium flex items-center justify-center gap-2 shadow-lg shadow-blue-500/20">
                                Играть
                            </button>
                            <button id="deleteGameBtnMobile" class="bg-red-500/10 text-red-400 border border-red-500/20 p-4 rounded-xl">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            </button>
                        </div>
                    </div>

                    <!-- History Section -->
                    <div class="bg-gray-800/50 rounded-2xl p-6 border border-gray-700/50 flex flex-col">
                        <h2 class="text-xl font-bold mb-4 flex items-center gap-2 pb-4 border-b border-gray-700/50">
                            <svg class="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            История сессий
                        </h2>
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

                        <form id="addNoteForm" class="mt-auto relative">
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
        document.getElementById('importWikiForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const urlInput = document.getElementById('wikiUrlInput') as HTMLInputElement;
            const btn = (e.currentTarget as HTMLFormElement).querySelector('button');
            const originalText = btn?.innerHTML || 'Импорт';
            if (btn) btn.innerHTML = 'Загрузка...';
            
            try {
                await api.importWikiChecklist(gameId, urlInput.value);
                urlInput.value = '';
                await loadChecklists(gameId);
                await updateProgressBar(gameId);
            } catch (err) {
                alert('Ошибка при импорте из Wiki');
            } finally {
                if (btn) btn.innerHTML = originalText;
            }
        });

        document.getElementById('syncSteamBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = 'Загрузка...';
            try {
                const results = await api.syncSteamAchievements(gameId);
                if (results.length === 0) {
                    const settings = await api.getSettings();
                    if (!settings.steam_api_key || !settings.steam_user_id) {
                        alert('Сначала настройте Steam API Key и профиль в Настройках.');
                    } else {
                        alert('Не удалось получить достижения. Убедитесь, что ваш профиль Steam открыт (Public), или у игры нет достижений.');
                    }
                }

                const updatedGame = await api.getGame(gameId);

                const heroEl = document.getElementById('playtimeHero');
                const mobileEl = document.getElementById('playtimeMobile');
                const playtimeHours = (updatedGame.total_playtime_minutes / 60).toFixed(1);

                if (heroEl) heroEl.innerText = playtimeHours;
                if (mobileEl) mobileEl.innerText = `${playtimeHours} ч.`;

                await loadAchievements(gameId);
                await updateProgressBar(gameId);
            } catch (err) {
                alert('Ошибка при синхронизации со Steam. Проверьте настройки API Key и доступ к интернету.');
            } finally {
                btn.innerHTML = originalHTML;
            }
        });

        document.getElementById('saveAgentConfigBtn')?.addEventListener('click', async (e) => {
            const btn = e.currentTarget as HTMLButtonElement;
            const input = document.getElementById('agentExeNameInput') as HTMLInputElement;
            const exeName = input.value.trim();

            if (!exeName) {
                alert('Введите имя exe-файла.');
                return;
            }

            const originalText = btn.textContent;
            btn.textContent = 'Сохранение...';
            btn.disabled = true;
            try {
                await api.configureAgent(gameId, exeName, true);
                await renderGamePage(container, gameId);
            } catch (err: any) {
                alert(err.message || 'Ошибка настройки агента.');
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
                alert(result.message);
                const updatedGame = await api.getGame(gameId);
                const heroEl = document.getElementById('playtimeHero');
                const mobileEl = document.getElementById('playtimeMobile');
                const playtimeHours = (updatedGame.total_playtime_minutes / 60).toFixed(1);

                if (heroEl) heroEl.innerText = playtimeHours;
                if (mobileEl) mobileEl.innerText = `${playtimeHours} ч.`;

                await loadHistory(gameId);
            } catch (err: any) {
                alert(err.message || 'Ошибка проверки связи с агентом.');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });

        document.getElementById('addChecklistForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const titleInput = document.getElementById('newTaskTitle') as HTMLInputElement;
            await api.createChecklistItem(gameId, { title: titleInput.value, category: 'General' });
            titleInput.value = '';
            await loadChecklists(gameId);
            updateProgressBar(gameId);
        });

        document.getElementById('addNoteForm')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const textInput = document.getElementById('newNoteText') as HTMLTextAreaElement;
            await api.createNote(gameId, { text: textInput.value });
            textInput.value = '';
            loadNotes(gameId);
        });

        const deleteHandler = async () => {
            if (confirm(`Вы уверены, что хотите полностью удалить игру "${game.title}"? Это действие необратимо и удалит все заметки и прогресс.`)) {
                try {
                    await api.deleteGame(gameId);
                    window.location.hash = '#library';
                } catch (err) {
                    alert('Ошибка при удалении игры');
                }
            }
        };

        document.getElementById('deleteGameBtn')?.addEventListener('click', deleteHandler);
        document.getElementById('deleteGameBtnMobile')?.addEventListener('click', deleteHandler);

    } catch (e) {
        container.innerHTML = `<div class="text-center py-20 text-red-400"><h1>Игра не найдена</h1><a href="#library" class="text-blue-400 underline mt-4 block">В библиотеку</a></div>`;
    }
}

async function loadChecklists(gameId: number) {
    const list = await api.getChecklist(gameId);
    const container = document.getElementById('checklistContainer')!;
    container.innerHTML = '';
    
    if (list.length === 0) {
        container.innerHTML = '<div class="text-gray-500 text-center py-4 text-sm bg-gray-900/50 rounded-lg">Список задач пуст</div>';
        return;
    }

    // Grouping by category
    const groups: { [key: string]: typeof list } = {};
    list.forEach(item => {
        const cat = item.category || 'Общее';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(item);
    });

    // Render each group
    Object.keys(groups).sort().forEach(cat => {
        const items = groups[cat];
        const completedCount = items.filter(i => i.completed).length;
        const percent = Math.round((completedCount / items.length) * 100);
        
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
                    <span class="font-bold text-sm uppercase tracking-wider text-gray-300">${cat}</span>
                    <span class="text-[10px] bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full font-mono">${completedCount}/${items.length}</span>
                </div>
                <div class="flex items-center gap-4">
                    <div class="hidden sm:block h-1.5 w-24 bg-gray-800 rounded-full overflow-hidden border border-gray-700/50">
                        <div class="h-full bg-emerald-500 transition-all duration-500" style="width: ${percent}%"></div>
                    </div>
                    <span class="text-[10px] font-bold text-gray-600 w-8 text-right">${percent}%</span>
                    <button data-cat="${cat}" class="delete-cat-btn p-1.5 text-gray-600 hover:text-red-400 opacity-0 group-hover/sum:opacity-100 transition-opacity ml-2" title="Удалить всю категорию">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    </button>
                </div>
            </summary>
            <div class="p-4 pt-0 space-y-2 border-t border-gray-800/30 mt-1">
                ${items.map(item => `
                    <div class="flex items-center gap-3 p-3 rounded-lg transition-all group/item ${item.completed ? 'bg-gray-900/40 text-gray-500 opacity-60' : 'bg-gray-800/60 border border-gray-700/50 hover:border-gray-600'}">
                        <div class="relative flex items-center shrink-0">
                            <input type="checkbox" ${item.completed ? 'checked' : ''} data-id="${item.id}" class="checklist-box w-5 h-5 bg-gray-950 border-2 border-gray-700 rounded cursor-pointer appearance-none checked:bg-emerald-600 checked:border-emerald-600 transition-colors">
                            <svg class="w-3.5 h-3.5 text-white absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none opacity-0 ${item.completed ? 'opacity-100' : ''}" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round"></path></svg>
                        </div>
                        <span class="${item.completed ? 'line-through decoration-gray-600' : ''} text-sm flex-grow">${item.title}</span>
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
    container.querySelectorAll('.delete-cat-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const el = e.currentTarget as HTMLButtonElement;
            const cat = el.getAttribute('data-cat')!;
            if (confirm(`Удалить ВСЕ задачи в категории "${cat}"?`)) {
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
            if (confirm('Удалить эту задачу?')) {
                await api.deleteChecklistItem(id);
                await loadChecklists(gameId);
                updateProgressBar(gameId);
            }
        });
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
            if (confirm('Удалить эту заметку?')) {
                try {
                    await api.deleteNote(id);
                    await loadNotes(gameId);
                } catch (err) {
                    alert('Ошибка при удалении заметки');
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
        container.innerHTML = '<div class="col-span-2 sm:col-span-3 text-gray-500 text-center py-6 text-sm bg-gray-900/50 rounded-xl border border-gray-800">Для игр через агент Steam-достижения не синхронизируются.</div>';
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
        
        const el = document.createElement('div');
        el.className = "flex items-center justify-between p-3 bg-gray-900/60 rounded-xl border border-gray-800 hover:border-gray-700 transition-colors group";
        
        const sourceIcon = session.source === 'steam_sync' 
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
                        ${session.source === 'steam_sync' ? 'Синхронизация Steam' : 'Игровая сессия'}
                    </div>
                </div>
            </div>
            <div class="text-right">
                <div class="text-[10px] text-gray-500 font-bold mb-0.5">+${session.duration_minutes} мин.</div>
                <div class="text-[9px] px-1.5 py-0.5 rounded bg-black/40 text-gray-600 border border-gray-800 font-bold uppercase tracking-tight capitalize">${session.source === 'agent' ? 'агент' : (session.source === 'steam_sync' ? 'steam' : session.source)}</div>
            </div>
        `;
        container.appendChild(el);
    });
}

import { api, type Game } from '../api';

function formatPlaytime(minutes: number): string {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h} ч ${m} мин`;
}

function statusLabel(status: string): string {
    if (status === 'playing') return 'Играю';
    if (status === 'completed') return 'Пройдено';
    if (status === 'backlog') return 'Запланировано';
    return status;
}

function compareGames(a: Game, b: Game, sortBy: string): number {
    if (sortBy === 'title-asc') return a.title.localeCompare(b.title, 'ru');
    if (sortBy === 'title-desc') return b.title.localeCompare(a.title, 'ru');
    if (sortBy === 'playtime-asc') return a.total_playtime_minutes - b.total_playtime_minutes;
    if (sortBy === 'playtime-desc') return b.total_playtime_minutes - a.total_playtime_minutes;
    return Date.parse(b.created_at) - Date.parse(a.created_at);
}

function getQuestText(stats: { playing: number; backlog: number; completed: number; totalMinutes: number }): string {
    if (stats.playing === 0 && stats.backlog > 0) {
        return 'Квест дня: выбери игру из бэклога и запусти первую сессию.';
    }
    if (stats.totalMinutes < 300) {
        return 'Квест дня: добей 5 часов общего времени для открытия ранга Scout.';
    }
    if (stats.completed < 3) {
        return 'Квест дня: закрой хотя бы одну игру и пополни зал трофеев.';
    }
    return 'Квест дня: синхронизируй достижения и обнови боевой журнал.';
}

export async function renderLibrary(container: HTMLElement) {
    container.innerHTML = `
        <section class="gt-panel p-5 md:p-7 mb-6 overflow-hidden relative">
            <div class="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                <div class="max-w-3xl">
                    <span class="gt-chip inline-flex mb-4">Командный центр</span>
                    <h1 class="text-3xl md:text-5xl font-bold leading-tight tracking-tight mb-3">Аркадный ангар<br class="hidden sm:block"> вашей библиотеки</h1>
                    <p class="text-slate-300/90 text-sm md:text-base max-w-2xl">Перетаскивай карточки между статусами, следи за прогрессом и прокачивай профиль игровыми сессиями.</p>
                </div>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full lg:w-auto" id="statsDock">
                    <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Всего игр</p><p id="statTotal" class="text-2xl font-bold">-</p></div>
                    <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Играю</p><p id="statPlaying" class="text-2xl font-bold text-cyan-300">-</p></div>
                    <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Пройдено</p><p id="statCompleted" class="text-2xl font-bold text-lime-300">-</p></div>
                    <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Часов</p><p id="statHours" class="text-2xl font-bold text-amber-300">-</p></div>
                </div>
            </div>
        </section>

        <section class="grid grid-cols-1 xl:grid-cols-[1fr_auto] gap-4 mb-5">
            <div class="gt-panel p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                <div class="relative flex-1">
                    <input id="librarySearch" class="gt-input pr-9" type="text" placeholder="Быстрый поиск по библиотеке...">
                    <svg class="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </div>
                <select id="librarySort" class="gt-input w-full sm:w-[240px]">
                    <option value="created-desc">Сначала новые</option>
                    <option value="playtime-desc">По времени (убыв.)</option>
                    <option value="playtime-asc">По времени (возр.)</option>
                    <option value="title-asc">По названию (А-Я)</option>
                    <option value="title-desc">По названию (Я-А)</option>
                </select>
            </div>

            <div class="gt-panel p-4 min-w-[260px]">
                <p class="text-xs text-cyan-200/80 uppercase tracking-[0.15em] mb-2">Daily Quest</p>
                <p id="dailyQuestText" class="text-sm text-slate-200">Синхронизация боевых задач...</p>
            </div>
        </section>

        <section class="mb-4 flex flex-wrap gap-2 bg-slate-900/40 border border-slate-600/30 p-1.5 rounded-2xl w-fit">
            <button class="status-tab px-4 py-2 rounded-xl text-sm font-semibold bg-cyan-500/20 text-cyan-200 border border-cyan-400/30 active-tab" data-status="playing">Играю</button>
            <button class="status-tab px-4 py-2 rounded-xl text-sm font-semibold text-slate-300 hover:bg-slate-700/60 border border-transparent" data-status="backlog">Запланировано</button>
            <button class="status-tab px-4 py-2 rounded-xl text-sm font-semibold text-slate-300 hover:bg-slate-700/60 border border-transparent" data-status="completed">Пройдено</button>
        </section>

        <section id="gamesGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4 lg:gap-5 relative min-h-[420px]"></section>
    `;

    const grid = container.querySelector<HTMLElement>('#gamesGrid')!;
    const searchInput = container.querySelector<HTMLInputElement>('#librarySearch')!;
    const sortSelect = container.querySelector<HTMLSelectElement>('#librarySort')!;
    const questTextEl = container.querySelector<HTMLElement>('#dailyQuestText')!;

    let dragMirror: HTMLElement | null = null;
    let gamesByStatus: Game[] = [];
    let currentStatus = 'playing';
    let searchText = '';
    let sortBy = 'created-desc';

    const transparentImage = new Image();
    transparentImage.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    const onGlobalDragOver = (e: DragEvent) => {
        e.preventDefault();
        if (e.dataTransfer) {
            e.dataTransfer.dropEffect = 'move';
        }
        if (dragMirror) {
            dragMirror.style.left = `${e.clientX}px`;
            dragMirror.style.top = `${e.clientY}px`;
        }
    };

    async function loadGames() {
        grid.innerHTML = `
            <div class="col-span-full absolute inset-0 flex flex-col items-center justify-center">
                <div class="loader-spinner mb-3"></div>
                <p class="text-slate-300/70 text-sm tracking-wide animate-pulse">Сканируем игровой ангар...</p>
            </div>
        `;

        try {
            const [filteredGames, allGames] = await Promise.all([
                api.getGames(currentStatus),
                api.getGames()
            ]);
            gamesByStatus = filteredGames;
            hydrateStats(allGames);
            renderGamesList();
        } catch {
            grid.innerHTML = `<div class="col-span-full text-center py-12 text-rose-300">Ошибка загрузки игр</div>`;
        }
    }

    function hydrateStats(allGames: Game[]) {
        const playing = allGames.filter((g) => g.status === 'playing').length;
        const completed = allGames.filter((g) => g.status === 'completed').length;
        const backlog = allGames.filter((g) => g.status === 'backlog').length;
        const totalMinutes = allGames.reduce((sum, game) => sum + game.total_playtime_minutes, 0);
        const totalHours = (totalMinutes / 60).toFixed(1);

        (container.querySelector('#statTotal') as HTMLElement).textContent = String(allGames.length);
        (container.querySelector('#statPlaying') as HTMLElement).textContent = String(playing);
        (container.querySelector('#statCompleted') as HTMLElement).textContent = String(completed);
        (container.querySelector('#statHours') as HTMLElement).textContent = totalHours;

        questTextEl.textContent = getQuestText({
            playing,
            backlog,
            completed,
            totalMinutes
        });
    }

    function getFilteredGames() {
        const needle = searchText.trim().toLowerCase();
        const filtered = needle
            ? gamesByStatus.filter((game) => game.title.toLowerCase().includes(needle))
            : [...gamesByStatus];

        return filtered.sort((a, b) => compareGames(a, b, sortBy));
    }

    function renderGamesList() {
        const games = getFilteredGames();
        grid.innerHTML = '';

        if (games.length === 0) {
            const emptyMessage = searchText.trim()
                ? 'Ничего не найдено по текущему фильтру.'
                : 'Здесь пока пусто. Добавьте первую игру.';
            grid.innerHTML = `
                <div class="col-span-full gt-panel px-6 py-16 text-center">
                    <p class="text-xl font-semibold mb-2 text-slate-100">${emptyMessage}</p>
                    <p class="text-slate-400 text-sm mb-5">Создайте карточку игры и распределите ее по статусам.</p>
                    <button onclick="document.getElementById('addGameBtn')?.click()" class="gt-btn gt-btn-primary">Добавить игру</button>
                </div>
            `;
            return;
        }

        games.forEach((game, index) => {
            const cover = game.cover_url || 'https://via.placeholder.com/300x400/111827/6b7280?text=No+Cover';
            const playtimeHours = game.total_playtime_minutes / 60;
            const progressPercent = Math.max(4, Math.min(100, Math.round((playtimeHours / 70) * 100)));

            const card = document.createElement('a');
            card.href = `#game/${game.id}`;
            card.draggable = true;
            card.className = 'group gt-panel overflow-hidden flex flex-col cursor-grab active:cursor-grabbing hover:-translate-y-1 transition-all duration-300';
            card.style.animation = `panel-in 300ms ease-out ${Math.min(index * 35, 250)}ms both`;

            card.addEventListener('dragstart', (evt) => {
                const e = evt as DragEvent;
                if (e.dataTransfer) {
                    e.dataTransfer.setData('gameId', game.id.toString());
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setDragImage(transparentImage, 0, 0);
                }

                dragMirror = card.cloneNode(true) as HTMLElement;
                dragMirror.classList.add('drag-mirror');
                dragMirror.style.left = `${e.clientX}px`;
                dragMirror.style.top = `${e.clientY}px`;
                dragMirror.classList.remove('group', 'hover:-translate-y-1');
                dragMirror.querySelectorAll('.flex-grow').forEach((el) => el.classList.remove('flex-grow'));
                document.body.appendChild(dragMirror);

                card.classList.add('dragging');
                grid.classList.add('games-grid-dragging');
                window.addEventListener('dragover', onGlobalDragOver);
            });

            card.addEventListener('dragend', () => {
                card.classList.remove('dragging');
                grid.classList.remove('games-grid-dragging');
                if (dragMirror) {
                    dragMirror.remove();
                    dragMirror = null;
                }
                window.removeEventListener('dragover', onGlobalDragOver);
                document.querySelectorAll('.status-tab').forEach((b) => b.classList.remove('drop-target'));
            });

            card.innerHTML = `
                <div class="aspect-[3/4] relative overflow-hidden pointer-events-none">
                    <img src="${cover}" alt="${game.title}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-900/30 to-transparent"></div>
                    <div class="absolute top-2 left-2 gt-chip">${statusLabel(game.status)}</div>
                    <div class="absolute bottom-0 left-0 right-0 p-3">
                        <h3 class="font-bold text-white leading-tight line-clamp-2">${game.title}</h3>
                    </div>
                </div>
                <div class="p-3 flex-grow flex flex-col gap-3 pointer-events-none">
                    <div class="flex items-center justify-between text-xs text-slate-300/80">
                        <span>Наиграно</span>
                        <span class="font-semibold text-cyan-200">${formatPlaytime(game.total_playtime_minutes)}</span>
                    </div>
                    <div class="gt-progress-track">
                        <div class="gt-progress-fill" style="width:${progressPercent}%"></div>
                    </div>
                    <p class="text-[11px] uppercase tracking-wider text-slate-400">Прогресс профиля: ${progressPercent}%</p>
                </div>
            `;

            grid.appendChild(card);
        });
    }

    container.querySelectorAll('.status-tab').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            const target = e.currentTarget as HTMLElement;
            container.querySelectorAll('.status-tab').forEach((tab) => {
                tab.classList.remove('bg-cyan-500/20', 'text-cyan-200', 'border-cyan-400/30', 'active-tab');
                tab.classList.add('text-slate-300', 'hover:bg-slate-700/60', 'border-transparent');
            });
            target.classList.remove('text-slate-300', 'hover:bg-slate-700/60', 'border-transparent');
            target.classList.add('bg-cyan-500/20', 'text-cyan-200', 'border-cyan-400/30', 'active-tab');

            currentStatus = target.getAttribute('data-status') || 'playing';
            loadGames();
        });

        btn.addEventListener('dragover', (e) => {
            e.preventDefault();
            const target = e.currentTarget as HTMLElement;
            if (target.getAttribute('data-status') !== currentStatus) {
                target.classList.add('drop-target');
            }
        });

        btn.addEventListener('dragleave', (e) => {
            (e.currentTarget as HTMLElement).classList.remove('drop-target');
        });

        btn.addEventListener('drop', async (evt) => {
            const e = evt as DragEvent;
            e.preventDefault();
            const target = e.currentTarget as HTMLElement;
            target.classList.remove('drop-target');

            const gameId = e.dataTransfer?.getData('gameId');
            const newStatus = target.getAttribute('data-status');

            if (gameId && newStatus && newStatus !== currentStatus) {
                try {
                    await api.updateGame(parseInt(gameId, 10), { status: newStatus });
                    loadGames();
                } catch {
                    alert('Не удалось переместить игру');
                }
            }
        });
    });

    searchInput.addEventListener('input', () => {
        searchText = searchInput.value;
        renderGamesList();
    });

    sortSelect.addEventListener('change', () => {
        sortBy = sortSelect.value;
        renderGamesList();
    });

    loadGames();
}

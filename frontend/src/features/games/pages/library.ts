import { api, type Game } from '../../../shared/api';
import { showNotification } from '../../../shared/ui';
import { pickSteamPoster } from '../../../shared/lib/steam-images';

function escapeHtml(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatPlaytime(minutes: number): string {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h} ч ${m} мин`;
}

function statusLabel(status: string): string {
    if (status === 'playing') return 'Играю';
    if (status === 'completed') return 'Пройдено';
    if (status === 'backlog') return 'Запланировано';
    if (status === 'deferred') return 'Отложено';
    return status;
}

function compareGames(a: Game, b: Game, sortBy: string): number {
    if (sortBy === 'title-asc') return a.title.localeCompare(b.title, 'ru');
    if (sortBy === 'title-desc') return b.title.localeCompare(a.title, 'ru');
    if (sortBy === 'playtime-asc') return a.total_playtime_minutes - b.total_playtime_minutes;
    if (sortBy === 'playtime-desc') return b.total_playtime_minutes - a.total_playtime_minutes;
    return Date.parse(b.created_at) - Date.parse(a.created_at);
}

export async function renderLibrary(container: HTMLElement) {
    let username = 'Игрок';
    try {
        const me = await api.getMe();
        if (me.username?.trim()) {
            username = me.username.trim();
        }
    } catch {
        // Keep fallback username when profile fetch fails.
    }

    container.innerHTML = `
        <div class="gt-page-flow gt-page-flow-lg">
            <section class="gt-panel gt-section-pad overflow-hidden relative">
                <button id="heroLogoutBtn" class="gt-btn absolute top-4 right-4 z-20 text-rose-100 border-rose-300/45 bg-rose-300/14 hover:bg-rose-300/24">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                    Выйти
                </button>
                <div class="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                    <div class="max-w-3xl gt-stack-md">
                        <span class="gt-chip inline-flex">Командный центр</span>
                        <h1 class="text-3xl md:text-5xl font-bold leading-tight tracking-tight">Привет, ${escapeHtml(username)}!</h1>
                        <p id="heroGameFact" class="text-slate-300/90 text-sm md:text-base max-w-2xl">Загружаем интересный факт об играх...</p>
                    </div>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full lg:w-auto" id="statsDock">
                        <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Всего игр</p><p id="statTotal" class="text-2xl font-bold">-</p></div>
                        <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Играю</p><p id="statPlaying" class="text-2xl font-bold text-cyan-300">-</p></div>
                        <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Пройдено</p><p id="statCompleted" class="text-2xl font-bold text-lime-300">-</p></div>
                        <div class="gt-panel p-3 min-w-[120px]"><p class="text-xs text-slate-300/70 uppercase tracking-wide">Часов</p><p id="statHours" class="text-2xl font-bold text-amber-300">-</p></div>
                    </div>
                </div>
            </section>

            <section class="gt-panel library-status-shell gt-section-pad-sm">
                <div class="library-status-header">
                    <p class="library-status-title">Раздел библиотеки</p>
                    <p class="library-status-subtitle">Переключение активного статуса</p>
                </div>
                <div class="library-status-tabs">
                    <button class="status-tab library-status-tab px-4 py-2 rounded-xl text-sm font-semibold bg-cyan-500/20 text-cyan-200 border border-cyan-400/30 active-tab" data-status="playing">Играю</button>
                    <button class="status-tab library-status-tab px-4 py-2 rounded-xl text-sm font-semibold text-slate-300 hover:bg-slate-700/60 border border-transparent" data-status="backlog">Запланировано</button>
                    <button class="status-tab library-status-tab px-4 py-2 rounded-xl text-sm font-semibold text-slate-300 hover:bg-slate-700/60 border border-transparent" data-status="completed">Пройдено</button>
                    <button class="status-tab library-status-tab px-4 py-2 rounded-xl text-sm font-semibold text-slate-300 hover:bg-slate-700/60 border border-transparent" data-status="deferred">Отложено</button>
                </div>
            </section>

            <section>
                <div class="gt-panel gt-section-pad-sm library-filters">
                <div class="relative library-search-wrap">
                    <input id="librarySearch" class="gt-input pr-9" type="text" placeholder="Быстрый поиск по библиотеке...">
                    <svg class="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </div>
                <div id="libraryGenreWrap" class="library-sort-wrap">
                    <button id="libraryGenreBtn" class="library-sort-btn gt-dropdown-control" type="button" aria-haspopup="listbox" aria-expanded="false">
                        <span id="libraryGenreLabel">Все жанры</span>
                        <svg class="library-sort-caret w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                    </button>
                    <div id="libraryGenreMenu" class="library-sort-menu" role="listbox" aria-label="Фильтр по жанру"></div>
                </div>
                <div id="librarySortWrap" class="library-sort-wrap">
                    <button id="librarySortBtn" class="library-sort-btn gt-dropdown-control" type="button" aria-haspopup="listbox" aria-expanded="false">
                        <span id="librarySortLabel">Сначала новые</span>
                        <svg class="library-sort-caret w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                    </button>
                    <div id="librarySortMenu" class="library-sort-menu" role="listbox" aria-label="Сортировка библиотеки">
                        <button class="library-sort-option is-active" type="button" role="option" aria-selected="true" data-value="created-desc">Сначала новые</button>
                        <button class="library-sort-option" type="button" role="option" aria-selected="false" data-value="playtime-desc">По времени (убыв.)</button>
                        <button class="library-sort-option" type="button" role="option" aria-selected="false" data-value="playtime-asc">По времени (возр.)</button>
                        <button class="library-sort-option" type="button" role="option" aria-selected="false" data-value="title-asc">По названию (А-Я)</button>
                        <button class="library-sort-option" type="button" role="option" aria-selected="false" data-value="title-desc">По названию (Я-А)</button>
                    </div>
                </div>
            </section>

            <section id="gamesGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4 lg:gap-5 relative min-h-[420px]"></section>
        </div>
    `;

    const grid = container.querySelector<HTMLElement>('#gamesGrid')!;
    const searchInput = container.querySelector<HTMLInputElement>('#librarySearch')!;
    const genreWrap = container.querySelector<HTMLElement>('#libraryGenreWrap')!;
    const genreButton = container.querySelector<HTMLButtonElement>('#libraryGenreBtn')!;
    const genreLabel = container.querySelector<HTMLElement>('#libraryGenreLabel')!;
    const sortWrap = container.querySelector<HTMLElement>('#librarySortWrap')!;
    const sortButton = container.querySelector<HTMLButtonElement>('#librarySortBtn')!;
    const sortLabel = container.querySelector<HTMLElement>('#librarySortLabel')!;
    const sortOptions = Array.from(container.querySelectorAll<HTMLButtonElement>('.library-sort-option'));
    const logoutBtn = container.querySelector<HTMLButtonElement>('#heroLogoutBtn');
    const factText = container.querySelector<HTMLElement>('#heroGameFact');

    let dragMirror: HTMLElement | null = null;
    let gamesByStatus: Game[] = [];
    let allGames: Game[] = [];
    const profileProgressByGameId = new Map<number, number>();
    let currentStatus = 'playing';
    let searchText = '';
    let selectedGenre = '';
    let sortBy = 'created-desc';
    const listenersAbort = new AbortController();
    const sortLabels: Record<string, string> = {
        'created-desc': 'Сначала новые',
        'playtime-desc': 'По времени (убыв.)',
        'playtime-asc': 'По времени (возр.)',
        'title-asc': 'По названию (А-Я)',
        'title-desc': 'По названию (Я-А)'
    };

    const transparentImage = new Image();
    transparentImage.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    logoutBtn?.addEventListener('click', () => {
        api.logout();
        window.location.hash = '#auth';
    });

    async function loadHeroFact() {
        if (!factText) return;
        factText.textContent = 'Загружаем интересный факт об играх...';
        try {
            const fact = await api.getRandomGameFact();
            factText.textContent = fact.text;
        } catch {
            factText.textContent = 'Факты пока недоступны. Сначала собери JSON через /api/facts/rebuild.';
        }
    }

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

    const toggleDropZoneHints = (enabled: boolean) => {
        container.querySelectorAll('.status-tab').forEach((el) => {
            const tab = el as HTMLElement;
            const tabStatus = tab.getAttribute('data-status');
            if (!tabStatus || tabStatus === currentStatus) return;
            tab.classList.toggle('drop-available', enabled);
        });
    };

    async function loadGames() {
        grid.innerHTML = `
            <div class="col-span-full absolute inset-0 flex flex-col items-center justify-center">
                <div class="loader-spinner mb-3"></div>
                <p class="text-slate-300/70 text-sm tracking-wide animate-pulse">Сканируем игровой ангар...</p>
            </div>
        `;

        try {
            allGames = await api.getGames();
            gamesByStatus = allGames.filter((g) => g.status === currentStatus);
            await hydrateProfileProgress(gamesByStatus);
            hydrateStats(allGames);
            hydrateGenres(allGames);
            renderGamesList();
        } catch {
            grid.innerHTML = `<div class="col-span-full text-center py-12 text-rose-300">Ошибка загрузки игр</div>`;
        }
    }

    function hydrateStats(allGames: Game[]) {
        const playing = allGames.filter((g) => g.status === 'playing').length;
        const completed = allGames.filter((g) => g.status === 'completed').length;
        const totalMinutes = allGames.reduce((sum, game) => sum + game.total_playtime_minutes, 0);
        const totalHours = (totalMinutes / 60).toFixed(1);

        (container.querySelector('#statTotal') as HTMLElement).textContent = String(allGames.length);
        (container.querySelector('#statPlaying') as HTMLElement).textContent = String(playing);
        (container.querySelector('#statCompleted') as HTMLElement).textContent = String(completed);
        (container.querySelector('#statHours') as HTMLElement).textContent = totalHours;
    }

    function getFilteredGames() {
        const needle = searchText.trim().toLowerCase();
        const byGenre = selectedGenre
            ? gamesByStatus.filter((game) => (game.genres || []).includes(selectedGenre))
            : [...gamesByStatus];
        const filtered = needle
            ? byGenre.filter((game) => game.title.toLowerCase().includes(needle))
            : byGenre;

        return filtered.sort((a, b) => compareGames(a, b, sortBy));
    }

    function hydrateGenres(games: Game[]) {
        const genreMenu = container.querySelector<HTMLElement>('#libraryGenreMenu');
        if (!genreMenu) return;
        const genres = new Set<string>();
        games.forEach((game) => {
            (game.genres || []).forEach((genre) => {
                if (genre) genres.add(genre);
            });
        });
        const sortedGenres = Array.from(genres).sort((a, b) => a.localeCompare(b, 'ru'));
        const genreOptions = [''].concat(sortedGenres);
        genreMenu.innerHTML = '';
        genreOptions.forEach((genre) => {
            const isActive = genre === selectedGenre;
            const label = genre || 'Все жанры';
            const option = document.createElement('button');
            option.type = 'button';
            option.className = `library-sort-option library-genre-option ${isActive ? 'is-active' : ''}`;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', isActive ? 'true' : 'false');
            option.dataset.value = genre;
            option.textContent = label;
            option.addEventListener('click', () => {
                selectedGenre = option.dataset.value || '';
                genreLabel.textContent = selectedGenre || 'Все жанры';
                renderGamesList();
                closeGenreMenu();
            });
            genreMenu.appendChild(option);
        });
        genreLabel.textContent = selectedGenre || 'Все жанры';
        if (selectedGenre && !sortedGenres.includes(selectedGenre)) {
            selectedGenre = '';
            genreLabel.textContent = 'Все жанры';
        }
    }

    function calcProgressPercent(completed: number, total: number): number {
        if (total <= 0) return 0;
        return Math.round((completed / total) * 100);
    }

    async function computeProfileProgress(game: Game): Promise<number> {
        try {
            if (game.sync_type === 'steam') {
                const [checklists, achievements] = await Promise.all([
                    api.getChecklist(game.id),
                    api.getAchievements(game.id)
                ]);

                const questPercent = calcProgressPercent(
                    checklists.filter((c) => c.completed).length,
                    checklists.length
                );
                const achPercent = calcProgressPercent(
                    achievements.filter((a) => a.completed).length,
                    achievements.length
                );

                if (checklists.length === 0 && achievements.length === 0) return 0;
                if (checklists.length === 0) return achPercent;
                if (achievements.length === 0) return questPercent;
                return Math.round((questPercent + achPercent) / 2);
            }

            const checklists = await api.getChecklist(game.id);
            return calcProgressPercent(
                checklists.filter((c) => c.completed).length,
                checklists.length
            );
        } catch {
            return 0;
        }
    }

    async function hydrateProfileProgress(games: Game[]) {
        await Promise.all(
            games.map(async (game) => {
                const progress = await computeProfileProgress(game);
                profileProgressByGameId.set(game.id, progress);
            })
        );
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
                    <p class="text-xl font-semibold mb-3 text-slate-100">${emptyMessage}</p>
                    <p class="text-slate-400 text-sm mb-6">Создайте карточку игры и распределите ее по статусам.</p>
                    <button onclick="document.getElementById('addGameBtn')?.click()" class="gt-btn gt-btn-primary">Добавить игру</button>
                </div>
            `;
            return;
        }

        games.forEach((game, index) => {
            const poster = pickSteamPoster(game);
            const cover = poster.src || game.cover_url || 'https://via.placeholder.com/300x400/111827/6b7280?text=No+Cover';
            const coverFallback = poster.fallback || '';
            const safeCover = escapeHtml(cover);
            const safeCoverFallback = escapeHtml(coverFallback);
            const safeTitle = escapeHtml(game.title);
            const safeGenres = escapeHtml((game.genres || []).slice(0, 2).join(' • ') || 'Жанры не заданы');
            const progressPercent = profileProgressByGameId.get(game.id) ?? 0;

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
                toggleDropZoneHints(true);
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
                toggleDropZoneHints(false);
                document.querySelectorAll('.status-tab').forEach((b) => b.classList.remove('drop-target'));
            });

                card.innerHTML = `
                <div class="aspect-[3/4] relative overflow-hidden pointer-events-none">
                    <img src="${safeCover}" alt="${safeTitle}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy" onerror="if(!this.dataset.fallback && '${safeCoverFallback}'){this.dataset.fallback='1';this.src='${safeCoverFallback}';}">
                    <div class="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-900/30 to-transparent"></div>
                    <div class="absolute top-2 left-2 gt-badge gt-badge-info">${statusLabel(game.status)}</div>
                    <div class="absolute bottom-0 left-0 right-0 p-3">
                        <h3 class="font-bold text-white leading-tight line-clamp-2">${safeTitle}</h3>
                    </div>
                </div>
                <div class="p-3 -mt-px flex-grow flex flex-col gap-3 pointer-events-none">
                    <div class="flex items-center justify-between text-xs text-slate-300/80">
                        <span>Наиграно</span>
                        <span class="font-semibold text-cyan-200">${formatPlaytime(game.total_playtime_minutes)}</span>
                    </div>
                    <div class="gt-progress-track">
                        <div class="gt-progress-fill" style="width:${progressPercent}%"></div>
                    </div>
                    <p class="text-[11px] uppercase tracking-wider text-slate-400">Прогресс профиля: ${progressPercent}%</p>
                    <p class="text-[11px] text-slate-400 line-clamp-2">${safeGenres}</p>
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
                    showNotification('Не удалось переместить игру', 'error');
                }
            }
        });
    });

    searchInput.addEventListener('input', () => {
        searchText = searchInput.value;
        renderGamesList();
    }, { signal: listenersAbort.signal });

    const closeGenreMenu = () => {
        genreWrap.classList.remove('is-open');
        genreButton.setAttribute('aria-expanded', 'false');
    };
    const openGenreMenu = () => {
        genreWrap.classList.add('is-open');
        genreButton.setAttribute('aria-expanded', 'true');
    };

    const closeSortMenu = () => {
        sortWrap.classList.remove('is-open');
        sortButton.setAttribute('aria-expanded', 'false');
    };

    const openSortMenu = () => {
        sortWrap.classList.add('is-open');
        sortButton.setAttribute('aria-expanded', 'true');
    };

    const setSortValue = (value: string) => {
        sortBy = value;
        sortLabel.textContent = sortLabels[value] || 'Сортировка';
        sortOptions.forEach((option) => {
            const isActive = option.dataset.value === value;
            option.classList.toggle('is-active', isActive);
            option.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
        renderGamesList();
    };

    sortButton.addEventListener('click', () => {
        if (sortWrap.classList.contains('is-open')) {
            closeSortMenu();
            return;
        }
        closeGenreMenu();
        openSortMenu();
    }, { signal: listenersAbort.signal });

    genreButton.addEventListener('click', () => {
        if (genreWrap.classList.contains('is-open')) {
            closeGenreMenu();
            return;
        }
        closeSortMenu();
        openGenreMenu();
    }, { signal: listenersAbort.signal });

    sortOptions.forEach((option) => {
        option.addEventListener('click', () => {
            const value = option.dataset.value;
            if (!value) return;
            setSortValue(value);
            closeSortMenu();
        }, { signal: listenersAbort.signal });
    });

    window.addEventListener('click', (e) => {
        if (!sortWrap.contains(e.target as Node)) {
            closeSortMenu();
        }
        if (!genreWrap.contains(e.target as Node)) {
            closeGenreMenu();
        }
    }, { signal: listenersAbort.signal });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSortMenu();
            closeGenreMenu();
        }
    }, { signal: listenersAbort.signal });

    const liveRefreshIntervalMs = 15000;
    let liveRefreshInFlight = false;
    const runLiveRefresh = async () => {
        if (liveRefreshInFlight) return;
        if (window.location.hash !== '#library') return;
        liveRefreshInFlight = true;
        try {
            await loadGames();
        } finally {
            liveRefreshInFlight = false;
        }
    };
    const liveTimer = window.setInterval(() => {
        if (document.visibilityState !== 'visible') return;
        void runLiveRefresh();
    }, liveRefreshIntervalMs);
    listenersAbort.signal.addEventListener('abort', () => {
        window.clearInterval(liveTimer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    }, { once: true });
    const onVisibilityChange = () => {
        if (document.visibilityState === 'visible') {
            void runLiveRefresh();
        }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    window.addEventListener('hashchange', () => listenersAbort.abort(), { once: true });

    setSortValue(sortBy);
    loadHeroFact();
    loadGames();
}

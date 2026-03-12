import { api } from '../api';
import { showNotification } from '../ui';
import { pickSteamPoster } from '../steamImages';

export function mountAddGameModal() {
    const root = document.getElementById('modal-root')!;
    
    // Create animated overlay
    const overlay = document.createElement('div');
    overlay.className = "gt-modal-overlay";
    
    // Modal content container
    const modal = document.createElement('div');
    modal.className = "gt-panel gt-modal-panel rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]";
    
    modal.innerHTML = `
        <div class="gt-modal-header">
            <div>
                <h2 class="gt-modal-title text-2xl">Добавить игру</h2>
                <p class="text-sm text-slate-300/80 mt-1">Поиск по базе Steam</p>
            </div>
            <button id="closeModal" class="gt-modal-close">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        
        <div class="p-6 border-b border-slate-600/45 bg-slate-900/35">
            <form id="searchForm" class="flex gap-3" novalidate>
                <div class="relative flex-grow group">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-cyan-300 transition-colors">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                    </div>
                    <input type="text" id="dbQuery" placeholder="Название игры (напр. Witcher 3)..." class="gt-input gt-input-icon" required>
                </div>
                <button type="submit" class="gt-btn gt-btn-primary px-6 py-3 whitespace-nowrap">
                    Найти
                </button>
            </form>
        </div>
        
        <div class="flex-grow overflow-y-auto p-6 bg-slate-900/35">
            <h3 class="text-xs font-bold text-slate-300/75 uppercase tracking-wider mb-4 border-b border-slate-600/45 pb-2">Результаты поиска</h3>
            <div id="searchResults" class="space-y-3">
                <div class="text-center py-10 text-slate-400">
                    <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-900/60 mb-4 border border-slate-600/45">
                        <svg class="w-8 h-8 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16l2.879-2.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                    <p>Введите название игры для поиска</p>
                </div>
            </div>
        </div>
    `;

    overlay.appendChild(modal);
    root.appendChild(overlay);

    // Trigger animations in next frame
    requestAnimationFrame(() => {
        overlay.classList.add('is-open');
        modal.classList.add('is-open');
        document.getElementById('dbQuery')?.focus();
    });

    const closeModal = () => {
        overlay.classList.remove('is-open');
        modal.classList.remove('is-open');
        setTimeout(() => root.innerHTML = '', 240);
    };

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });
    document.getElementById('closeModal')?.addEventListener('click', closeModal);

    document.getElementById('searchForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const queryInput = document.getElementById('dbQuery') as HTMLInputElement;
        const query = queryInput.value.trim();
        if (!query) {
            showNotification('Введите название игры для поиска.', 'info');
            queryInput.focus();
            return;
        }
        const resultsBox = document.getElementById('searchResults')!;
        const alreadyAddedClass = "bg-rose-500/15 text-rose-300 border border-rose-400/45 text-sm font-medium px-4 py-2 rounded-lg transition-all cursor-default opacity-90";
        const alreadyAddedIcon = '<svg class="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke-width="2"></circle><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7.5 16.5L16.5 7.5"></path></svg>';

        const markButtonsAsAlreadyAdded = (buttons: NodeListOf<Element>) => {
            buttons.forEach(button => {
                const el = button as HTMLButtonElement;
                el.disabled = true;
                el.className = alreadyAddedClass;
                el.innerHTML = alreadyAddedIcon;
            });
        };
        
        // Show loading state
        resultsBox.innerHTML = `
            <div class="flex items-center justify-center py-10">
                <div class="w-8 h-8 border-3 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
                <span class="ml-3 text-gray-400">Поиск в базах данных...</span>
            </div>
        `;

        try {
            const [steam, existingGames] = await Promise.all([
                api.searchSteam(query),
                api.getGames()
            ]);

            const results = steam;
            const existingSteamIds = new Set(
                existingGames
                    .map(g => g.steam_app_id)
                    .filter((id): id is number => typeof id === 'number')
            );
            const existingTitles = new Set(
                existingGames
                    .map(g => (g.title || '').trim().toLowerCase())
                    .filter(Boolean)
            );

            resultsBox.innerHTML = '';
            
            if (results.length === 0) {
                resultsBox.innerHTML = `<div class="gt-empty-state">Ничего не найдено</div>`;
                return;
            }

            results.forEach((game, idx) => {
                const normalizedTitle = (game.title || '').trim().toLowerCase();
                const isAlreadyAdded =
                    (typeof game.steam_app_id === 'number' && existingSteamIds.has(game.steam_app_id)) ||
                    (!!normalizedTitle && existingTitles.has(normalizedTitle));

                const steamBtnClass = isAlreadyAdded
                    ? alreadyAddedClass
                    : "add-btn bg-cyan-400/20 hover:bg-cyan-400/30 text-cyan-200 border border-cyan-300/40 text-sm font-medium px-4 py-2 rounded-lg transition-all";
                const nonSteamBtnClass = isAlreadyAdded
                    ? alreadyAddedClass
                    : "add-btn bg-lime-400/20 hover:bg-lime-400/30 text-lime-200 border border-lime-300/40 text-sm font-medium px-4 py-2 rounded-lg transition-all";
                const steamBtnContent = isAlreadyAdded ? alreadyAddedIcon : "Steam";
                const nonSteamBtnContent = isAlreadyAdded ? alreadyAddedIcon : "Non-Steam";
                const disabledAttr = isAlreadyAdded ? "disabled" : "";

                const el = document.createElement('div');
                el.className = "group flex items-center justify-between p-4 bg-slate-900/60 rounded-xl border border-slate-600/45 hover:border-cyan-400/55 transition-colors";

                // Animation stagger
                el.style.animation = `fadeIn 0.3s ease-out ${idx * 0.05}s both`;

                const poster = pickSteamPoster(game);
                const coverUrl = poster.src || game.cover_url || `https://cdn.akamai.steamstatic.com/steam/apps/${game.steam_app_id}/header.jpg`;
                const coverFallback = poster.fallback || '';

                el.innerHTML = `
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-16 bg-slate-900 rounded flex items-center justify-center border border-slate-600/45 shrink-0 overflow-hidden">
                            <img src="${coverUrl}" alt="${game.title}" class="w-full h-full object-cover" loading="lazy" onerror="if(!this.dataset.fallback && '${coverFallback}'){this.dataset.fallback='1';this.src='${coverFallback}';return;} this.style.display='none'; this.parentElement.innerHTML='<svg class=\\'w-6 h-6 text-slate-500\\' fill=\\'none\\' stroke=\\'currentColor\\' viewBox=\\'0 0 24 24\\'><path stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\' stroke-width=\\'2\\' d=\\'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z\\'></svg>'">
                        </div>
                        <div>
                            <div class="font-medium text-white group-hover:text-cyan-200 transition-colors">${game.title}</div>
                            <div class="text-xs text-slate-400 mt-1">Как синхронизировать игру после добавления?</div>
                        </div>
                    </div>
                    <div class="flex gap-2 shrink-0">
                        <button class="${steamBtnClass}" data-idx="${idx}" data-sync-type="steam" ${disabledAttr}>
                            ${steamBtnContent}
                        </button>
                        <button class="${nonSteamBtnClass}" data-idx="${idx}" data-sync-type="non_steam" ${disabledAttr}>
                            ${nonSteamBtnContent}
                        </button>
                    </div>
                `;
                resultsBox.appendChild(el);
            });

            // Bind add events
            resultsBox.querySelectorAll('.add-btn').forEach(btn => {
                btn.addEventListener('click', async (btnEv) => {
                    const target = btnEv.currentTarget as HTMLButtonElement;
                    if (target.disabled) return;
                    const idx = parseInt(target.getAttribute('data-idx')!);
                    const syncType = target.getAttribute('data-sync-type') as 'steam' | 'non_steam';
                    const targetGame = results[idx];
                    const siblingButtons = resultsBox.querySelectorAll(`.add-btn[data-idx="${idx}"]`);

                    siblingButtons.forEach(button => {
                        (button as HTMLButtonElement).disabled = true;
                    });
                    target.innerHTML = '<div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>';

                    try {
                        const targetPoster = pickSteamPoster(targetGame);
                        await api.createGame({
                            title: targetGame.title,
                            sync_type: syncType,
                            steam_app_id: targetGame.steam_app_id,
                            cover_url: targetPoster.src || targetGame.cover_url || '',
                            status: 'backlog'
                        });

                        markButtonsAsAlreadyAdded(siblingButtons);

                        // Refetch library if shown
                        if (window.location.hash === '' || window.location.hash === '#library') {
                            window.dispatchEvent(new Event('hashchange'));
                        }
                    } catch(e) {
                         showNotification('Ошибка добавления', 'error');
                         siblingButtons.forEach(button => {
                            const el = button as HTMLButtonElement;
                            el.disabled = false;
                            el.textContent = el.getAttribute('data-sync-type') === 'steam' ? 'Steam' : 'Non-Steam';
                         });
                    }
                });
            });

        } catch (e) {
            resultsBox.innerHTML = `<div class="gt-empty-state error">Ошибка поиска. Сервер FastAPI запущен?</div>`;
        }
    });
}

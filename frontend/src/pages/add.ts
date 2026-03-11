import { api } from '../api';

export function mountAddGameModal() {
    const root = document.getElementById('modal-root')!;
    
    // Create animated overlay
    const overlay = document.createElement('div');
    overlay.className = "fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4 opacity-0 transition-opacity duration-300 ease-out";
    
    // Modal content container
    const modal = document.createElement('div');
    modal.className = "bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl border border-gray-700/50 overflow-hidden transform scale-95 opacity-0 transition-all duration-300 ease-out flex flex-col max-h-[90vh]";
    
    modal.innerHTML = `
        <div class="p-6 border-b border-gray-700/50 flex justify-between items-center bg-gray-800/50">
            <div>
                <h2 class="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400">Добавить игру</h2>
                <p class="text-sm text-gray-400 mt-1">Поиск по базе Steam</p>
            </div>
            <button id="closeModal" class="text-gray-400 hover:text-white hover:bg-gray-700 p-2 rounded-lg transition-colors">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        
        <div class="p-6 border-b border-gray-700/50 bg-gray-900/30">
            <form id="searchForm" class="flex gap-3">
                <div class="relative flex-grow group">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400 group-focus-within:text-blue-400 transition-colors">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                    </div>
                    <input type="text" id="dbQuery" placeholder="Название игры (напр. Witcher 3)..." class="w-full bg-gray-900 border border-gray-700 rounded-xl pl-10 pr-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all shadow-inner" required>
                </div>
                <button type="submit" class="bg-blue-600 hover:bg-blue-500 text-white px-6 py-3 rounded-xl font-medium transition-all shadow-lg shadow-blue-500/20 whitespace-nowrap">
                    Найти
                </button>
            </form>
        </div>
        
        <div class="flex-grow overflow-y-auto p-6 bg-gray-800">
            <h3 class="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4 border-b border-gray-700/50 pb-2">Результаты поиска</h3>
            <div id="searchResults" class="space-y-3">
                <div class="text-center py-10 text-gray-500">
                    <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-800 mb-4 border border-gray-700">
                        <svg class="w-8 h-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16l2.879-2.879m0 0a3 3 0 104.243-4.242 3 3 0 00-4.243 4.242zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
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
        overlay.classList.remove('opacity-0');
        overlay.classList.add('opacity-100');
        modal.classList.remove('scale-95', 'opacity-0');
        modal.classList.add('scale-100', 'opacity-100');
        document.getElementById('dbQuery')?.focus();
    });

    const closeModal = () => {
        overlay.classList.remove('opacity-100');
        overlay.classList.add('opacity-0');
        modal.classList.remove('scale-100', 'opacity-100');
        modal.classList.add('scale-95', 'opacity-0');
        setTimeout(() => root.innerHTML = '', 300);
    };

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });
    document.getElementById('closeModal')?.addEventListener('click', closeModal);

    document.getElementById('searchForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = (document.getElementById('dbQuery') as HTMLInputElement).value;
        const resultsBox = document.getElementById('searchResults')!;
        
        // Show loading state
        resultsBox.innerHTML = `
            <div class="flex items-center justify-center py-10">
                <div class="w-8 h-8 border-3 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
                <span class="ml-3 text-gray-400">Поиск в базах данных...</span>
            </div>
        `;

        try {
            // Search Steam API
            const steam = await api.searchSteam(query);

            const results = steam;

            resultsBox.innerHTML = '';
            
            if (results.length === 0) {
                resultsBox.innerHTML = `<div class="text-center py-6 text-gray-400">Ничего не найдено</div>`;
                return;
            }

            results.forEach((game, idx) => {
                const el = document.createElement('div');
                el.className = "group flex items-center justify-between p-4 bg-gray-900 rounded-xl border border-gray-700/50 hover:border-blue-500/50 transition-colors";

                // Animation stagger
                el.style.animation = `fadeIn 0.3s ease-out ${idx * 0.05}s both`;

                const coverUrl = game.cover_url || `https://cdn.akamai.steamstatic.com/steam/apps/${game.steam_app_id}/header.jpg`;

                el.innerHTML = `
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-16 bg-gray-800 rounded flex items-center justify-center border border-gray-700 shrink-0 overflow-hidden">
                            <img src="${coverUrl}" alt="${game.title}" class="w-full h-full object-cover" loading="lazy" onerror="this.style.display='none'; this.parentElement.innerHTML='<svg class=\\'w-6 h-6 text-gray-500\\' fill=\\'none\\' stroke=\\'currentColor\\' viewBox=\\'0 0 24 24\\'><path stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\' stroke-width=\\'2\\' d=\\'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z\\'></svg>'">
                        </div>
                        <div>
                            <div class="font-medium text-white group-hover:text-blue-400 transition-colors">${game.title}</div>
                        </div>
                    </div>
                    <button class="add-btn bg-gray-800 hover:bg-white hover:text-gray-900 border border-gray-600 text-sm font-medium px-4 py-2 rounded-lg transition-all" data-idx="${idx}">
                        Добавить
                    </button>
                `;
                resultsBox.appendChild(el);
            });

            // Bind add events
            resultsBox.querySelectorAll('.add-btn').forEach(btn => {
                btn.addEventListener('click', async (btnEv) => {
                    const idx = parseInt((btnEv.target as HTMLElement).getAttribute('data-idx')!);
                    const targetGame = results[idx];
                    
                    const btnEl = btnEv.target as HTMLButtonElement;
                    btnEl.disabled = true;
                    btnEl.innerHTML = '<div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>';
                    
                    try {
                        await api.createGame({
                            title: targetGame.title,
                            source: targetGame.source,
                            steam_app_id: targetGame.steam_app_id,
                            cover_url: targetGame.cover_url || '',
                            status: 'backlog'
                        });
                        
                        btnEl.className = "bg-green-500/20 text-green-400 border border-green-500/50 text-sm font-medium px-4 py-2 rounded-lg transition-all cursor-default";
                        btnEl.innerHTML = '<svg class="w-5 h-5 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>';
                        
                        // Refetch library if shown
                        if (window.location.hash === '' || window.location.hash === '#library') {
                            window.dispatchEvent(new Event('hashchange'));
                        }
                    } catch(e) {
                         alert('Ошибка добавления');
                         btnEl.disabled = false;
                         btnEl.textContent = 'Добавить';
                    }
                });
            });

        } catch (e) {
            resultsBox.innerHTML = `<div class="text-center py-6 text-red-500">Ошибка поиска. Сервер FastAPI запущен?</div>`;
        }
    });
}

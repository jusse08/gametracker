import { api, type Game } from '../api';

export async function renderLibrary(container: HTMLElement) {
    container.innerHTML = `
        <div class="mb-8 flex justify-between items-end">
            <div>
                <h1 class="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-500 mb-2">Моя Библиотека</h1>
                <p class="text-gray-400">Отслеживайте свои игры, время и прогресс.</p>
            </div>
            
            <div class="flex gap-2 bg-gray-800 p-1 rounded-xl shadow-inner mt-4 md:mt-0">
                <button class="status-tab px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-blue-600/20 text-blue-400 active-tab" data-status="playing">Играю</button>
                <button class="status-tab px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-gray-700 text-gray-400" data-status="backlog">Запланировано</button>
                <button class="status-tab px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-gray-700 text-gray-400" data-status="completed">Пройдено</button>
            </div>
        </div>
        <div id="gamesGrid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-6 relative min-h-[400px] transition-all duration-300">
            <div class="absolute inset-0 flex items-center justify-center">
                 <div class="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
            </div>
        </div>
    `;

    const grid = document.getElementById('gamesGrid')!;

    let dragMirror: HTMLElement | null = null;
    const transparentImage = new Image();
    transparentImage.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

    // Global dragover to prevent "forbidden" cursor and update mirror position
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
    let currentStatus = 'playing';

    async function loadGames() {
        grid.innerHTML = `
        <div class="col-span-full absolute inset-0 flex flex-col items-center justify-center opacity-50">
            <div class="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-4"></div>
            <p class="text-gray-400 animate-pulse">Загрузка...</p>
        </div>`;
        
        try {
            const games = await api.getGames(currentStatus);
            renderGamesList(games);
        } catch (e) {
            grid.innerHTML = `<div class="col-span-full text-center py-10 text-red-400">Ошибка загрузки игр</div>`;
        }
    }

    container.querySelectorAll('.status-tab').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const target = e.currentTarget as HTMLElement;
            document.querySelectorAll('.status-tab').forEach(b => {
                b.classList.remove('bg-blue-600/20', 'text-blue-400', 'active-tab');
                b.classList.add('hover:bg-gray-700', 'text-gray-400');
            });
            target.classList.remove('hover:bg-gray-700', 'text-gray-400');
            target.classList.add('bg-blue-600/20', 'text-blue-400', 'active-tab');

            currentStatus = target.getAttribute('data-status') || '';
            loadGames();
        });

        // Drag and Drop: Drop Target
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
                    await api.updateGame(parseInt(gameId), { status: newStatus });
                    loadGames(); // Refresh the grid
                } catch (error) {
                    console.error('Failed to move game:', error);
                    alert('Не удалось переместить игру');
                }
            }
        });
    });

    function renderGamesList(games: Game[]) {
        grid.innerHTML = '';
        if (games.length === 0) {
            grid.innerHTML = `
                <div class="col-span-full flex flex-col items-center justify-center py-20 bg-gray-800/50 rounded-2xl border border-gray-700/50 border-dashed">
                    <svg class="w-16 h-16 text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path></svg>
                    <p class="text-xl text-gray-400 font-medium mb-2">Здесь пока пусто</p>
                    <p class="text-gray-500 mb-6 text-sm">Добавьте игры, чтобы начать отслеживание.</p>
                    <button onclick="document.getElementById('addGameBtn')?.click()" class="bg-gray-700 hover:bg-gray-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-all shadow-md">
                        Добавить первую игру
                    </button>
                </div>
            `;
            return;
        }

        games.forEach(game => {
            const cover = game.cover_url || 'https://via.placeholder.com/300x400/1f2937/4b5563?text=Нет+обложки';
            const card = document.createElement('a');
            card.href = `#game/${game.id}`;
            card.className = "group relative rounded-xl overflow-hidden bg-gray-800 hover:-translate-y-1 hover:shadow-xl hover:shadow-blue-500/10 transition-all duration-300 ring-1 ring-gray-700 hover:ring-blue-500/50 flex flex-col h-full cursor-grab active:cursor-grabbing";
            card.draggable = true;

            card.addEventListener('dragstart', (evt) => {
                const e = evt as DragEvent;
                if (e.dataTransfer) {
                    e.dataTransfer.setData('gameId', game.id.toString());
                    e.dataTransfer.effectAllowed = 'move';
                    // Hide default ghost
                    e.dataTransfer.setDragImage(transparentImage, 0, 0);
                }

                // Create mirror
                dragMirror = card.cloneNode(true) as HTMLElement;
                dragMirror.classList.add('drag-mirror');
                dragMirror.id = `mirror-${game.id}`;
                dragMirror.style.left = `${e.clientX}px`;
                dragMirror.style.top = `${e.clientY}px`;
                
                // Remove layout classes that cause stretching in fixed position
                dragMirror.classList.remove('group', 'relative', 'hover:-translate-y-1', 'hover:shadow-xl', 'ring-1', 'hover:ring-blue-500/50', 'h-full', 'flex-col');
                
                // Ensure the inner elements don't try to grow
                dragMirror.querySelectorAll('.flex-grow').forEach(el => el.classList.remove('flex-grow'));
                
                document.body.appendChild(dragMirror);

                card.classList.add('dragging');
                grid.classList.add('games-grid-dragging');
                
                // Add global listener to handle movement and cursor
                window.addEventListener('dragover', onGlobalDragOver);
            });

            card.addEventListener('dragend', () => {
                card.classList.remove('dragging');
                grid.classList.remove('games-grid-dragging');
                
                // Remove mirror
                if (dragMirror) {
                    dragMirror.remove();
                    dragMirror = null;
                }

                // Clean up global listener
                window.removeEventListener('dragover', onGlobalDragOver);
                document.querySelectorAll('.status-tab').forEach(b => b.classList.remove('drop-target'));
            });
            
            card.innerHTML = `
                <div class="aspect-[3/4] overflow-hidden bg-gray-900 relative pointer-events-none">
                    <img src="${cover}" alt="${game.title}" class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy">
                    <div class="absolute inset-0 bg-gradient-to-t from-gray-900 via-gray-900/40 to-transparent opacity-80 group-hover:opacity-100 transition-opacity"></div>
                    
                    <!-- Drag Handle Icon (subtle) -->
                    <div class="absolute top-2 right-2 p-1.5 bg-gray-900/60 backdrop-blur-md rounded-lg opacity-0 group-hover:opacity-100 transition-opacity border border-white/10">
                        <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
                    </div>

                    <div class="absolute bottom-0 left-0 right-0 p-4 translate-y-2 group-hover:translate-y-0 transition-transform">
                        <h3 class="font-bold text-white mb-1 line-clamp-2 leading-tight">${game.title}</h3>
                    </div>
                </div>
                <div class="p-4 bg-gray-800/95 flex-grow backdrop-blur-sm border-t border-gray-700/50 pointer-events-none">
                    <div class="flex items-center text-xs text-blue-400 font-medium bg-blue-500/10 px-2 py-1.5 rounded inline-flex self-start">
                        <svg class="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        ${Math.floor(game.total_playtime_minutes / 60)} ч. ${game.total_playtime_minutes % 60} мин.
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    }

    loadGames();
}

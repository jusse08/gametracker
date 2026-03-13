import { api, type Game } from '../api';

const DEFAULT_GAMES_CACHE_MAX_AGE_MS = 15_000;
export const GAMES_CHANGED_EVENT = 'gametracker:games-changed';

export type GamesChangedDetail =
    | { type: 'replace'; games: Game[] }
    | { type: 'upsert'; game: Game }
    | { type: 'remove'; gameId: number }
    | { type: 'invalidate' };

let cachedGames: Game[] = [];
let cacheLoadedAt = 0;

function cloneGames(games: Game[]): Game[] {
    return games.map((game) => ({
        ...game,
        genres: game.genres ? [...game.genres] : game.genres,
        cover_urls: game.cover_urls ? { ...game.cover_urls } : game.cover_urls,
    }));
}

function emit(detail: GamesChangedDetail) {
    window.dispatchEvent(new CustomEvent<GamesChangedDetail>(GAMES_CHANGED_EVENT, { detail }));
}

export function getCachedGamesSnapshot(): Game[] {
    return cloneGames(cachedGames);
}

export function invalidateGamesCache(options: { emitEvent?: boolean } = {}): void {
    cacheLoadedAt = 0;
    if (options.emitEvent) {
        emit({ type: 'invalidate' });
    }
}

export function replaceCachedGames(games: Game[], options: { emitEvent?: boolean } = {}): Game[] {
    cachedGames = cloneGames(games);
    cacheLoadedAt = Date.now();
    if (options.emitEvent) {
        emit({ type: 'replace', games: getCachedGamesSnapshot() });
    }
    return getCachedGamesSnapshot()
}

export function upsertCachedGame(game: Game, options: { emitEvent?: boolean } = {}): Game[] {
    const next = getCachedGamesSnapshot();
    const index = next.findIndex((item) => item.id === game.id);
    if (index >= 0) {
        next[index] = { ...game, genres: game.genres ? [...game.genres] : game.genres };
    } else {
        next.push({ ...game, genres: game.genres ? [...game.genres] : game.genres });
    }
    replaceCachedGames(next, { emitEvent: false });
    if (options.emitEvent !== false) {
        emit({ type: 'upsert', game: { ...game, genres: game.genres ? [...game.genres] : game.genres } });
    }
    return getCachedGamesSnapshot()
}

export function removeCachedGame(gameId: number, options: { emitEvent?: boolean } = {}): Game[] {
    const next = getCachedGamesSnapshot().filter((item) => item.id !== gameId);
    replaceCachedGames(next, { emitEvent: false });
    if (options.emitEvent !== false) {
        emit({ type: 'remove', gameId });
    }
    return getCachedGamesSnapshot()
}

export async function loadGamesWithCache(options: { force?: boolean; maxAgeMs?: number } = {}): Promise<Game[]> {
    const { force = false, maxAgeMs = DEFAULT_GAMES_CACHE_MAX_AGE_MS } = options;
    const cacheIsFresh = cacheLoadedAt > 0 && (Date.now() - cacheLoadedAt) < maxAgeMs;
    if (!force && cacheIsFresh && cachedGames.length > 0) {
        return getCachedGamesSnapshot();
    }

    const games = await api.getGames();
    return replaceCachedGames(games, { emitEvent: false });
}

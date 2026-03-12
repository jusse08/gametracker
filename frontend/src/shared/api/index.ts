// types
export interface User {
    id: number;
    username: string;
    email?: string;
    steam_api_key?: string;
    steam_profile_url?: string;
    is_superadmin?: boolean;
}

export interface Game {
    id: number;
    title: string;
    status: string;
    cover_url?: string;
    cover_urls?: Partial<Record<'poster' | 'poster2x' | 'hero' | 'hero_blur' | 'header' | 'capsule_main', string>>;
    description?: string;
    sync_type: 'steam' | 'non_steam';
    steam_app_id?: number;
    exe_name?: string;
    launch_path?: string;
    personal_rating?: number;
    genres?: string[];
    created_at: string;
    total_playtime_minutes: number;
}

export interface Note {
    id: number;
    game_id: number;
    text: string;
    created_at: string;
}

export interface ChecklistItem {
    id: number;
    game_id: number;
    title: string;
    category: string;
    completed: boolean;
    sort_order: number;
}

export interface QuestCategory {
    id: number;
    game_id: number;
    name: string;
    created_at: string;
}

export interface Achievement {
    id: number;
    game_id: number;
    name: string;
    description?: string;
    icon_url?: string;
    completed: boolean;
    completed_at?: string;
    steam_api_name?: string;
}

export interface GameSession {
    id: number;
    game_id: number;
    started_at: string;
    ended_at?: string;
    duration_minutes: number;
    source: string;
}

export interface AgentConfigResponse {
    id: number;
    game_id: number;
    exe_name: string;
    launch_path?: string;
    enabled: boolean;
    updated_at: string;
}

export interface Settings {
    steam_api_key?: string;
    steam_profile_url?: string;
    steam_user_id?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000/api';

// Custom error class for API errors
export class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

async function handleResponse<T>(res: Response): Promise<T> {
    if (!res.ok) {
        let message = `Request failed with status ${res.status}`;
        try {
            const errorData = await res.json();
            message = errorData.detail || errorData.message || message;
        } catch {
            message = res.statusText || message;
        }
        throw new ApiError(res.status, message);
    }
    return res.json();
}

// Get auth token from localStorage
function getAuthToken(): string | null {
    return localStorage.getItem('auth_token');
}

function getAuthHeaders(): HeadersInit {
    const token = getAuthToken();
    if (!token) {
        return {};
    }
    return { 'Authorization': `Bearer ${token}` };
}

export const api = {
    // --- AUTH ---
    async getUsers(): Promise<User[]> {
        const res = await fetch(`${API_BASE}/users`, {
            headers: getAuthHeaders()
        });
        return handleResponse<User[]>(res);
    },

    async adminCreateUser(username: string, password: string): Promise<User> {
        const res = await fetch(`${API_BASE}/users`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        return handleResponse<User>(res);
    },

    async login(username: string, password: string): Promise<{ access_token: string, token_type: string, user: User }> {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            body: formData
        });
        const data = await handleResponse<{ access_token: string, token_type: string, user: User }>(res);
        if (data.access_token) {
            localStorage.setItem('auth_token', data.access_token);
        }
        return data;
    },

    logout() {
        localStorage.removeItem('auth_token');
    },

    async getMe(): Promise<User> {
        const res = await fetch(`${API_BASE}/auth/me`, {
            headers: getAuthHeaders()
        });
        return handleResponse<User>(res);
    },

    // --- SETTINGS ---
    async getSettings(): Promise<Settings> {
        const res = await fetch(`${API_BASE}/settings`, { headers: getAuthHeaders() });
        return handleResponse<Settings>(res);
    },

    async updateSettings(settings: Partial<Settings>): Promise<Settings> {
        const res = await fetch(`${API_BASE}/settings`, {
            method: 'PUT',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        return handleResponse<Settings>(res);
    },

    // --- GAMES ---
    async getGames(status?: string): Promise<Game[]> {
        const url = status ? `${API_BASE}/games?status=${status}` : `${API_BASE}/games`;
        const res = await fetch(url, { headers: getAuthHeaders() });
        return handleResponse<Game[]>(res);
    },

    async getGame(id: number): Promise<Game> {
        const res = await fetch(`${API_BASE}/games/${id}`, { headers: getAuthHeaders() });
        return handleResponse<Game>(res);
    },

    async createGame(game: Partial<Game>): Promise<Game> {
        const res = await fetch(`${API_BASE}/games`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(game)
        });
        return handleResponse<Game>(res);
    },

    async updateGame(id: number, game: Partial<Game>): Promise<Game> {
        const res = await fetch(`${API_BASE}/games/${id}`, {
            method: 'PUT',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(game)
        });
        return handleResponse<Game>(res);
    },

    async deleteGame(id: number): Promise<{ ok: boolean }> {
        const res = await fetch(`${API_BASE}/games/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean }>(res);
    },

    async searchSteam(query: string): Promise<Partial<Game>[]> {
        const res = await fetch(`${API_BASE}/games/search/steam?query=${encodeURIComponent(query)}`);
        return handleResponse<Partial<Game>[]>(res);
    },

    // --- CHECKLIST ---
    async getChecklist(gameId: number): Promise<ChecklistItem[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist`, { headers: getAuthHeaders() });
        return handleResponse<ChecklistItem[]>(res);
    },

    async createChecklistItem(gameId: number, item: Partial<ChecklistItem>): Promise<ChecklistItem> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        return handleResponse<ChecklistItem>(res);
    },

    async getChecklistCategories(gameId: number): Promise<QuestCategory[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist/categories`, { headers: getAuthHeaders() });
        return handleResponse<QuestCategory[]>(res);
    },

    async createChecklistCategory(gameId: number, name: string): Promise<QuestCategory> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist/categories`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        return handleResponse<QuestCategory>(res);
    },

    async renameChecklistCategory(gameId: number, oldName: string, newName: string): Promise<{ ok: boolean; category: string; updated_items: number }> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist/categories/${encodeURIComponent(oldName)}`, {
            method: 'PUT',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: newName })
        });
        return handleResponse<{ ok: boolean; category: string; updated_items: number }>(res);
    },

    async completeChecklistItem(itemId: number, completed: boolean): Promise<ChecklistItem> {
        const res = await fetch(`${API_BASE}/checklist/${itemId}?completed=${completed}`, {
            method: 'PUT',
            headers: getAuthHeaders()
        });
        return handleResponse<ChecklistItem>(res);
    },

    async deleteChecklistItem(itemId: number): Promise<{ ok: boolean }> {
        const res = await fetch(`${API_BASE}/checklist/${itemId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean }>(res);
    },

    async deleteChecklistCategory(gameId: number, category: string): Promise<{ ok: boolean }> {
        const res = await fetch(`${API_BASE}/games/${gameId}/checklist/category/${encodeURIComponent(category)}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean }>(res);
    },

    // --- NOTES ---
    async getNotes(gameId: number): Promise<Note[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/notes`, { headers: getAuthHeaders() });
        return handleResponse<Note[]>(res);
    },

    async createNote(gameId: number, item: Partial<Note>): Promise<Note> {
        const res = await fetch(`${API_BASE}/games/${gameId}/notes`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(item)
        });
        return handleResponse<Note>(res);
    },

    async updateNote(noteId: number, text: string): Promise<Note> {
        const res = await fetch(`${API_BASE}/notes/${noteId}?text=${encodeURIComponent(text)}`, {
            method: 'PUT',
            headers: getAuthHeaders()
        });
        return handleResponse<Note>(res);
    },

    async deleteNote(noteId: number): Promise<{ ok: boolean }> {
        const res = await fetch(`${API_BASE}/notes/${noteId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean }>(res);
    },

    // --- ACHIEVEMENTS & WIKI ---
    async importWikiChecklist(gameId: number, url: string): Promise<ChecklistItem[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/import/wiki`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        return handleResponse<ChecklistItem[]>(res);
    },

    async getAchievements(gameId: number): Promise<Achievement[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/achievements`, { headers: getAuthHeaders() });
        return handleResponse<Achievement[]>(res);
    },

    async syncSteamAchievements(gameId: number): Promise<Achievement[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/sync/steam/achievements`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        return handleResponse<Achievement[]>(res);
    },

    async syncSteamManual(gameId: number): Promise<{ ok: boolean; added_minutes: number }> {
        const res = await fetch(`${API_BASE}/games/${gameId}/sync/steam/manual`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean; added_minutes: number }>(res);
    },

    async getSessions(gameId: number): Promise<GameSession[]> {
        const res = await fetch(`${API_BASE}/games/${gameId}/sessions`, { headers: getAuthHeaders() });
        return handleResponse<GameSession[]>(res);
    },

    // --- AGENT ---
    async downloadAgent(): Promise<Blob> {
        const res = await fetch(`${API_BASE}/agent/download`);
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new ApiError(res.status, errorData.detail || 'Failed to download agent');
        }
        return res.blob();
    },

    async getAgentGames(): Promise<Game[]> {
        const res = await fetch(`${API_BASE}/agent/games`, { headers: getAuthHeaders() });
        return handleResponse<Game[]>(res);
    },

    async configureAgent(game_id: number, launch_path: string, enabled: boolean = true): Promise<AgentConfigResponse> {
        const res = await fetch(`${API_BASE}/agent/configure`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id, launch_path, enabled })
        });
        return handleResponse<AgentConfigResponse>(res);
    },

    async deleteAgentConfig(gameId: number): Promise<{ ok: boolean }> {
        const res = await fetch(`${API_BASE}/agent/config/${gameId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean }>(res);
    },

    async testAgentPing(gameId: number): Promise<{ ok: boolean, message: string, exe_name: string, status: string, duration_minutes?: number }> {
        const res = await fetch(`${API_BASE}/agent/test-ping`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId })
        });
        return handleResponse<{ ok: boolean, message: string, exe_name: string, status: string, duration_minutes?: number }>(res);
    },

    async requestAgentLaunch(gameId: number): Promise<{ ok: boolean, message: string, request_id: string }> {
        const res = await fetch(`${API_BASE}/agent/launch`, {
            method: 'POST',
            headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameId })
        });
        return handleResponse<{ ok: boolean, message: string, request_id: string }>(res);
    },

    async getAgentToken(): Promise<{ ok: boolean, agent_token: string }> {
        const res = await fetch(`${API_BASE}/agent/token`, { headers: getAuthHeaders() });
        return handleResponse<{ ok: boolean, agent_token: string }>(res);
    },

    async rotateAgentToken(): Promise<{ ok: boolean, agent_token: string }> {
        const res = await fetch(`${API_BASE}/agent/token/rotate`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        return handleResponse<{ ok: boolean, agent_token: string }>(res);
    }
};


export type SteamImageSet = {
    poster: string;
    poster2x: string;
    hero: string;
    heroBlur: string;
    header: string;
    capsuleMain: string;
};

export type SteamImageCarrier = {
    cover_url?: string;
    steam_app_id?: number;
    cover_urls?: Partial<Record<'poster' | 'poster2x' | 'hero' | 'hero_blur' | 'header' | 'capsule_main', string>>;
};

function buildSteamBaseUrl(appId: number): string {
    return `https://cdn.akamai.steamstatic.com/steam/apps/${appId}`;
}

export function buildSteamImageSet(appId: number): SteamImageSet {
    const base = buildSteamBaseUrl(appId);
    return {
        poster: `${base}/library_600x900.jpg`,
        poster2x: `${base}/library_600x900_2x.jpg`,
        hero: `${base}/library_hero.jpg`,
        heroBlur: `${base}/library_hero_blur.jpg`,
        header: `${base}/header.jpg`,
        capsuleMain: `${base}/capsule_616x353.jpg`
    };
}

function isWideSteamAsset(url: string): boolean {
    return /\/header\.jpg$|\/capsule_\d+x\d+\.jpg$|\/library_hero(_blur)?\.jpg$/i.test(url);
}

export function pickSteamPoster(input: SteamImageCarrier): { src: string; fallback?: string } {
    const appId = input.steam_app_id;
    if (!appId) {
        return { src: input.cover_url || '' };
    }

    const set = buildSteamImageSet(appId);
    const explicitPoster = input.cover_urls?.poster2x || input.cover_urls?.poster;
    if (explicitPoster) {
        return { src: explicitPoster, fallback: input.cover_urls?.header || set.header };
    }

    if (input.cover_url && !isWideSteamAsset(input.cover_url)) {
        return { src: input.cover_url, fallback: set.header };
    }

    return { src: set.poster2x, fallback: set.header };
}

export function pickSteamHero(input: SteamImageCarrier): { src: string; fallback?: string } {
    const appId = input.steam_app_id;
    if (!appId) {
        return { src: input.cover_url || '' };
    }

    const set = buildSteamImageSet(appId);
    const hero = input.cover_urls?.hero || set.hero;
    const fallback = input.cover_urls?.header || input.cover_url || set.header;
    return { src: hero, fallback };
}

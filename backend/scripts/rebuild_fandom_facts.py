import argparse

from app.integrations.fandom_facts import (
    DEFAULT_SEED_URLS,
    collect_facts_from_fandom_page,
    collect_fandom_facts,
    save_facts_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build game facts JSON from Fandom wikis")
    parser.add_argument("--per-seed-limit", type=int, default=60)
    parser.add_argument("--max-facts", type=int, default=600)
    parser.add_argument("--seed", action="append", dest="seeds", help="Fandom wiki URL seed (repeatable)")
    parser.add_argument("--page-url", type=str, default="", help="Single Fandom page URL")
    parser.add_argument("--game", type=str, default="", help="Game name for single page mode")
    args = parser.parse_args()

    if args.page_url:
        facts = collect_facts_from_fandom_page(
            page_url=args.page_url,
            game=args.game or None,
            max_facts=max(1, args.max_facts),
        )
    else:
        seeds = args.seeds if args.seeds else DEFAULT_SEED_URLS
        facts = collect_fandom_facts(
            seed_urls=seeds,
            per_seed_limit=max(1, args.per_seed_limit),
            max_facts=max(1, args.max_facts),
        )
    path = save_facts_json(facts)
    print(f"Saved {len(facts)} facts to {path}")


if __name__ == "__main__":
    main()

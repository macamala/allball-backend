"""Pass-4 mapping table for unresolved competitions. No live fetch."""

from __future__ import annotations

import json

from collector.registry import build_runtime_registry

UNRESOLVED = [
    "afc-champions-league",
    "argentina-primera",
    "brazil-lnf",
    "bwf-and-national-events",
    "caf-champions-league",
    "chile-primera",
    "copa-sudamericana",
    "denmark-superliga",
    "fifa-futsal-when-listed",
    "france-letrot-meetings",
    "france-pro-d2",
    "france-top-14",
    "gbgb-meetings",
    "germany-click-tt",
    "germany-handball-bundesliga",
    "india-super-league",
    "iran-pro-league",
    "malaysia-super-league",
    "mexico-lnbp",
    "nsw-hrnsw-meetings",
    "poland-ekstraklasa",
    "slovakia-super-liga",
    "spain-acb",
    "sweden-allsvenskan",
    "tour-de-france",
    "uci-calendar",
    "uruguay-primera",
    "wnba",
    "australia-a-league",
    "australia-a-league-women",
    "bulgaria-first-league",
    "futsalplanet-leagues-cups",
    "tunisia-ligue-1",
    "vietnam-v-league-1",
    "africa-cup-of-nations",
    "korean-golf-tour",
    "nrl",
    "usa-nwsl",
    "super-rugby",
]


def main() -> None:
    runtime = build_runtime_registry()
    rows = []
    for cid in UNRESOLVED:
        spec = runtime["competitions"].get(cid) or {}
        srcs = [s for s in spec.get("sources") or [] if s.get("enabled")]
        all_srcs = spec.get("sources") or []
        print(f"\n{cid} sport={spec.get('sport')} enabled={len(srcs)} total_maps={len(all_srcs)}")
        for s in all_srcs:
            cfg = s.get("source_config") or {}
            print(
                f"  en={s.get('enabled')} pri={s.get('priority')} fam={s.get('source_family')} "
                f"adapter={s.get('adapter_key')} cov={s.get('coverage')} "
                f"url={cfg.get('url')} src={s.get('source_id')[:60]}"
            )
            rows.append(
                {
                    "competition": cid,
                    "enabled": s.get("enabled"),
                    "family": s.get("source_family"),
                    "adapter": s.get("adapter_key"),
                    "priority": s.get("priority"),
                    "url": cfg.get("url"),
                    "coverage": s.get("coverage"),
                    "source_id": s.get("source_id"),
                    "source_competition_id": s.get("source_competition_id"),
                }
            )
    json.dump(rows, open("pass4_mappings.json", "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()

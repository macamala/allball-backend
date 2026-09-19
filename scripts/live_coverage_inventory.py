"""Build the observed live-capability matrix from the current database."""

from database import SessionLocal
from collector.live_capability import build_inventory


def main() -> None:
    db = SessionLocal()
    try:
        payload = build_inventory(db)
        print(
            {
                "competitions": payload["total_enabled_competitions"],
                "families": payload["total_provider_families"],
                "classes": payload["class_counts"],
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

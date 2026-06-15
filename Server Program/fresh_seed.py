"""Command-line entrypoint for Laravel-style fresh DB seeding."""

from __future__ import annotations

import argparse
import getpass
import sys

from server_app.core.config import ConfigManager
from server_app.db.fresh_seed import DemoSeedOptions, fresh_seed_database, profile_for_scale, validate_fresh_mode


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Drop/recreate the configured DB schema and seed demo ERP data.",
    )
    parser.add_argument("--mode", choices=("tables", "database"), default="tables")
    parser.add_argument("--yes", action="store_true", help="Skip the destructive confirmation prompt.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without changing the DB.")
    parser.add_argument("--super-admin-password", help="Password for the fixed super_admin account.")
    parser.add_argument("--demo-user-password", default="password123", help="Password for seeded demo users.")
    parser.add_argument("--scale", choices=("small", "medium", "large"), default="small")
    parser.add_argument("--seed", type=int, help="Integer seed for reproducible fake data.")
    return parser


def _load_config(config_manager: ConfigManager):
    """Load the saved application config or raise a user-facing error."""

    if not config_manager.exists():
        raise RuntimeError("No saved server config found. Run first setup before fresh seeding.")
    return config_manager.load()


def _confirm(config, mode: str) -> bool:
    """Ask the operator to confirm the destructive reset."""

    expected = config.database.database
    answer = input(
        f"Type the database name '{expected}' to confirm fresh seed in {mode!r} mode: "
    ).strip()
    return answer == expected


def main(argv: list[str] | None = None) -> int:
    """Run the fresh seed command and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        validate_fresh_mode(args.mode)
        profile = profile_for_scale(args.scale)
        config = _load_config(ConfigManager())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("[INFO] Fresh seed target:")
    print(f"  server:   {config.database.server}")
    print(f"  database: {config.database.database}")
    print(f"  mode:     {args.mode}")
    print(f"  scale:    {args.scale}")
    print(f"  seed:     {args.seed if args.seed is not None else 'random'}")
    print(
        "  profile:  "
        f"{profile.user_copies_per_role} user(s)/role, "
        f"{profile.product_count} products, "
        f"{profile.counterparty_count} counterparties, "
        f"{profile.service_count} services"
    )

    if args.dry_run:
        print("[OK] Dry run complete. No database changes were made.")
        return 0

    if not args.yes and not _confirm(config, args.mode):
        print("[INFO] Fresh seed cancelled.")
        return 1

    super_admin_password = args.super_admin_password
    if not super_admin_password:
        super_admin_password = getpass.getpass("New super_admin password: ")
    if not super_admin_password:
        print("[ERROR] Super Admin password is required.", file=sys.stderr)
        return 1

    try:
        options = DemoSeedOptions(
            super_admin_password=super_admin_password,
            demo_user_password=args.demo_user_password,
            scale=args.scale,
            seed=args.seed,
        )
        result = fresh_seed_database(config, options, mode=args.mode)
    except Exception as exc:
        print(f"[ERROR] Fresh seed failed: {exc}", file=sys.stderr)
        return 1

    print("[OK] Database was freshly migrated and seeded.")
    print("[INFO] Seeded table counts:")
    for table_name, count in sorted(result.table_counts.items()):
        print(f"  {table_name}: {count}")
    print(f"[INFO] Demo users use password: {args.demo_user_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

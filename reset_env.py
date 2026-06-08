"""Helper script to reset the ERP Accounting Server to its initial state.

Equivalents to Laravel commands:
- Clear settings and drop DB: php artisan migrate:fresh --seed (clean slate)
- Clear cache: php artisan optimize:clear (python bytecode purge)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Add project root to path so we can import server_app modules
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

try:
    from sqlalchemy import text
    from server_app.core.config import ConfigManager
    from server_app.db.session import create_db_engine
    from server_app.db.bootstrap import create_database_if_missing, run_migrations
except ImportError as exc:
    print(f"Error: Missing dependencies. Please run within your python environment: {exc}")
    sys.exit(1)


def clear_bytecode_cache() -> None:
    """Clear __pycache__ directories and compile files (equivalent of optimize:clear)."""
    print("🧹 Clearing Python bytecode cache...")
    count = 0
    for path in project_root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path)
            count += 1
    for path in project_root.rglob("*.pyc"):
        if path.is_file():
            path.unlink()
            count += 1
    print(f"✅ Cleared {count} cache folders/files.")


def drop_mssql_database(config) -> None:
    """Drop the configured MSSQL database by forcing connections closed."""
    db_name = config.database.database
    print(f"🗑️ Dropping MSSQL database '{db_name}'...")
    
    # We must connect to the 'master' database to drop the application database
    engine = create_db_engine(config, database_override="master")
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            # Check if database exists
            exists = connection.execute(
                text("SELECT 1 FROM sys.databases WHERE name = :name"),
                {"name": db_name},
            ).scalar_one_or_none()
            
            if exists:
                print("⚠️  Forcing all active database connections to close...")
                # Put in single-user mode to close active connections, then drop
                connection.execute(text(f"ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"))
                connection.execute(text(f"DROP DATABASE [{db_name}]"))
                print(f"✅ Database '{db_name}' dropped successfully.")
            else:
                print(f"ℹ️  Database '{db_name}' does not exist.")
    except Exception as exc:
        print(f"❌ Failed to drop database: {exc}")
        print("Note: Ensure your SQL Server instance is running and your user has permissions to drop databases.")
    finally:
        engine.dispose()


def clear_config_settings(config_manager: ConfigManager) -> None:
    """Delete the application settings file (equivalent of first-run state reset)."""
    config_path = config_manager.path
    if config_path.exists():
        print(f"🗑️ Removing configuration file at: {config_path}")
        try:
            config_path.unlink()
            # If the directory is now empty, remove it too
            if config_path.parent.exists() and not any(config_path.parent.iterdir()):
                config_path.parent.rmdir()
            print("✅ Configuration settings cleared. The app will launch in first-run setup mode.")
        except Exception as exc:
            print(f"❌ Failed to delete configuration file: {exc}")
    else:
        print(f"ℹ️  No saved configuration found at {config_path} (already in initial state).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset ERP Accounting Server database, configuration, and caches."
    )
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Only drop the database, keeping config.json intact."
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Only clear __pycache__ directories."
    )
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Only delete the saved configuration settings."
    )
    args = parser.parse_args()

    config_manager = ConfigManager()
    config = None
    if config_manager.exists():
        try:
            config = config_manager.load()
        except Exception as exc:
            print(f"⚠️  Could not load configuration file: {exc}")

    # 1. Purge Cache
    if args.cache_only:
        clear_bytecode_cache()
        return

    # 2. Rebuild/Reset database & config
    if args.config_only:
        clear_config_settings(config_manager)
        return

    if args.db_only:
        if config:
            drop_mssql_database(config)
        else:
            print("❌ Cannot drop database: config.json does not exist. Run in full reset mode.")
        return

    # Full Reset (Default)
    print("🚀 Starting FULL environment reset...")
    if config:
        drop_mssql_database(config)
    clear_config_settings(config_manager)
    clear_bytecode_cache()
    print("\n✨ Environment successfully reset to the initial state!")
    print("👉 Next step: run 'python server.py' to launch the first-run GUI and recreate the database.")


if __name__ == "__main__":
    main()

"""Synchronize checked-in theory data into PostgreSQL."""

import argparse
import asyncio
import os
from pathlib import Path

from app.database.session import create_session_factory
from app.services.theory.importer import TheoryImporter

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT / "data" / "theory",
        help="Theory repository root (default: %(default)s)",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="SQLAlchemy async URL (default: DATABASE_URL)",
    )
    arguments = parser.parse_args()
    if not arguments.database_url:
        parser.error("DATABASE_URL is required")
    return arguments


async def run() -> None:
    arguments = parse_arguments()
    factory = create_session_factory(arguments.database_url)
    async with factory() as session:
        report = await TheoryImporter(session).synchronize(arguments.root)
    print(
        "Synchronized "
        f"{report.knowledge_elements} knowledge elements and {report.questions} questions; "
        f"deactivated {report.deactivated_knowledge_elements} elements and "
        f"{report.deactivated_questions} questions."
    )


if __name__ == "__main__":
    asyncio.run(run())

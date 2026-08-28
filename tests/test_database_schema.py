import unittest

from sqlalchemy import create_engine, inspect

import app.database.models  # noqa: F401
from app.database.base import Base


class DatabaseSchemaTests(unittest.TestCase):
    def test_required_tables_are_present_in_metadata(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        table_names = set(inspect(engine).get_table_names())
        self.assertTrue(
            {
                "users",
                "topics",
                "subtopics",
                "sources",
                "knowledge_elements",
                "questions",
                "question_options",
                "attempts",
                "progress",
                "review_schedule",
                "user_settings",
            }.issubset(table_names)
        )

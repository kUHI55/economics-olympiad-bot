from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.learning import ReviewSchedule


class LearningRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def due_review_element_ids(self, user_id: int, limit: int = 20) -> list[int]:
        query = (
            select(ReviewSchedule.knowledge_element_id)
            .where(
                ReviewSchedule.user_id == user_id, ReviewSchedule.next_review <= datetime.now(UTC)
            )
            .order_by(ReviewSchedule.next_review)
            .limit(limit)
        )
        return list(await self.session.scalars(query))

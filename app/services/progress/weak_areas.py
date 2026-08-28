from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.learning import Progress


class WeakAreasService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def element_ids(self, user_id: int, limit: int = 20) -> list[int]:
        query = (
            select(Progress.knowledge_element_id)
            .where(Progress.user_id == user_id, Progress.attempts_count > 0)
            .order_by(Progress.mastery_score, Progress.last_attempt_at)
            .limit(limit)
        )
        return list(await self.session.scalars(query))

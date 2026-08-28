from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.user import User, UserSettings


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self, telegram_id: int, username: str | None, display_name: str | None, is_admin: bool
    ) -> User:
        user = await self.session.scalar(
            select(User).options(selectinload(User.settings)).where(User.telegram_id == telegram_id)
        )
        if user:
            user.username = username
            user.display_name = display_name
            user.is_admin = is_admin
            return user
        user = User(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            is_admin=is_admin,
        )
        self.session.add(user)
        await self.session.flush()
        settings = UserSettings(user_id=user.id)
        user.settings = settings
        self.session.add(settings)
        return user

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.catalog import Section, Subtopic, Topic


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sections(self) -> list[Section]:
        return list(
            await self.session.scalars(select(Section).order_by(Section.sort_order, Section.name))
        )

    async def list_topics(self, section_id: int) -> list[Topic]:
        query = (
            select(Topic)
            .where(Topic.section_id == section_id)
            .order_by(Topic.sort_order, Topic.name)
        )
        return list(await self.session.scalars(query))

    async def list_subtopics(self, topic_id: int) -> list[Subtopic]:
        query = (
            select(Subtopic)
            .where(Subtopic.topic_id == topic_id)
            .order_by(Subtopic.sort_order, Subtopic.name)
        )
        return list(await self.session.scalars(query))

    async def create_section(self, name: str) -> Section:
        section = Section(name=name.strip())
        self.session.add(section)
        await self.session.flush()
        return section

    async def create_topic(self, section_id: int, name: str) -> Topic:
        topic = Topic(section_id=section_id, name=name.strip())
        self.session.add(topic)
        await self.session.flush()
        return topic

    async def create_subtopic(self, topic_id: int, name: str) -> Subtopic:
        subtopic = Subtopic(topic_id=topic_id, name=name.strip())
        self.session.add(subtopic)
        await self.session.flush()
        return subtopic

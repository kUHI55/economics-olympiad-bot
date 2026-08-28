import unittest

from app.core.enums import KnowledgeType, QuestionType, SourceType
from app.schemas.analysis import KnowledgeElementDraft, MaterialAnalysis, QuestionDraft
from app.services.theory.analyzer import SourceAnalyzerService


class FakeLlm:
    async def analyze_source_chunk(self, **kwargs) -> MaterialAnalysis:
        return MaterialAnalysis(
            source_name="Конспект",
            source_type=SourceType.TEXT,
            knowledge_elements=[
                KnowledgeElementDraft(
                    title="Рабочая сила",
                    knowledge_type=KnowledgeType.DEFINITION,
                    content="Занятые и безработные.",
                    source_excerpt="Рабочая сила включает занятых и безработных.",
                ),
                KnowledgeElementDraft(
                    title="Внешняя теория",
                    knowledge_type=KnowledgeType.TERM,
                    content="Этого нет в конспекте.",
                    source_excerpt="Несуществующая цитата.",
                ),
            ],
            questions=[
                QuestionDraft(
                    knowledge_element_index=0,
                    question="Что включает рабочая сила?",
                    question_type=QuestionType.DEFINITION,
                    reference_answer="Занятых и безработных.",
                    key_points=["занятые", "безработные"],
                    hint="Вспомни две группы из определения.",
                    explanation="Это определение из источника.",
                    source_excerpt="Рабочая сила включает занятых и безработных.",
                )
            ],
        )


class SourceAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_only_items_grounded_in_source(self) -> None:
        analysis = await SourceAnalyzerService(FakeLlm()).analyze(
            source_name="Конспект",
            source_type=SourceType.TEXT,
            content="Рабочая сила включает занятых и безработных.",
        )
        self.assertEqual(len(analysis.knowledge_elements), 1)
        self.assertEqual(analysis.knowledge_elements[0].title, "Рабочая сила")
        self.assertEqual(len(analysis.questions), 1)
        self.assertTrue(any("точной цитаты" in warning for warning in analysis.warnings))

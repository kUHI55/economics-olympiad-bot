from app.core.enums import SourceType
from app.schemas.analysis import KnowledgeElementDraft, MaterialAnalysis, QuestionDraft
from app.services.llm.client import LlmClient


def _compact(text: str) -> str:
    return " ".join(text.split())


def split_source_text(text: str, max_chars: int = 12_000) -> list[str]:
    """Split long sources along paragraphs; only source-ingestion calls see these chunks."""
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        elif len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[index : index + max_chars]
                for index in range(0, len(paragraph), max_chars)
            )
        else:
            current = f"{current}\n\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks or [text]


class SourceAnalyzerService:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    async def analyze(
        self, *, source_name: str, source_type: SourceType, content: str
    ) -> MaterialAnalysis:
        if not content.strip():
            raise ValueError("В материале нет текста для анализа.")
        all_elements: list[KnowledgeElementDraft] = []
        all_questions: list[QuestionDraft] = []
        warnings: list[str] = []
        compact_source = _compact(content)

        for chunk in split_source_text(content):
            proposal = await self.llm.analyze_source_chunk(
                source_name=source_name, source_type=source_type.value, content=chunk
            )
            offset = len(all_elements)
            grounded_elements = [
                element
                for element in proposal.knowledge_elements
                if _compact(element.source_excerpt) in compact_source
            ]
            dropped = len(proposal.knowledge_elements) - len(grounded_elements)
            if dropped:
                warnings.append(
                    f"Не сохранено элементов без точной цитаты из источника: {dropped}."
                )

            original_to_new = {
                old_index: offset + new_index
                for old_index, element in enumerate(proposal.knowledge_elements)
                for new_index, kept in enumerate(grounded_elements)
                if element is kept
            }
            all_elements.extend(grounded_elements)
            for question in proposal.questions:
                if (
                    question.knowledge_element_index in original_to_new
                    and _compact(question.source_excerpt) in compact_source
                ):
                    all_questions.append(
                        question.model_copy(
                            update={
                                "knowledge_element_index": original_to_new[
                                    question.knowledge_element_index
                                ]
                            }
                        )
                    )
                else:
                    warnings.append("Не сохранён вопрос без подтверждённой связи с источником.")
            warnings.extend(proposal.warnings)

        if not all_elements:
            warnings.append(
                "В сохранённом материале недостаточно информации для надёжных элементов знаний."
            )
        return MaterialAnalysis(
            source_name=source_name,
            source_type=source_type,
            knowledge_elements=all_elements,
            questions=all_questions,
            warnings=list(dict.fromkeys(warnings)),
        )

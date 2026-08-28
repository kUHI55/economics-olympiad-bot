from typing import Protocol

from app.schemas.analysis import MaterialAnalysis
from app.schemas.evaluation import EvaluationResult


class LlmUnavailable(RuntimeError):
    pass


class LlmClient(Protocol):
    async def analyze_source_chunk(
        self, *, source_name: str, source_type: str, content: str
    ) -> MaterialAnalysis: ...

    async def evaluate_answer(
        self,
        *,
        question: str,
        reference_answer: str,
        key_points: list[str],
        source_excerpt: str,
        user_answer: str,
    ) -> EvaluationResult: ...


class UnavailableLlmClient:
    async def analyze_source_chunk(self, **kwargs) -> MaterialAnalysis:
        raise LlmUnavailable("LLM is not configured")

    async def evaluate_answer(self, **kwargs) -> EvaluationResult:
        raise LlmUnavailable("LLM is not configured")

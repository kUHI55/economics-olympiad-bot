import json

from openai import AsyncOpenAI

from app.schemas.analysis import MaterialAnalysis
from app.schemas.evaluation import EvaluationResult

ANALYZE_SYSTEM_PROMPT = (
    "You extract a proposal from one user-provided economics source. The source is the sole authority. "
    "Do not add, correct, or complete theory from your own knowledge. Every proposed knowledge element and "
    "question must include a short, verbatim source_excerpt that directly supports it. If the text is insufficient, "
    "omit the item and add a warning in Russian. Generate only theory questions: definitions, formula, notation, "
    "understanding, causal relations, comparison, common mistake, or multiple choice. Do not create numerical "
    "or olympiad problems. Add a short hint that guides recall but does not state the answer. Return JSON matching "
    "the supplied schema."
)
EVALUATE_SYSTEM_PROMPT = (
    "Evaluate a student's answer only against the supplied reference answer, key points, and source excerpt. "
    "The excerpt is the authority; do not introduce external theory. Return JSON matching the schema. If the "
    "evidence or answer is ambiguous, use verdict uncertain. Never reveal the complete reference answer in "
    "short_explanation: give only a short directional response, because the student may retry."
)


class OpenAiLlmClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def analyze_source_chunk(
        self, *, source_name: str, source_type: str, content: str
    ) -> MaterialAnalysis:
        response = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Source name: {source_name}\nSource type: {source_type}\n\n"
                        f"SOURCE TEXT:\n{content}\n\n"
                        "Return source_name, source_type, knowledge_elements, questions and warnings."
                    ),
                },
            ],
        )
        payload = response.choices[0].message.content
        if not payload:
            raise ValueError("LLM returned an empty analysis")
        return MaterialAnalysis.model_validate(json.loads(payload))

    async def evaluate_answer(
        self,
        *,
        question: str,
        reference_answer: str,
        key_points: list[str],
        source_excerpt: str,
        user_answer: str,
    ) -> EvaluationResult:
        response = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": EVALUATE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": question,
                            "reference_answer": reference_answer,
                            "key_points": key_points,
                            "source_excerpt": source_excerpt,
                            "user_answer": user_answer,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        payload = response.choices[0].message.content
        if not payload:
            raise ValueError("LLM returned an empty evaluation")
        return EvaluationResult.model_validate(json.loads(payload))

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import AttemptVerdict


class EvaluationResult(BaseModel):
    """Structured feedback: never exposes the reference answer before the user asks for it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    verdict: AttemptVerdict
    score: float = Field(ge=0, le=1)
    what_is_correct: list[str] = Field(default_factory=list)
    what_is_wrong: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    short_explanation: str = Field(default="", max_length=1000)

    @field_validator("score")
    @classmethod
    def score_matches_verdict(cls, value: float, info) -> float:
        verdict = info.data.get("verdict")
        if verdict is AttemptVerdict.CORRECT and value < 0.8:
            raise ValueError("Correct answers must receive a high score")
        if verdict is AttemptVerdict.INCORRECT and value > 0.4:
            raise ValueError("Incorrect answers must receive a low score")
        return value


class FormulaComparisonResult(BaseModel):
    equivalent: bool
    normalised_answer: str
    normalised_reference: str
    reason: Literal["equivalent", "different", "unsupported"]

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenzoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenzoChatRequest(BenzoModel):
    question: str = Field(min_length=1, max_length=4_000)
    current_smiles: str | None = Field(default=None, max_length=20_000)

    @field_validator("question")
    @classmethod
    def reject_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must contain non-whitespace text")
        return value.strip()


class BenzoStructureSuggestion(BenzoModel):
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)
    smiles: str | None


class BenzoModelAnswer(BenzoModel):
    scope: Literal["ANSWERED", "OUT_OF_SCOPE"]
    answer: str = Field(min_length=1, max_length=1_600)
    suggestions: list[BenzoStructureSuggestion] = Field(max_length=4)


class BenzoChatResponse(BenzoModel):
    scope: Literal["ANSWERED", "OUT_OF_SCOPE"]
    answer: str
    suggestions: list[BenzoStructureSuggestion]
    model: str

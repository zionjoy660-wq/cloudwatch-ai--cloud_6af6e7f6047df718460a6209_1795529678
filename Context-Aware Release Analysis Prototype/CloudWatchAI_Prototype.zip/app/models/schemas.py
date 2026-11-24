"""Request models. FastAPI uses these to validate incoming JSON automatically."""
from typing import List

from pydantic import BaseModel, Field, field_validator


def _clean_list(values):
    """Strip blanks and duplicates from a list of short strings."""
    seen, result = set(), []
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result


class TeamProfile(BaseModel):
    team_name: str = Field(default="Cloud Platform Team", max_length=100)
    services: List[str] = Field(
        default_factory=lambda: ["AWS", "Azure", "Google Cloud", "Kubernetes", "Terraform"],
        max_length=50,
    )
    projects: List[str] = Field(
        default_factory=lambda: ["cloud migration", "container platform", "observability"],
        max_length=50,
    )
    risk_tolerance: str = Field(default="moderate", max_length=30)
    additional_context: str = Field(default="", max_length=2000)

    @field_validator("services", "projects")
    @classmethod
    def clean_lists(cls, value):
        return _clean_list(value)

    @field_validator("team_name")
    @classmethod
    def default_team_name(cls, value):
        return value.strip() or "Cloud Platform Team"


class AnalyzeRequest(BaseModel):
    update_id: str = Field(min_length=1, max_length=64)
    team_profile: TeamProfile = Field(default_factory=TeamProfile)


class DigestRequest(BaseModel):
    team_profile: TeamProfile = Field(default_factory=TeamProfile)
    # Only updates with a known publish date are filtered by this window;
    # records without a date (demo data, page captures) are always included.
    days: int = Field(default=30, ge=1, le=365)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    team_profile: TeamProfile = Field(default_factory=TeamProfile)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Please type a question (at least 3 characters).")
        return value


class MemoryCreate(BaseModel):
    """Team context entered by the user on the Team memory page."""
    title: str = Field(default="Team context", max_length=150)
    content: str = Field(min_length=1, max_length=4000)
    services: List[str] = Field(default_factory=list, max_length=30)

    @field_validator("title")
    @classmethod
    def default_title(cls, value):
        return value.strip() or "Team context"

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Memory content is required.")
        return value.strip()

    @field_validator("services")
    @classmethod
    def clean_services(cls, value):
        return _clean_list(value)

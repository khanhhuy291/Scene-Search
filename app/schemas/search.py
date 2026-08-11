"""Semantic scene-search request and response contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    video_id: str | None = Field(default=None, min_length=1, max_length=255)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    scene_id: str
    video_id: str
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    score: float = Field(ge=0.0, le=1.0)
    thumbnail_url: str | None = None

    @model_validator(mode="after")
    def end_must_follow_start(self) -> SearchResult:
        if self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")
        return self


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    total: int = Field(ge=0)
    took_ms: float = Field(ge=0.0)


__all__ = ["SearchRequest", "SearchResponse", "SearchResult"]

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from model_story.enums import Grade, Phase, TaskType


class RawLogLine(BaseModel):
    seq: int
    timestamp: datetime
    source: Literal["stdin", "file", "sdk", "ssh"]
    text: str


class RawMetric(BaseModel):
    seq: int
    epoch: float | None = None
    step: int | None = None
    key: str
    value: float | str
    parser_name: str
    confidence: float = Field(ge=0.0, le=1.0)


class MetricEvent(BaseModel):
    run_id: str
    seq: int
    timestamp: datetime
    epoch: float | None = None
    step: int | None = None
    canonical_key: str
    raw_key: str
    value: float
    unit: str | None = None
    task_hint: TaskType | None = None


class MetaphorCard(BaseModel):
    title: str
    body: str
    icon: str = ""
    color: str = ""


class Milestone(BaseModel):
    run_id: str
    seq: int
    kind: str
    epoch: float | None = None
    value: float | None = None
    message: str


class Warning(BaseModel):
    kind: Literal["overfit", "plateau", "divergence", "lr_drop"]
    epoch: float | None = None
    message: str


class StoryFrame(BaseModel):
    run_id: str
    seq: int
    epoch: float | None = None
    progress: float = Field(ge=0.0, le=1.0)
    phase: Phase
    grade: Grade
    primary_metric_value: float
    confidence: float = Field(ge=0.0, le=1.0)
    narrative: str
    metaphor_cards: list[MetaphorCard] = Field(default_factory=list)
    skill_dimensions: dict[str, float] = Field(default_factory=dict)
    milestones: list[Milestone] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    task_type: TaskType


class Run(BaseModel):
    id: str
    name: str | None = None
    task_type: TaskType
    started_at: datetime
    finished_at: datetime | None = None
    primary_metric: str
    framework_detected: str | None = None
    parser_used: str
    total_epochs_est: int | None = None
    final_grade: Grade | None = None
    story_summary: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class WSMessage(BaseModel):
    v: int = 1
    type: Literal["story_frame", "milestone", "warning", "complete", "ping"]
    run_id: str
    seq: int
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

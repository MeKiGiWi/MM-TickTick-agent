from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


TaskStatus = Literal["normal", "completed"]
ClarifyClassification = Literal["single_action", "project", "unclear"]


class Task(BaseModel):
    id: str
    title: str
    project_id: str = "inbox"
    status: TaskStatus = "normal"
    priority: int = 0
    due_date: Optional[str] = None
    content: Optional[str] = None
    is_overdue: bool = False
    tags: list[str] = Field(default_factory=list)
    subtasks: list["Task"] = Field(default_factory=list)


class Project(BaseModel):
    id: str
    name: str
    kind: Literal["TASK", "NOTE"] = "TASK"


class ClarifyAssessment(BaseModel):
    task_id: str
    title: str
    classification: ClarifyClassification
    concrete: bool
    vague: bool
    needs_breakdown: bool
    reasoning: str
    suggested_subtasks: list[str] = Field(default_factory=list)


class TickTickCredentials(BaseModel):
    provider: Literal["mock", "ticktick"] = "mock"
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    access_token: str = ""
    scope: str = "tasks:write tasks:read"
    auth_state: str = ""
    inbox_project_id: str = "inbox"


class OpenRouterConfig(BaseModel):
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "meta-llama/llama-3.3-70b-instruct:free"


class AppConfig(BaseModel):
    openrouter: OpenRouterConfig
    ticktick: TickTickCredentials

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


TaskStatus = Literal["normal", "completed"]


class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    title: str
    project_id: str = Field(
        default="inbox",
        validation_alias=AliasChoices("project_id", "projectId"),
    )
    project_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("project_name", "projectName"),
    )
    status: TaskStatus = "normal"
    priority: int = 0
    due_date: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("due_date", "dueDate"),
    )
    start_date: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("start_date", "startDate"),
    )
    is_all_day: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_all_day", "isAllDay"),
    )
    time_zone: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("time_zone", "timeZone"),
    )
    content: Optional[str] = None
    is_overdue: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_overdue", "isOverdue"),
    )
    tags: list[str] = Field(default_factory=list)
    subtasks: list["Task"] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: Any) -> TaskStatus:
        if value in ("normal", "open", 0, "0", None):
            return "normal"
        if value in ("completed", 2, "2"):
            return "completed"
        raise ValueError(f"Unsupported TickTick task status: {value}")


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(validation_alias=AliasChoices("id", "projectId"))
    name: str = Field(validation_alias=AliasChoices("name", "projectName"))
    kind: Literal["TASK", "NOTE"] = "TASK"


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
    model: str = "qwen/qwen-turbo"
    fallback_models: list[str] = Field(default_factory=list)
    reasoning_enabled: bool = True


class AppConfig(BaseModel):
    openrouter: OpenRouterConfig
    ticktick: TickTickCredentials
    user_timezone: Optional[str] = None

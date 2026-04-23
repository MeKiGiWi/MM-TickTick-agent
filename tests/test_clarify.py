from app.agents.clarify import ClarifyAgent
from app.domain.models import Task


def test_clarify_marks_large_task_for_breakdown() -> None:
    agent = ClarifyAgent()
    assessment = agent.assess_task(Task(id="1", title="Разобрать inbox по GTD"))
    assert assessment.needs_breakdown is True
    assert assessment.classification in {"project", "unclear"}
    assert 3 <= len(assessment.suggested_subtasks) <= 5


def test_clarify_keeps_small_task_concrete() -> None:
    agent = ClarifyAgent()
    assessment = agent.assess_task(Task(id="2", title="Купить молоко"))
    assert assessment.concrete is True
    assert assessment.needs_breakdown is False

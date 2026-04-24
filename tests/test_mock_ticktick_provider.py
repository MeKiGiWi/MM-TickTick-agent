from __future__ import annotations

import pytest

from app.providers.mock.ticktick import MockTickTickProvider


def test_mock_move_parent_task_moves_subtasks_together() -> None:
    provider = MockTickTickProvider()
    parent = provider.create_task(title="Parent", project_id="inbox")
    subtasks = provider.create_subtasks(parent.id, ["One", "Two"])

    moved = provider.move_task(parent.id, "work")

    assert moved.project_id == "work"
    assert provider.get_task_details(parent.id).project_id == "work"
    assert [provider.get_task_details(item.id).project_id for item in subtasks] == ["work", "work"]


def test_mock_move_subtask_alone_refuses_to_detach() -> None:
    provider = MockTickTickProvider()
    parent = provider.create_task(title="Parent", project_id="inbox")
    subtask = provider.create_subtasks(parent.id, ["One"])[0]

    with pytest.raises(ValueError, match="Нельзя переместить подзадачу отдельно"):
        provider.move_task(subtask.id, "work")

    assert provider.get_task_details(subtask.id).project_id == "inbox"

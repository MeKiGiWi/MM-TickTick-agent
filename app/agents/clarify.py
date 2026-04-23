from __future__ import annotations

from app.domain.models import ClarifyAssessment, Task


class ClarifyAgent:
    VAGUE_MARKERS = {
        "разобрать",
        "организовать",
        "подготовить",
        "спланировать",
        "сделать",
        "починить",
        "улучшить",
    }

    PROJECT_MARKERS = {"и", "по", "план", "проект", "организовать", "спланировать"}

    def assess_task(self, task: Task) -> ClarifyAssessment:
        text = f"{task.title} {task.content or ''}".lower()
        concrete = len(task.title.split()) <= 4 and not any(
            marker in text for marker in self.VAGUE_MARKERS
        )
        vague = not concrete
        looks_project = len(task.title.split()) >= 3 and any(
            marker in text for marker in self.PROJECT_MARKERS
        )
        classification = "single_action"
        if looks_project:
            classification = "project"
        elif vague:
            classification = "unclear"

        needs_breakdown = classification in {"project", "unclear"} or len(task.title.split()) >= 5
        reasoning = self._build_reasoning(classification, vague, needs_breakdown)
        suggestions = self._suggest_subtasks(task) if needs_breakdown else []
        return ClarifyAssessment(
            task_id=task.id,
            title=task.title,
            classification=classification,
            concrete=concrete,
            vague=vague,
            needs_breakdown=needs_breakdown,
            reasoning=reasoning,
            suggested_subtasks=suggestions,
        )

    def assess_tasks(self, tasks: list[Task]) -> list[ClarifyAssessment]:
        return [self.assess_task(task) for task in tasks]

    def _build_reasoning(
        self,
        classification: str,
        vague: bool,
        needs_breakdown: bool,
    ) -> str:
        parts = [f"classification={classification}"]
        parts.append("формулировка размыта" if vague else "формулировка конкретная")
        if needs_breakdown:
            parts.append("нужна декомпозиция на шаги")
        return "; ".join(parts)

    def _suggest_subtasks(self, task: Task) -> list[str]:
        title = task.title.lower()
        if "gtd" in title or "inbox" in title:
            return [
                "Собрать все входящие задачи в один список",
                "Отсеять мусор и удалить неактуальное",
                "Задачи на 2 минуты выполнить сразу",
                "Остальное распределить по следующим действиям",
                "Назначить даты только там, где есть реальный дедлайн",
            ]
        if "отчет" in title:
            return [
                "Собрать исходные данные и источники",
                "Проверить полноту и корректность цифр",
                "Подготовить черновую структуру отчета",
                "Заполнить разделы фактами и выводами",
                "Сделать финальную вычитку и отправить",
            ]
        if "отпуск" in title:
            return [
                "Определить бюджет и допустимые даты",
                "Выбрать 2-3 направления для сравнения",
                "Проверить билеты и жилье",
                "Собрать список документов и ограничений",
                "Зафиксировать маршрут и бронирования",
            ]
        return [
            "Уточнить ожидаемый результат",
            "Собрать входные данные",
            "Выделить первый конкретный шаг",
            "Разбить работу на 3-5 коротких действий",
        ]

from __future__ import annotations

import logging

import httpx

from core.telegram_bot_listener.json_types import JsonDict
from core.telegram_bot_listener.models import SurveySession

logger = logging.getLogger(__name__)


class TelegramBotEventForwarder:
    def __init__(
        self,
        *,
        events_engine_url: str,
        target_agent_slug: str,
        source_slug: str = "telegram_bot_listener",
    ) -> None:
        self._events_engine_url = events_engine_url.rstrip("/")
        self._target_agent_slug = target_agent_slug
        self._source_slug = source_slug
        self._client = httpx.AsyncClient(timeout=30.0, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def publish_survey_finished(self, session: SurveySession) -> None:
        delivery = {
            "agent_slug": self._target_agent_slug,
            "event_data": self._delivery_payload(session),
        }
        endpoint = f"{self._events_engine_url}/deliver"
        logger.info("Publishing survey completion to %s", endpoint)
        response = await self._client.post(endpoint, json=delivery)
        response.raise_for_status()

    def _delivery_payload(self, session: SurveySession) -> JsonDict:
        created_at = session.completed_at or session.created_at
        return {
            "delivery_id": f"telegram_bot_done_{session.session_id}",
            "events": [
                {
                    "event_id": None,
                    "thread_id": None,
                    "root_thread_id": None,
                    "parent_thread_id": None,
                    "owner_agent_slug": None,
                    "sequence_no": None,
                    "event_kind": "telegram_bot_survey_finished",
                    "notification_status": None,
                    "from_agent_slug": self._source_slug,
                    "to_agent_slug": self._target_agent_slug,
                    "message_text": self._summary_text(session),
                    "interrupts_runtime": False,
                    "requires_response": True,
                    "created_at": created_at,
                    "metadata": {
                        "source": "telegram_bot",
                        "session_id": session.session_id,
                        "title": session.title,
                        "telegram_user_id": session.telegram_user_id,
                        "chat_id": session.chat_id,
                        "answers": _answers_payload(session.answers),
                    },
                }
            ],
        }

    def _summary_text(self, session: SurveySession) -> str:
        return "\n".join(
            [
                f"Telegram bot survey finished: {session.title}",
                f"User: {session.telegram_user_id}",
                f"Session: {session.session_id}",
                f"Answers: {session.answers}",
            ]
        )


def _answers_payload(answers: dict[str, list[str]]) -> JsonDict:
    return {key: list(values) for key, values in answers.items()}

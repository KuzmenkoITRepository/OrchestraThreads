from __future__ import annotations

from dataclasses import asdict, dataclass, field

from core.telegram_bot_listener.json_types import (
    JsonDict,
    cast_json_dict,
    cast_json_list,
    optional_text,
    parse_int,
)


@dataclass(frozen=True, slots=True)
class SurveyOption:
    option_id: str
    label: str

    @classmethod
    def from_dict(cls, payload: JsonDict) -> SurveyOption:
        return cls(
            option_id=str(payload["option_id"]),
            label=str(payload["label"]),
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(frozen=True, slots=True)
class SurveyQuestion:
    question_id: str
    text: str
    multi_select: bool
    options: list[SurveyOption]

    @classmethod
    def from_dict(cls, payload: JsonDict) -> SurveyQuestion:
        raw_options = payload.get("options")
        options = [
            SurveyOption.from_dict(cast_json_dict(option)) for option in cast_json_list(raw_options)
        ]
        return cls(
            question_id=str(payload["question_id"]),
            text=str(payload["text"]),
            multi_select=bool(payload.get("multi_select", False)),
            options=options,
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(frozen=True, slots=True)
class CallbackAction:
    session_id: str
    question_id: str
    option_id: str
    option_label: str
    multi_select: bool

    @classmethod
    def from_dict(cls, payload: JsonDict) -> CallbackAction:
        return cls(
            session_id=str(payload["session_id"]),
            question_id=str(payload["question_id"]),
            option_id=str(payload["option_id"]),
            option_label=str(payload["option_label"]),
            multi_select=bool(payload.get("multi_select", False)),
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(slots=True)
class SurveySession:
    session_id: str
    title: str
    telegram_user_id: int
    chat_id: int
    status: str
    created_at: str
    completed_at: str | None
    questions: list[SurveyQuestion]
    answers: dict[str, list[str]] = field(default_factory=dict)
    callback_actions: dict[str, CallbackAction] = field(default_factory=dict)
    outbound_message_ids: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: JsonDict) -> SurveySession:
        raw_questions = cast_json_list(payload.get("questions"))
        raw_actions = cast_json_dict(payload.get("callback_actions"))
        raw_answers = cast_json_dict(payload.get("answers"))
        return cls(
            session_id=str(payload["session_id"]),
            title=str(payload["title"]),
            telegram_user_id=parse_int(payload["telegram_user_id"]),
            chat_id=parse_int(payload["chat_id"]),
            status=str(payload["status"]),
            created_at=str(payload["created_at"]),
            completed_at=optional_text(payload.get("completed_at")),
            questions=[
                SurveyQuestion.from_dict(cast_json_dict(question)) for question in raw_questions
            ],
            answers={
                key: [str(item) for item in cast_json_list(value)]
                for key, value in raw_answers.items()
            },
            callback_actions={
                key: CallbackAction.from_dict(cast_json_dict(value))
                for key, value in raw_actions.items()
            },
            outbound_message_ids=[
                parse_int(value) for value in cast_json_list(payload.get("outbound_message_ids"))
            ],
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(frozen=True, slots=True)
class TranscriptEntry:
    entry_id: str
    session_id: str | None
    telegram_user_id: int
    chat_id: int
    timestamp: str
    actor: str
    kind: str
    text: str
    structured: JsonDict

    @classmethod
    def from_dict(cls, payload: JsonDict) -> TranscriptEntry:
        return cls(
            entry_id=str(payload["entry_id"]),
            session_id=optional_text(payload.get("session_id")),
            telegram_user_id=parse_int(payload["telegram_user_id"]),
            chat_id=parse_int(payload["chat_id"]),
            timestamp=str(payload["timestamp"]),
            actor=str(payload["actor"]),
            kind=str(payload["kind"]),
            text=str(payload["text"]),
            structured=cast_json_dict(payload.get("structured")),
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(slots=True)
class ListenerState:
    last_update_id: int = 0
    sessions: dict[str, SurveySession] = field(default_factory=dict)
    active_session_by_user: dict[str, str] = field(default_factory=dict)
    transcript: list[TranscriptEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: JsonDict) -> ListenerState:
        raw_sessions = cast_json_dict(payload.get("sessions"))
        raw_active = cast_json_dict(payload.get("active_session_by_user"))
        raw_transcript = cast_json_list(payload.get("transcript"))
        return cls(
            last_update_id=parse_int(payload.get("last_update_id", 0) or 0),
            sessions={
                key: SurveySession.from_dict(cast_json_dict(value))
                for key, value in raw_sessions.items()
            },
            active_session_by_user={key: str(value) for key, value in raw_active.items()},
            transcript=[
                TranscriptEntry.from_dict(cast_json_dict(entry)) for entry in raw_transcript
            ],
        )

    def to_dict(self) -> JsonDict:
        return cast_json_dict(asdict(self))


@dataclass(frozen=True, slots=True)
class SelectionResult:
    session_id: str
    question_id: str
    option_id: str
    option_label: str
    selected: bool

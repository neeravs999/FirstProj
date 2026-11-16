"""FR-05a: append answers and thumbs feedback to logs/interactions.jsonl."""
import json
import uuid
from datetime import datetime, timezone

from config import LOG_PATH


def _write(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_answer(question: str, answer: str, source_ids: list[str], channel: str) -> str:
    interaction_id = uuid.uuid4().hex
    _write({"type": "answer", "id": interaction_id, "channel": channel,
            "question": question, "answer": answer, "sources": source_ids})
    return interaction_id


def log_feedback(interaction_id: str, rating: str) -> None:
    _write({"type": "feedback", "id": interaction_id, "rating": rating})

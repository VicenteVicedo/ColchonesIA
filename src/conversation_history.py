import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class Message:
    role: str  # 'user', 'assistant', or 'system'
    content: str


class ConversationHistory:
    """Simple conversation history manager.

    - Keeps messages in memory in order of arrival.
    - Can persist to a JSON file and load from it.
    - Provides helpers to append messages and to render the last N messages
      formatted for inclusion in prompts.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self.messages: List[Message] = []
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path and self.persist_path.exists():
            try:
                self._load()
            except Exception:
                # If loading fails, start with an empty history
                self.messages = []

    def add_user(self, text: str):
        self.messages.append(Message(role="user", content=text))
        self._maybe_persist()

    def add_assistant(self, text: str):
        self.messages.append(Message(role="assistant", content=text))
        self._maybe_persist()

    def add_system(self, text: str):
        self.messages.append(Message(role="system", content=text))
        self._maybe_persist()

    def last_messages(self, n: int = 10) -> List[Message]:
        return self.messages[-n:]

    def render_for_prompt(self, n: int = 10) -> str:
        """Return a textual rendering of the last n messages suitable for
        inserting into a prompt. Each message is prefixed with the role.
        """
        parts: List[str] = []
        for msg in self.last_messages(n):
            parts.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(parts)

    def _maybe_persist(self):
        if self.persist_path:
            try:
                self._save()
            except Exception:
                # Persist failures shouldn't crash the app; ignore.
                pass

    def _save(self):
        data = [asdict(m) for m in self.messages]
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        with open(self.persist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.messages = [Message(**m) for m in data]

    def clear(self):
        self.messages = []
        if self.persist_path and self.persist_path.exists():
            try:
                self.persist_path.unlink()
            except Exception:
                pass



class ConversationHistoryManager:
    """Manage per-user conversation histories.

    Histories are stored on disk under a base directory (default: chroma_db/).
    Each user gets a JSON file named <user_id>.json. The manager caches
    ConversationHistory instances in memory for the process lifetime.
    """

    def __init__(self, base_dir: str = "chroma_db"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, ConversationHistory] = {}

    def _path_for(self, user_id: str) -> Path:
        # sanitize minimal: allow alphanum, dash and underscore; otherwise replace with '_'
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in user_id)
        return self.base_dir / f"{safe}.json"

    def get(self, user_id: str) -> ConversationHistory:
        if user_id in self._cache:
            return self._cache[user_id]
        p = str(self._path_for(user_id))
        ch = ConversationHistory(persist_path=p)
        self._cache[user_id] = ch
        return ch

    def create(self, user_id: str) -> ConversationHistory:
        # (re)create a fresh history for the user
        ch = ConversationHistory(persist_path=str(self._path_for(user_id)))
        ch.clear()
        self._cache[user_id] = ch
        return ch

    def delete(self, user_id: str) -> None:
        if user_id in self._cache:
            del self._cache[user_id]
        p = self._path_for(user_id)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    def list_user_ids(self):
        for f in self.base_dir.glob("*.json"):
            yield f.stem

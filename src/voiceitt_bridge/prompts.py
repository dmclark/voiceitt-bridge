"""Prompt inventory loading for the Voiceitt Bridge API."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
from typing import TypedDict

from pydantic import BaseModel


class PromptSummary(TypedDict):
    """Safe prompt metadata returned by the API."""

    id: str
    name: str
    path: str
    content_hash: str


class PromptDocument(PromptSummary):
    """Loaded prompt content for server-side provider calls."""

    system_text: str


class ActivePromptState(TypedDict):
    """Backend-owned active prompt selection shared by API clients."""

    active_prompt_id: str
    updated_at: str
    updated_by: str


class PromptStateUpdate(BaseModel):
    """Request body for changing the active prompt."""

    active_prompt_id: str
    updated_by: str


class PromptWrite(BaseModel):
    """Request body for creating or updating a local prompt."""

    id: str | None = None
    system_text: str


class PromptValidationRequest(BaseModel):
    """Request body for validating prompt authoring input."""

    id: str | None = None
    system_text: str


class PromptValidationResult(BaseModel):
    """Validation result returned before or during prompt writes."""

    ok: bool
    errors: list[str]


class PromptNotFoundError(ValueError):
    """Raised when a prompt cannot be loaded deterministically."""


class PromptValidationError(ValueError):
    """Raised when prompt authoring input is unsafe or incomplete."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class PromptAlreadyExistsError(ValueError):
    """Raised when creating a prompt that already exists."""


class PromptSystemManagedError(ValueError):
    """Raised when a write would remove a packaged system prompt."""


PROMPT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class PromptStore:
    """File-backed prompt authoring boundary for the local API."""

    def __init__(self, prompts_dir: Path | str) -> None:
        self.prompts_dir = Path(prompts_dir)
        self.user_prompts_dir = self.prompts_dir / "user"
        self.active_prompt_state = default_prompt_state(self.list_prompts())

    def list_prompts(self) -> list[PromptSummary]:
        """Return safe metadata for active system prompts plus user overrides."""
        prompt_paths: dict[str, Path] = {}

        if self.prompts_dir.is_dir():
            for prompt_path in sorted(self.prompts_dir.glob("*.md")):
                if prompt_path.is_file():
                    prompt_paths[prompt_path.stem] = prompt_path

        if self.user_prompts_dir.is_dir():
            for prompt_path in sorted(self.user_prompts_dir.glob("*.md")):
                if prompt_path.is_file():
                    prompt_paths[prompt_path.stem] = prompt_path

        prompts: list[PromptSummary] = []
        for prompt_id, prompt_path in sorted(prompt_paths.items()):
            content = prompt_path.read_bytes()
            prompts.append(
                {
                    "id": prompt_id,
                    "name": prompt_id,
                    "path": self._display_path(prompt_path),
                    "content_hash": sha256(content).hexdigest(),
                }
            )

        return prompts

    def load_prompt(
        self,
        prompt_id: str,
        *,
        content_hash: str | None = None,
    ) -> PromptDocument:
        """Load one UTF-8 prompt by stable ID and optional content hash."""
        for prompt in self.list_prompts():
            if prompt["id"] != prompt_id:
                continue
            if content_hash is not None and prompt["content_hash"] != content_hash:
                raise PromptNotFoundError(f"prompt hash mismatch: {prompt_id}")

            prompt_path = self._effective_prompt_path(prompt_id)
            return {
                **prompt,
                "system_text": prompt_path.read_text(encoding="utf-8"),
            }

        raise PromptNotFoundError(f"unknown prompt id: {prompt_id}")

    def validate_prompt(
        self,
        *,
        prompt_id: str | None,
        system_text: str,
    ) -> PromptValidationResult:
        """Validate authoring input without writing to disk."""
        errors: list[str] = []
        if prompt_id is not None and not PROMPT_ID_PATTERN.fullmatch(prompt_id):
            errors.append(
                "prompt id must be lowercase letters, numbers, or hyphens"
            )
        if not system_text.strip():
            errors.append("system_text must not be empty")
        return PromptValidationResult(ok=not errors, errors=errors)

    def create_prompt(self, *, prompt_id: str, system_text: str) -> PromptDocument:
        """Create a new local user prompt file."""
        self._validate_or_raise(prompt_id=prompt_id, system_text=system_text)
        prompt_path = self._user_prompt_path(prompt_id)
        if self._system_prompt_path(prompt_id).exists() or prompt_path.exists():
            raise PromptAlreadyExistsError(f"prompt already exists: {prompt_id}")

        self.user_prompts_dir.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(system_text, encoding="utf-8")
        return self.load_prompt(prompt_id)

    def update_prompt(self, *, prompt_id: str, system_text: str) -> PromptDocument:
        """Update a user prompt or create a user override for a system prompt."""
        self._validate_or_raise(prompt_id=prompt_id, system_text=system_text)
        if not self._system_prompt_path(prompt_id).exists() and not self._user_prompt_path(
            prompt_id
        ).exists():
            raise PromptNotFoundError(f"unknown prompt id: {prompt_id}")

        self.user_prompts_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = self._user_prompt_path(prompt_id)
        prompt_path.write_text(system_text, encoding="utf-8")
        return self.load_prompt(prompt_id)

    def archive_prompt(self, prompt_id: str) -> ActivePromptState:
        """Disable a user prompt or remove a user override."""
        prompt_path = self._user_prompt_path(prompt_id)
        if not prompt_path.exists():
            if self._system_prompt_path(prompt_id).exists():
                raise PromptSystemManagedError(
                    f"system-managed prompt cannot be archived: {prompt_id}"
                )
            raise PromptNotFoundError(f"unknown prompt id: {prompt_id}")

        archive_dir = self.user_prompts_dir / ".archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archived_path = archive_dir / f"{prompt_id}.{utc_now_iso()}.md"
        prompt_path.rename(archived_path)

        if self.active_prompt_state["active_prompt_id"] == prompt_id:
            self.active_prompt_state.update(
                {
                    **default_prompt_state(self.list_prompts()),
                    "updated_by": "prompt-archive",
                }
            )
        return self.active_prompt_state

    def get_active_prompt_state(self) -> ActivePromptState:
        """Return backend-owned active prompt selection."""
        return self.active_prompt_state

    def set_active_prompt_state(self, update: PromptStateUpdate) -> ActivePromptState:
        """Set the active prompt after checking it exists."""
        prompt_ids = {prompt["id"] for prompt in self.list_prompts()}
        if update.active_prompt_id not in prompt_ids:
            raise PromptNotFoundError("unknown prompt id")

        self.active_prompt_state.update(
            {
                "active_prompt_id": update.active_prompt_id,
                "updated_at": utc_now_iso(),
                "updated_by": update.updated_by,
            }
        )
        return self.active_prompt_state

    def _system_prompt_path(self, prompt_id: str) -> Path:
        return self.prompts_dir / f"{prompt_id}.md"

    def _user_prompt_path(self, prompt_id: str) -> Path:
        return self.user_prompts_dir / f"{prompt_id}.md"

    def _effective_prompt_path(self, prompt_id: str) -> Path:
        user_prompt_path = self._user_prompt_path(prompt_id)
        if user_prompt_path.exists():
            return user_prompt_path
        return self._system_prompt_path(prompt_id)

    def _display_path(self, prompt_path: Path) -> str:
        try:
            return str(prompt_path.relative_to(self.prompts_dir.parent))
        except ValueError:
            return str(prompt_path)

    def _validate_or_raise(self, *, prompt_id: str, system_text: str) -> None:
        result = self.validate_prompt(prompt_id=prompt_id, system_text=system_text)
        if not result.ok:
            raise PromptValidationError(result.errors)


def load_prompt_inventory(prompts_dir: Path) -> list[PromptSummary]:
    """Return safe metadata for Markdown prompts in `prompts_dir`."""
    return PromptStore(prompts_dir).list_prompts()


def load_prompt_by_id(
    prompts_dir: Path,
    prompt_id: str,
    *,
    content_hash: str | None = None,
) -> PromptDocument:
    """Load one UTF-8 prompt by stable ID and optional content hash."""
    return PromptStore(prompts_dir).load_prompt(prompt_id, content_hash=content_hash)


def frame_transcript(raw_text: str) -> str:
    """Frame dictated text so the LLM treats it as transcript input."""
    return f"<TRANSCRIPT>\n{raw_text}\n</TRANSCRIPT>"


def default_prompt_state(prompts: list[PromptSummary]) -> ActivePromptState:
    """Return the initial active prompt state for a prompt inventory."""
    active_prompt_id = prompts[0]["id"] if prompts else ""
    return {
        "active_prompt_id": active_prompt_id,
        "updated_at": utc_now_iso(),
        "updated_by": "server-default",
    }


def utc_now_iso() -> str:
    """Return an API-friendly UTC timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

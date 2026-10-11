"""Hire the cell by talking to it. A voice agent takes the order and places the job; the house account pays."""
from __future__ import annotations

import json
import secrets
from typing import Any

from .config import settings
from .events import Publisher

AGENT_NAME = "Hired Hands front desk"
FIRST_MESSAGE = "Hired Hands. What should the arms move?"
PROMPT = """You are the front desk of Hired Hands, a workcell of three robot arms that moves small coloured objects on a
table for a fee paid in XRP. Keep every reply to one or two short sentences.

Find out what the caller wants moved and where. Objects are described by colour: red, orange, yellow, green, cyan,
blue, purple or pink. A destination is another coloured object, or a place on the table: left, right, front, back
or centre. Once you have both, call place_job with one instruction such as "put the red block in the blue cup" or
"move the green block to the left". Then tell the caller the price and that the dashboard shows the job live. If the
tool reports an error, say what went wrong in plain words and offer to try again."""


class Voice:
    def __init__(self, publisher: Publisher, api_url: str):
        self.publisher = publisher
        self.api_url = api_url.rstrip("/")
        self.path = settings().state_dir / "voice.json"
        self.state: dict[str, Any] = json.loads(self.path.read_text()) if self.path.exists() else {}
        if "secret" not in self.state:
            self.state["secret"] = secrets.token_urlsafe(24)
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2) + "\n")

    @property
    def agent_id(self) -> str | None:
        return self.state.get("agent_id")

    def authorized(self, header_value: str | None) -> bool:
        return bool(header_value) and secrets.compare_digest(header_value, self.state["secret"])

    def ensure(self) -> str:
        """Create the agent and its tool the first time; afterwards point the tool at the current address."""
        from elevenlabs import ElevenLabs
        from elevenlabs.types import (
            AgentConfig,
            ConversationalConfig,
            LiteralJsonSchemaProperty,
            ObjectJsonSchemaPropertyInput,
            ToolRequestModel,
            ToolRequestModelToolConfig_Webhook,
            WebhookToolApiSchemaConfigInput,
        )

        key = settings().elevenlabs_api_key
        if not key:
            raise RuntimeError("no ELEVENLABS_API_KEY configured")
        client = ElevenLabs(api_key=key)

        tool = ToolRequestModel(tool_config=ToolRequestModelToolConfig_Webhook(
            name="place_job",
            description="Place a paid job with the robot arms. Call it once the caller has said what to move and where.",
            response_timeout_secs=30,
            api_schema=WebhookToolApiSchemaConfigInput(
                url=f"{self.api_url}/voice/jobs",
                method="POST",
                request_headers={"X-Voice-Key": self.state["secret"]},
                request_body_schema=ObjectJsonSchemaPropertyInput(
                    type="object",
                    required=["instruction"],
                    properties={
                        "instruction": LiteralJsonSchemaProperty(
                            type="string",
                            description='The job in one sentence, e.g. "put the red block in the blue cup".'),
                        "caller": LiteralJsonSchemaProperty(type="string", description="The caller's name, if given."),
                    },
                ),
            ),
        ))
        if self.state.get("tool_id"):
            client.conversational_ai.tools.update(self.state["tool_id"], request=tool)
        else:
            self.state["tool_id"] = client.conversational_ai.tools.create(request=tool).id
            self._save()

        config = ConversationalConfig(agent=AgentConfig(
            first_message=FIRST_MESSAGE,
            language="en",
            prompt={"prompt": PROMPT, "tool_ids": [self.state["tool_id"]], "temperature": 0.3},
        ))
        if self.state.get("agent_id"):
            client.conversational_ai.agents.update(self.state["agent_id"], conversation_config=config)
        else:
            self.state["agent_id"] = client.conversational_ai.agents.create(name=AGENT_NAME, conversation_config=config).agent_id
            self._save()
        self.publisher.cell(voice_agent_id=self.state["agent_id"])
        return self.state["agent_id"]

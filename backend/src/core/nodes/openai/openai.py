import openai
import os
from typing import Optional

import tokentrim as tt

from src.core.nodes.base_node import BaseNode, NodeConfig
from src.core.nodes.openai.openai_model import *
from src.utils.router_generator import generate_node_end_points


openai_node_config = {
    "name": "openai",
    "description": "A node that interacts with OpenAI's GPT-3 model.",
    "functions": {
        "chat": "Chat with OpenAI's LLM model.",
        "chat_with_prompt_template": "Chat with OpenAI's LLM model with a specific prompt template.",
        "chat_with_message": "Chat with OpenAI's LLM model with a specific message dict.",
    },
}


@generate_node_end_points
class OpenAINode(BaseNode):
    config: NodeConfig = NodeConfig(**openai_node_config)

    history: list[dict[str, any]]
    functions: list[dict[str, any]]

    cur_role: Optional[str]
    cur_content: Optional[str]

    def __init__(self):
        super().__init__()

        self.history = []
        self.functions = []

        self.cur_role = None
        self.cur_content = None

        openai.api_key = os.getenv("OPENAI_CHAT_API_KEY")
        openai.api_base = os.getenv("OPENAI_CHAT_API_BASE")

    def complete(self, input: CompleteInput):
        """
        Complete with only current history. No extra messages.
        """
        return self._make_completion([], input)

    # TODO: generalize these chat functions
    def chat(self, input: ChatInput):
        """
        Chat with OpenAI's model with simple text.
        """
        return self._make_completion(
            [
                Message(
                    role="user",
                    content=input.message_text,
                )
            ],
            input,
        )

    def chat_with_prompt_template(self, input: ChatWithPromptTemplateInput):
        """
        Chat with OpenAI's model with a specific prompt template.
        """
        return self._make_completion(
            [
                Message(
                    role="user",
                    content=input.prompt_template.format(**input.params),
                )
            ],
            input,
        )

    def chat_with_message(self, input: ChatWithMessageInput):
        """
        Chat with OpenAI's model with a specific message dict.
        """
        return self._make_completion([input.message], input)

    def chat_with_messages(self, input: ChatWithMessagesInput):
        """
        Chat with OpenAI's model with a specific message dict.
        """
        return self._make_completion(input.messages, input)

    def _make_completion(
        self, messages: list[Message], input: ChatConfig
    ) -> OpenAIResp | OpenAIStreamingResp:
        """
        Make a completion with the given messages.
        """

        kwargs = {
            "model": input.model,
        }

        cur_messages = []

        # if history is empty, add a default system message
        if len(self.history) == 0:
            cur_messages.append(
                Message(
                    role="system",
                    content="You are a helpful AI assistant. You should answer the user's questions and help them with their tasks.",
                ).dict(exclude_none=True)
            )
        else:
            cur_messages += self.history

        # append history if needed
        if input.append_history:
            for message in messages:
                self.add_single_message(message)

        # add all input messages to argument `messages`
        for message in messages:
            cur_messages.append(message.dict(exclude_none=True))

        kwargs["messages"] = tt.trim(cur_messages, input.model)

        # add function definitions if exists
        if len(self.functions) > 0:
            kwargs["functions"] = self.functions
            kwargs["function_call"] = "auto"

        # set streaming if needed
        if input.use_streaming:
            kwargs["stream"] = True

        # TODO: add exception handling
        try:
            response = openai.ChatCompletion.create(**kwargs)
        except Exception as e:
            return OpenAIResp(
                message=Message(
                    role="system",
                    content=f"Error occurred: {e}",
                ),
                finish_reason="error",
            )

        if input.use_streaming:
            resp = OpenAIStreamingResp(**response.choices[0])
            if input.append_history:
                self.history.append(resp.delta.dict(exclude_none=True))
            return resp

        resp = OpenAIResp(**response.choices[0])
        if input.append_history:
            self.history.append(resp.message.dict(exclude_none=True))
        return resp

    def add_function(self, func_def: FunctionDefinition):
        self.functions.append(
            func_def.dict()
        )  # redefined dict() doesn't have exclude_none arg

    def add_single_message(self, msg: Message):
        if self.cur_role is not None and self.cur_content is not None:
            self.history.append(
                Message(
                    role=self.cur_role,
                    content=self.cur_content,
                ).dict(exclude_none=True)
            )
            self.cur_role = None
            self.cur_content = None

        self.history.append(msg.dict(exclude_none=True))

    def add_system_message(self, content: str):
        self.add_single_message(
            Message(
                role="system",
                content=content,
            )
        )


    def add_role(self, role: str):
        if self.cur_role is not None and self.cur_content is not None:
            self.add_single_message(
                Message(
                    role=self.cur_role,
                    content=self.cur_content,
                )
            )

        self.cur_role = role

    def add_content(self, content: str):
        if self.cur_content is not None:
            self.cur_content += content
        else:
            self.cur_content = content

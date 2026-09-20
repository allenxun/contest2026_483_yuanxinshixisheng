import time
from typing import List, Any, Optional

from openai import OpenAI
from langchain_core.language_models import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import GenerationChunk

from rag.common.utils import logger


_CLIENTS = {}


class OpenaiCompatibleLLM(LLM):

    model_name: str
    api_key: str
    base_url: str
    enable_thinking: bool = False

    def _client(self) -> OpenAI:
        key = (self.api_key, self.base_url)
        client = _CLIENTS.get(key)
        if client is None:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            _CLIENTS[key] = client
        return client

    def _extra_body(self, override=None) -> dict:
        enabled = self.enable_thinking if override is None else bool(override)
        return {"thinking": {"type": "enabled" if enabled else "disabled"}}

    def _stream(self,
                prompt: str,
                stop: Optional[List[str]] = None,
                run_manager: Optional[CallbackManagerForLLMRun] = None,
                **kwargs: Any, ):
        extra_body = self._extra_body(kwargs.get("enable_thinking"))
        started = time.perf_counter()
        first_token_at = None
        reasoning_len = 0
        try:
            response = self._client().chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                stream=True,
                extra_body=extra_body,
            )

            for res in response:
                # OpenAI-compatible providers may emit usage/control chunks with
                # an empty choices list, and finish chunks without text content.
                choices = getattr(res, "choices", None)
                if not choices:
                    continue

                choice = choices[0]
                delta = getattr(choice, "delta", None)
                reasoning = getattr(delta, "reasoning_content", None) if delta else None
                if reasoning:
                    reasoning_len += len(reasoning)
                token = getattr(delta, "content", None) if delta else None
                if token:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    yield GenerationChunk(text=token)

                if getattr(choice, "finish_reason", None):
                    break
        except Exception as e:
            msg = "inference request error"
            logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
            raise
        finally:
            elapsed = time.perf_counter() - started
            ttft = (first_token_at - started) if first_token_at else elapsed
            logger.info(
                "llm stream model=%s thinking=%s ttft=%.2fs total=%.2fs reasoning_chars=%s",
                self.model_name,
                extra_body["thinking"]["type"],
                ttft,
                elapsed,
                reasoning_len,
            )

    def _call(self,
              prompt: str,
              stop: Optional[List[str]] = None,
              run_manager: Optional[CallbackManagerForLLMRun] = None,
              **kwargs: Any, ):
        extra_body = self._extra_body(kwargs.get("enable_thinking"))
        started = time.perf_counter()
        try:
            response = self._client().chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                extra_body=extra_body,
            )
        except Exception as e:
            msg = "inference request error"
            logger.error(f'{e.__class__.__name__}: {msg}', exc_info=e)
            raise

        message = response.choices[0].message
        reasoning = getattr(message, "reasoning_content", None) or ""
        logger.info(
            "llm call model=%s thinking=%s total=%.2fs reasoning_chars=%s completion=%s",
            self.model_name,
            extra_body["thinking"]["type"],
            time.perf_counter() - started,
            len(reasoning),
            getattr(response.usage, "completion_tokens", None),
        )
        return message.content

    def _llm_type(self) -> str:
        """Return type of chat model."""
        return self.model_name

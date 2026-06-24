from __future__ import annotations
import logging
import os
from collections.abc import Iterator
from typing import Protocol
from pydantic import BaseModel

logger = logging.getLogger("clare.providers")

class _Msg(Protocol):
    role: str
    text: str

SchemaT = type[BaseModel]

class ProviderError(Exception):
    """Falha recuperável de um provedor — sinaliza ao router para tentar o próximo."""

class LLMProvider:
    name: str = "base"

    def stream_chat(
        self,
        messages: list[_Msg],
        system_instruction: str,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> Iterator[str]:
        raise NotImplementedError

    def generate_json(
        self,
        messages: list[_Msg],
        system_instruction: str,
        schema: SchemaT,
        temperature: float,
    ) -> BaseModel:
        raise NotImplementedError

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        from google import genai

        self._genai = genai
        self.model = model
        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _to_contents(messages: list[_Msg]) -> list[dict]:
        return [{"role": m.role, "parts": [{"text": m.text}]} for m in messages]

    def stream_chat(self, messages, system_instruction, temperature, max_output_tokens):
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=self._to_contents(messages),
            config=config,
        )
        truncated = False
        for chunk in stream:
            if chunk.text:
                yield chunk.text
            cand = (chunk.candidates or [None])[0]
            if cand and cand.finish_reason and str(cand.finish_reason).endswith("MAX_TOKENS"):
                truncated = True
        if truncated:
            yield "\n\n_(resposta interrompida por limite de tamanho)_"

    def generate_json(self, messages, system_instruction, schema, temperature):
        from google.genai import types

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=self._to_contents(messages),
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as exc:
            raise ProviderError(f"gemini: erro na chamada: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        try:
            return schema.model_validate_json(response.text)
        except Exception as exc:
            raise ProviderError(f"gemini: resposta fora do formato: {exc}") from exc

def _strictify(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for value in node:
            _strictify(value)
    return node

class _OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        client,
        chat_model: str,
        json_model: str,
        max_tokens_param: str = "max_tokens",
        extra_headers: dict | None = None,
    ):
        self.name = name
        self.client = client
        self.chat_model = chat_model
        self.json_model = json_model
        self._max_tokens_param = max_tokens_param
        self._extra_headers = extra_headers or None

    @staticmethod
    def _to_messages(messages: list[_Msg], system_instruction: str) -> list[dict]:
        out = [{"role": "system", "content": system_instruction}]
        for m in messages:
            role = "assistant" if m.role == "model" else "user"
            out.append({"role": role, "content": m.text})
        return out

    def _create(self, **kwargs):
        if self._extra_headers:
            kwargs["extra_headers"] = self._extra_headers
        return self.client.chat.completions.create(**kwargs)

    def stream_chat(self, messages, system_instruction, temperature, max_output_tokens):
        kwargs = {
            "model": self.chat_model,
            "messages": self._to_messages(messages, system_instruction),
            "temperature": temperature,
            "stream": True,
        }
        if max_output_tokens:
            kwargs[self._max_tokens_param] = max_output_tokens
        stream = self._create(**kwargs)
        truncated = False
        for chunk in stream:
            choice = (chunk.choices or [None])[0]
            if not choice:
                continue
            if choice.delta and choice.delta.content:
                yield choice.delta.content
            if choice.finish_reason == "length":
                truncated = True
        if truncated:
            yield "\n\n_(resposta interrompida por limite de tamanho)_"

    def generate_json(self, messages, system_instruction, schema, temperature):
        json_schema = _strictify(schema.model_json_schema())
        try:
            response = self._create(
                model=self.json_model,
                messages=self._to_messages(messages, system_instruction),
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__.lstrip("_") or "output",
                        "strict": True,
                        "schema": json_schema,
                    },
                },
            )
        except Exception as exc:
            raise ProviderError(f"{self.name}: erro na chamada: {exc}") from exc

        content = response.choices[0].message.content
        try:
            return schema.model_validate_json(content)
        except Exception as exc:
            raise ProviderError(f"{self.name}: resposta fora do formato: {exc}") from exc

class GroqProvider(_OpenAICompatProvider):
    def __init__(self, api_key: str, chat_model: str, json_model: str):
        from groq import Groq

        super().__init__(
            name="groq",
            client=Groq(api_key=api_key),
            chat_model=chat_model,
            json_model=json_model,
            max_tokens_param="max_completion_tokens",
        )

class MistralProvider(_OpenAICompatProvider):

    def __init__(self, api_key: str, chat_model: str, json_model: str):
        from openai import OpenAI

        super().__init__(
            name="mistral",
            client=OpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1"),
            chat_model=chat_model,
            json_model=json_model,
            max_tokens_param="max_tokens",
        )

class ProviderRouter:
    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise RuntimeError(
                "Nenhum provedor de IA configurado. Defina GEMINI_API_KEY e/ou "
                "GROQ_API_KEY no .env."
            )
        self.providers = providers

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def generate_json(self, messages, system_instruction, schema, temperature) -> BaseModel:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.generate_json(messages, system_instruction, schema, temperature)
            except Exception as exc:
                logger.warning("Provedor '%s' falhou em generate_json: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError("Todos os provedores falharam — " + " | ".join(errors))

    def stream_chat(
        self, messages, system_instruction, temperature, max_output_tokens
    ) -> Iterator[str]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                stream = provider.stream_chat(
                    messages, system_instruction, temperature, max_output_tokens
                )
                first = next(stream)
            except StopIteration:
                return 
            except Exception as exc:
                logger.warning("Provedor '%s' falhou ao abrir o stream: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue

            yield first
            try:
                for chunk in stream:
                    yield chunk
            except Exception as exc:
                logger.warning("Provedor '%s' falhou no meio do stream: %s", provider.name, exc)
                if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                    yield "\n\n⚠️ Limite de uso da IA atingido. Tente novamente em alguns instantes."
                else:
                    yield "\n\n⚠️ Tive um problema para gerar a resposta. Pode tentar de novo?"
            return

        logger.error("Todos os provedores falharam no stream: %s", " | ".join(errors))
        yield "\n\n⚠️ Nenhuma IA está disponível no momento. Tente novamente em alguns instantes."

def build_router_from_env() -> ProviderRouter:
    order = [
        p.strip().lower()
        for p in os.getenv("LLM_PROVIDERS", "mistral,gemini,groq").split(",")
        if p.strip()
    ]

    mistral_key = os.getenv("MISTRAL_API_KEY") or os.getenv("MISTRALAI_API_KEY")
    mistral_chat_model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    mistral_json_model = os.getenv("MISTRAL_JSON_MODEL", "mistral-small-latest")

    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    groq_chat_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_json_model = os.getenv("GROQ_JSON_MODEL", "openai/gpt-oss-120b")

    available: dict[str, LLMProvider] = {}
    if mistral_key:
        available["mistral"] = MistralProvider(mistral_key, mistral_chat_model, mistral_json_model)
    if gemini_key:
        available["gemini"] = GeminiProvider(gemini_key, gemini_model)
    if groq_key:
        available["groq"] = GroqProvider(groq_key, groq_chat_model, groq_json_model)

    providers = [available[name] for name in order if name in available]
    providers += [p for name, p in available.items() if name not in order]

    router = ProviderRouter(providers)
    logger.info("Provedores de IA ativos (em ordem de fallback): %s", router.names)
    return router
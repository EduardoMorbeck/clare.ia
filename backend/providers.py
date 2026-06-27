from __future__ import annotations
import logging
import os
from typing import Protocol

logger = logging.getLogger("clare.providers")

class _Msg(Protocol):
    role: str
    text: str

class ProviderError(Exception):
    """Falha recuperável de um provedor — sinaliza ao router para tentar o próximo."""

class LLMProvider:
    name: str = "base"

    def generate_json(
        self,
        messages: list[_Msg],
        system_instruction: str,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> str:
        """Gera uma resposta completa (não-stream) como texto JSON cru.

        O texto retornado AINDA não é validado aqui — quem chama (o handler) é
        responsável por fazer o parse/validação do JSON. Levantar qualquer
        exceção sinaliza ao router para tentar o próximo provedor.
        """
        raise NotImplementedError

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, thinking_budget: int = 1024):
        from google import genai

        self._genai = genai
        self.model = model
        self.thinking_budget = thinking_budget
        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _to_contents(messages: list[_Msg]) -> list[dict]:
        return [{"role": m.role, "parts": [{"text": m.text}]} for m in messages]

    def generate_json(self, messages, system_instruction, temperature, max_output_tokens):
        from google.genai import types

        effective_max = max_output_tokens
        if self.thinking_budget > 0 and effective_max:
            effective_max = effective_max + self.thinking_budget

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            max_output_tokens=effective_max,

            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=self.thinking_budget),
        )
        resp = self.client.models.generate_content(
            model=self.model,
            contents=self._to_contents(messages),
            config=config,
        )
        return resp.text or ""

class _OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        client,
        chat_model: str,
        max_tokens_param: str = "max_tokens",
        extra_headers: dict | None = None,
    ):
        self.name = name
        self.client = client
        self.chat_model = chat_model
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

    def generate_json(self, messages, system_instruction, temperature, max_output_tokens):
        kwargs = {
            "model": self.chat_model,
            "messages": self._to_messages(messages, system_instruction),
            "temperature": temperature,
            # Modo JSON do protocolo OpenAI (suportado por Groq/Mistral/Cerebras).
            # Exige que a palavra "json" apareça no prompt — garantido pela persona.
            "response_format": {"type": "json_object"},
        }
        if max_output_tokens:
            kwargs[self._max_tokens_param] = max_output_tokens
        resp = self._create(**kwargs)
        return resp.choices[0].message.content or ""

class GroqProvider(_OpenAICompatProvider):
    def __init__(self, api_key: str, chat_model: str):
        from groq import Groq

        super().__init__(
            name="groq",
            client=Groq(api_key=api_key),
            chat_model=chat_model,
            max_tokens_param="max_completion_tokens",
        )

class MistralProvider(_OpenAICompatProvider):

    def __init__(self, api_key: str, chat_model: str):
        from openai import OpenAI

        super().__init__(
            name="mistral",
            client=OpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1"),
            chat_model=chat_model,
            max_tokens_param="max_tokens",
        )

class CerebrasProvider(_OpenAICompatProvider):

    def __init__(self, api_key: str, chat_model: str):
        from openai import OpenAI

        super().__init__(
            name="cerebras",
            client=OpenAI(api_key=api_key, base_url="https://api.cerebras.ai/v1"),
            chat_model=chat_model,
            max_tokens_param="max_completion_tokens",
        )

class ProviderRouter:
    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise RuntimeError(
                "Nenhum provedor de IA configurado. Defina MISTRAL_API_KEY, "
                "GEMINI_API_KEY e/ou GROQ_API_KEY no .env."
            )
        self.providers = providers

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def generate_json(
        self, messages, system_instruction, temperature, max_output_tokens
    ) -> tuple[str | None, str | None]:
        """Tenta cada provedor em ordem até um responder com sucesso.

        Retorna (nome_do_provedor, texto_json_cru). Sem streaming, o fallback é
        um simples try/except: qualquer falha de um provedor (chave inválida,
        429, indisponibilidade) faz o próximo assumir. Se todos falharem,
        retorna (None, None) e o chamador decide a mensagem amigável.
        """
        errors: list[str] = []
        for provider in self.providers:
            try:
                raw = provider.generate_json(
                    messages, system_instruction, temperature, max_output_tokens
                )
            except Exception as exc:
                logger.warning("Provedor '%s' falhou: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue
            return provider.name, raw

        logger.error("Todos os provedores falharam: %s", " | ".join(errors))
        return None, None

def build_router_from_env() -> ProviderRouter:
    order = [
        p.strip().lower()
        for p in os.getenv("LLM_PROVIDERS", "gemini,cerebras,groq,mistral").split(",")
        if p.strip()
    ]

    mistral_key = os.getenv("MISTRAL_API_KEY") or os.getenv("MISTRALAI_API_KEY")
    mistral_chat_model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    gemini_thinking = int(os.getenv("GEMINI_THINKING_BUDGET", "1024"))

    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    groq_chat_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    cerebras_key = os.getenv("CEREBRAS_API_KEY")
    cerebras_chat_model = os.getenv("CEREBRAS_MODEL", "zai-glm-4.7")

    available: dict[str, LLMProvider] = {}
    if mistral_key:
        available["mistral"] = MistralProvider(mistral_key, mistral_chat_model)
    if gemini_key:
        available["gemini"] = GeminiProvider(gemini_key, gemini_model, gemini_thinking)
    if groq_key:
        available["groq"] = GroqProvider(groq_key, groq_chat_model)
    if cerebras_key:
        available["cerebras"] = CerebrasProvider(cerebras_key, cerebras_chat_model)

    providers = [available[name] for name in order if name in available]
    providers += [p for name, p in available.items() if name not in order]

    router = ProviderRouter(providers)
    logger.info("Provedores de IA ativos (em ordem de fallback): %s", router.names)
    return router

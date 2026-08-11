from langchain_openai import ChatOpenAI

from core.config import get_settings


def get_llm() -> ChatOpenAI:
    settings = get_settings().app
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key.get_secret_value(),
        temperature=settings.llm_temperature,
    )

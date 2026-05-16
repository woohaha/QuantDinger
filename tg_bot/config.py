"""Bot settings loaded from environment variables."""
from pathlib import Path
from typing import Annotated, Set

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_int_set(value: str) -> Set[int]:
    if not value:
        return set()
    out: Set[int] = set()
    for chunk in value.replace(" ", "").split(","):
        if chunk:
            out.add(int(chunk))
    return out


class Settings(BaseSettings):
    """Bot runtime configuration."""
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    # --- Telegram ---
    tg_bot_token: str = Field(..., alias="TG_BOT_TOKEN")
    whitelist_group_ids: Annotated[Set[int], NoDecode] = Field(..., alias="WHITELIST_GROUP_IDS")
    whitelist_user_ids: Annotated[Set[int], NoDecode] = Field(..., alias="WHITELIST_USER_IDS")

    # --- Backend ---
    quantdinger_api_url: HttpUrl = Field(..., alias="QUANTDINGER_API_URL")
    quantdinger_username: str = Field(..., alias="QUANTDINGER_USERNAME")
    quantdinger_password: str = Field(..., alias="QUANTDINGER_PASSWORD")

    # --- Telegraph ---
    telegraph_access_token: str | None = Field(default=None, alias="TELEGRAPH_ACCESS_TOKEN")
    telegraph_author_name: str = Field(default="QuantDinger Bot", alias="TELEGRAPH_AUTHOR_NAME")
    telegraph_author_url: str = Field(default="", alias="TELEGRAPH_AUTHOR_URL")
    telegraph_reuse_page: bool = Field(default=False, alias="TELEGRAPH_REUSE_PAGE")

    # --- Storage ---
    db_path: Path = Field(default=Path("/data/bot.db"), alias="DB_PATH")

    @field_validator("whitelist_group_ids", "whitelist_user_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return _parse_int_set(v)
        return v

    @field_validator("telegraph_access_token", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "":
            return None
        return v

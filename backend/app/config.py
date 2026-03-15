from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    backend_port: int = 8000

    frontend_base_url: str = "http://localhost:8000"
    backend_base_url: str = "http://localhost:8000"
    cors_allowed_origins: str = "http://localhost:8000"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "visutrade"
    db_user: str = "visutrade"
    db_password: str = "visutrade"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    starting_balance_usdt: float = 15.0
    normal_buy_usdt: float = 3.0
    panic_buy_usdt: float = 1.5
    trade_cooldown_seconds: int = 300

    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()

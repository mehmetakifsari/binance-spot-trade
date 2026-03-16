from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    backend_port: int = 8000

    frontend_base_url: str = ""
    backend_base_url: str = ""
    cors_allowed_origins: str = ""

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

    signal_collector_enabled: bool = False
    signal_collector_symbol: str = "BTCUSDT"
    signal_collector_interval: str = "15m"
    signal_collector_limit: int = 200
    signal_collector_period: int = 14
    signal_collector_loop_seconds: int = 60
    state_monitor_refresh_seconds: int = 5

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_auth_db: str = "visutrade_auth"
    mongodb_auth_collection: str = "admin_users"
    mongodb_server_selection_timeout_ms: int = 300
    binance_symbols_cache_ttl_minutes: int = 720

    @model_validator(mode="after")
    def apply_environment_defaults(self) -> "Settings":
        is_production_like = self.app_env.lower() in {"production", "staging"}
        if is_production_like:
            self.frontend_base_url = self.frontend_base_url or "https://trade.visupanel.com"
            self.backend_base_url = self.backend_base_url or "https://api-trade.visupanel.com"
            self.cors_allowed_origins = self.cors_allowed_origins or self.frontend_base_url
        else:
            local_default = "http://localhost:8000"
            self.frontend_base_url = self.frontend_base_url or local_default
            self.backend_base_url = self.backend_base_url or local_default
            self.cors_allowed_origins = self.cors_allowed_origins or local_default
        return self

    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()

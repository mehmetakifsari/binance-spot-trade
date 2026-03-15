from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    binance_stream: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    n8n_webhook_url: str
    bridge_http_port: int = 8001


settings = Settings()

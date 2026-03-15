from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Slack
    slack_bot_token: str = ""
    slack_channel: str = "general"

    # Twitter/X
    twitter_bearer_token: str = ""

    # Schedules (cron)
    business_finder_schedule: str = "0 8 * * *"  # 8am daily


settings = Settings()

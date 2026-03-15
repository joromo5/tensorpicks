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

    # Google Maps (for Local Outreach agent)
    google_maps_api_key: str = ""

    # Gmail (for Local Outreach agent)
    gmail_address: str = ""
    gmail_app_password: str = ""

    # Outreach settings
    outreach_location: str = ""
    outreach_sender_name: str = ""
    outreach_sender_business: str = ""
    outreach_auto_send: bool = False

    # Schedules (cron)
    business_finder_schedule: str = "0 8 * * *"  # 8am daily
    local_outreach_schedule: str = "0 9 * * 1"  # 9am every Monday


settings = Settings()

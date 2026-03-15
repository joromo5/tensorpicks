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

    # Crypto Trader
    crypto_paper_balance: float = 100.0
    crypto_trading_mode: str = "paper"  # "paper" or "live"

    # Content Creator
    slack_app_token: str = ""  # xapp-... for Socket Mode listener
    comfyui_url: str = "http://localhost:8188"
    comfyui_checkpoint: str = "sd_xl_base_1.0.safetensors"
    piper_voice_model: str = "en_US-lessac-medium"
    musicgen_model: str = "facebook/musicgen-small"

    # Schedules (cron)
    business_finder_schedule: str = "0 8 * * *"  # 8am daily
    local_outreach_schedule: str = "0 9 * * 1"  # 9am every Monday
    crypto_trader_schedule: str = "0 */4 * * *"  # every 4 hours


settings = Settings()

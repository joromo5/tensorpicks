import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

_client: WebClient | None = None


def _get_client() -> WebClient:
    global _client
    if _client is None:
        _client = WebClient(token=settings.slack_bot_token)
    return _client


def post(text: str, channel: str | None = None, blocks: list | None = None) -> bool:
    """Post a message to Slack. Returns True on success."""
    ch = channel or settings.slack_channel
    try:
        _get_client().chat_postMessage(channel=ch, text=text, blocks=blocks)
        return True
    except SlackApiError as e:
        log.error("Slack post failed to channel '%s': %s", ch, e.response["error"])
        return False
    except Exception as e:
        log.error("Slack post failed to channel '%s' (network): %s", ch, e)
        return False

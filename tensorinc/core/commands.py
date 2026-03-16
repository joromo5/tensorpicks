"""Slash command handler — listens for Slack slash commands via Socket Mode."""

import logging
import threading

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

_socket_client: SocketModeClient | None = None


def start_command_listener():
    """Start a Socket Mode listener that handles slash commands.

    Requires SLACK_APP_TOKEN (xapp-...) and SLACK_BOT_TOKEN (xoxb-...).
    """
    global _socket_client

    if not settings.slack_app_token:
        log.error("SLACK_APP_TOKEN not set — cannot listen for commands")
        return

    web_client = WebClient(token=settings.slack_bot_token)
    _socket_client = SocketModeClient(
        app_token=settings.slack_app_token,
        web_client=web_client,
    )

    def _handle(client: SocketModeClient, req: SocketModeRequest):
        # Acknowledge immediately with a visible response
        client.send_socket_mode_response(
            SocketModeResponse(
                envelope_id=req.envelope_id,
                payload={"text": ":mag: Running business finder scan... hang tight."},
            )
        )

        if req.type != "slash_commands":
            return

        command = req.payload.get("command", "")
        channel = req.payload.get("channel_id", "")
        user = req.payload.get("user_id", "")

        if command == "/idea":
            log.info("/idea triggered by user %s in %s", user, channel)
            # Run the business finder in a background thread so we don't block
            thread = threading.Thread(
                target=_run_idea, args=(settings.business_finder_channel,), daemon=True
            )
            thread.start()

    _socket_client.socket_mode_request_listeners.append(_handle)

    thread = threading.Thread(target=_socket_client.connect, daemon=True)
    thread.start()
    log.info("Command listener started — /idea ready")


def _run_idea(channel: str):
    """Run the Business Finder agent and post results to the requesting channel."""
    from tensorinc.core import slack
    from tensorinc.business_finder.agent import BusinessFinderAgent

    try:
        agent = BusinessFinderAgent()
        agent.run()
    except Exception as e:
        log.error("/idea failed: %s", e)
        slack.post(f":x: Business finder scan failed: {e}", channel=channel)


def stop_command_listener():
    global _socket_client
    if _socket_client:
        _socket_client.close()
        _socket_client = None

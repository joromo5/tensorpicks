"""Listen for @bot mentions in Slack and queue content creation jobs."""

import logging
import re
import threading
import queue

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from tensorpicks.core.config import settings

log = logging.getLogger(__name__)

# Queue where incoming prompts land for the agent to pick up
job_queue: queue.Queue[dict] = queue.Queue()

_socket_client: SocketModeClient | None = None


def start_listener():
    """Start the Slack Socket Mode listener in a background thread.

    Requires SLACK_APP_TOKEN (xapp-...) for Socket Mode
    and SLACK_BOT_TOKEN (xoxb-...) for API calls.
    """
    global _socket_client

    if not settings.slack_app_token:
        log.error("SLACK_APP_TOKEN not set — cannot listen for mentions")
        return

    web_client = WebClient(token=settings.slack_bot_token)
    _socket_client = SocketModeClient(
        app_token=settings.slack_app_token,
        web_client=web_client,
    )

    # Get our own bot user ID so we can detect @mentions
    try:
        auth = web_client.auth_test()
        bot_user_id = auth["user_id"]
    except Exception as e:
        log.error("Could not get bot user ID: %s", e)
        return

    def _handle_event(client: SocketModeClient, req: SocketModeRequest):
        # Acknowledge immediately
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if req.type != "events_api":
            return

        event = req.payload.get("event", {})

        # Only process messages that @mention the bot
        if event.get("type") != "message" or event.get("subtype"):
            return

        text = event.get("text", "")
        if f"<@{bot_user_id}>" not in text:
            return

        # Strip the @mention from the prompt
        prompt = re.sub(rf"<@{bot_user_id}>\s*", "", text).strip()
        if not prompt:
            return

        channel = event.get("channel", "")
        user = event.get("user", "")
        ts = event.get("ts", "")

        log.info("Content request from %s: %s", user, prompt[:100])

        # React to acknowledge receipt
        try:
            web_client.reactions_add(channel=channel, name="movie_camera", timestamp=ts)
        except Exception:
            pass

        job_queue.put({
            "prompt": prompt,
            "channel": channel,
            "user": user,
            "ts": ts,
        })

    _socket_client.socket_mode_request_listeners.append(_handle_event)

    thread = threading.Thread(target=_socket_client.connect, daemon=True)
    thread.start()
    log.info("Slack listener started — waiting for @mentions")


def stop_listener():
    global _socket_client
    if _socket_client:
        _socket_client.close()
        _socket_client = None

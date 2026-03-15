"""TensorInc — Multi-agent business automation system."""

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from tensorinc.core.config import settings
from tensorinc.business_finder.agent import BusinessFinderAgent
from tensorinc.local_outreach.agent import LocalOutreachAgent
from tensorinc.crypto_trader.agent import CryptoTraderAgent
from tensorinc.content_creator.agent import ContentCreatorAgent
from tensorinc.sports_bettor.agent import SportsBettorAgent
from tensorinc.twitter_monetizer.agent import TwitterMonetizerAgent
from tensorinc.youtube_sleep.agent import YouTubeSleepAgent
from tensorinc.youtube_meditation.agent import YouTubeMeditationAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tensorinc")


def main():
    args = sys.argv[1:]

    # Manual run: `tensorinc run business_finder`
    if args and args[0] == "run":
        agent_name = args[1] if len(args) > 1 else None
        _run_agent(agent_name)
        return

    # Default: start scheduler
    log.info("Starting TensorPicks scheduler...")
    scheduler = BlockingScheduler()

    # Register agents on their schedules
    business_finder = BusinessFinderAgent()
    cron = _parse_cron(settings.business_finder_schedule)
    scheduler.add_job(business_finder.run, CronTrigger(**cron), id="business_finder")
    log.info("Scheduled business_finder: %s", settings.business_finder_schedule)

    local_outreach = LocalOutreachAgent()
    cron = _parse_cron(settings.local_outreach_schedule)
    scheduler.add_job(local_outreach.run, CronTrigger(**cron), id="local_outreach")
    log.info("Scheduled local_outreach: %s", settings.local_outreach_schedule)

    crypto_trader = CryptoTraderAgent()
    cron = _parse_cron(settings.crypto_trader_schedule)
    scheduler.add_job(crypto_trader.run, CronTrigger(**cron), id="crypto_trader")
    log.info("Scheduled crypto_trader: %s", settings.crypto_trader_schedule)

    sports_bettor = SportsBettorAgent()
    cron = _parse_cron(settings.sports_bettor_schedule)
    scheduler.add_job(sports_bettor.run, CronTrigger(**cron), id="sports_bettor")
    log.info("Scheduled sports_bettor: %s", settings.sports_bettor_schedule)

    twitter_monetizer = TwitterMonetizerAgent()
    cron = _parse_cron(settings.twitter_monetizer_schedule)
    scheduler.add_job(twitter_monetizer.run, CronTrigger(**cron), id="twitter_monetizer")
    log.info("Scheduled twitter_monetizer: %s", settings.twitter_monetizer_schedule)

    youtube_sleep = YouTubeSleepAgent()
    cron = _parse_cron(settings.youtube_sleep_schedule)
    scheduler.add_job(youtube_sleep.run, CronTrigger(**cron), id="youtube_sleep")
    log.info("Scheduled youtube_sleep: %s", settings.youtube_sleep_schedule)

    youtube_meditation = YouTubeMeditationAgent()
    cron = _parse_cron(settings.youtube_meditation_schedule)
    scheduler.add_job(youtube_meditation.run, CronTrigger(**cron), id="youtube_meditation")
    log.info("Scheduled youtube_meditation: %s", settings.youtube_meditation_schedule)

    # Content Creator — runs via Slack listener, not cron.
    # Start the listener and schedule periodic queue processing.
    content_creator = ContentCreatorAgent()
    from tensorinc.content_creator.listener import start_listener
    start_listener()
    scheduler.add_job(content_creator.run, "interval", seconds=10, id="content_creator")
    log.info("Content creator listener started")

    # Slash command listener — handles /idea, etc.
    from tensorinc.core.commands import start_command_listener
    start_command_listener()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down.")


def _run_agent(name: str | None):
    """Run a single agent immediately."""
    agents = {
        "business_finder": BusinessFinderAgent,
        "local_outreach": LocalOutreachAgent,
        "crypto_trader": CryptoTraderAgent,
        "content_creator": ContentCreatorAgent,
        "sports_bettor": SportsBettorAgent,
        "twitter_monetizer": TwitterMonetizerAgent,
        "youtube_sleep": YouTubeSleepAgent,
        "youtube_meditation": YouTubeMeditationAgent,
    }

    if not name or name not in agents:
        print(f"Usage: tensorinc run <agent_name>")
        print(f"Available agents: {', '.join(agents.keys())}")
        sys.exit(1)

    log.info("Running agent: %s", name)
    agent = agents[name]()
    agent.run()
    log.info("Agent %s finished.", name)


def _parse_cron(expr: str) -> dict:
    """Parse a standard cron expression into APScheduler kwargs."""
    parts = expr.split()
    fields = ["minute", "hour", "day", "month", "day_of_week"]
    return {fields[i]: parts[i] for i in range(min(len(parts), len(fields)))}


if __name__ == "__main__":
    main()

"""TensorPicks — Multi-agent business automation system."""

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from tensorpicks.core.config import settings
from tensorpicks.agents.business_finder.agent import BusinessFinderAgent
from tensorpicks.agents.local_outreach.agent import LocalOutreachAgent
from tensorpicks.agents.crypto_trader.agent import CryptoTraderAgent
from tensorpicks.agents.content_creator.agent import ContentCreatorAgent
from tensorpicks.agents.sports_bettor.agent import SportsBettorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tensorpicks")


def main():
    args = sys.argv[1:]

    # Manual run: `tensorpicks run business_finder`
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

    # Content Creator — runs via Slack listener, not cron.
    # Start the listener and schedule periodic queue processing.
    content_creator = ContentCreatorAgent()
    from tensorpicks.agents.content_creator.listener import start_listener
    start_listener()
    scheduler.add_job(content_creator.run, "interval", seconds=10, id="content_creator")
    log.info("Content creator listener started")

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
    }

    if not name or name not in agents:
        print(f"Usage: tensorpicks run <agent_name>")
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

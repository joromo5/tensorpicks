"""Sports Bettor Agent — ML-powered sports betting with EV analysis.

Ingests historical data, trains predictive models, pulls live odds from
The Odds API, computes expected value, and tracks P&L on $10 flat bets.
"""

import logging

from tensorpicks.core.agent import Agent
from tensorpicks.core import slack
from tensorpicks.core.config import settings
from tensorpicks.agents.sports_bettor import odds, data_ingest, model, ev, tracker
from tensorpicks.agents.sports_bettor.features import build_features

log = logging.getLogger(__name__)

# Slack message templates
PICK_MSG = """:moneybag: *Sports Pick — {type}*

*{away_team} @ {home_team}*
:point_right: *{pick}* ({odds_str}) — {bookmaker}

*Model:* {model_prob:.1%} | *Book:* {implied_prob:.1%} | *Edge:* {edge:.1%}
*EV:* {ev_pct:+.1f}% | *Kelly:* {kelly:.2%}
*Bet:* ${bet_size:.2f} to win ${potential_profit:.2f}

_{sport}_"""

SUMMARY_MSG = """:chart_with_upwards_trend: *Sports Bettor — Daily Scan*

*Games scanned:* {games_scanned}
*+EV bets found:* {bets_found}
*Bets placed:* {bets_placed}
*Bets settled:* {bets_settled}

:bar_chart: *Lifetime Record:*
{stats}

_Bet size: ${bet_size:.2f} | Min EV: {min_ev:.1f}%_"""

TRAIN_MSG = """:brain: *Model Training Complete*

*Samples:* {samples}
*Win Model Accuracy:* {win_acc:.1%}
*Total Points MAE:* {total_mae:.1f}
*Spread MAE:* {spread_mae:.1f}

_Models saved and ready for predictions_"""

NO_API_KEY_MSG = (
    ":warning: Sports Bettor: THE_ODDS_API_KEY not configured. "
    "Get a free key at https://the-odds-api.com"
)


class SportsBettorAgent(Agent):
    name = "sports_bettor"

    def run(self) -> None:
        self.log.info("Starting sports bettor scan...")

        if not settings.the_odds_api_key:
            slack.post(NO_API_KEY_MSG)
            return

        # 1. Ingest historical data for training
        historical = data_ingest.load_historical()
        if not historical:
            self.log.info("No historical data — ingesting last 90 days...")
            historical = data_ingest.ingest_all(days=90)

        # 2. Fetch team stats
        team_stats = self._fetch_team_stats()

        # 3. Train models if they don't exist or retrain weekly
        if not model.models_exist():
            self.log.info("Training models for the first time...")
            self._train_models(historical, team_stats)

        # 4. Load trained models
        models = model.load_models()
        if not models:
            self.log.error("Failed to load models — aborting scan")
            slack.post(":warning: Sports Bettor: Model loading failed")
            return

        # 5. Settle any pending bets from previous runs
        bets_settled = self._settle_pending()

        # 6. Fetch live odds
        opportunities = odds.fetch_all_upcoming()
        if not opportunities:
            self.log.info("No upcoming games with odds")
            self._post_summary(0, 0, 0, bets_settled)
            return

        # 7. Group by game and find +EV bets
        games_by_id = {}
        for opp in opportunities:
            gid = opp["game_id"]
            if gid not in games_by_id:
                games_by_id[gid] = opp  # store first occurrence for game info

        bets_found = 0
        bets_placed = 0

        for game_id, game_info in games_by_id.items():
            # Build a pseudo-game dict for feature engineering
            game = self._build_game_dict(game_info, team_stats)

            # Build features
            features = build_features(game, historical, team_stats)
            if features is None:
                continue

            # Get model predictions
            prediction = model.predict(models, features)
            if prediction is None:
                continue

            # Find +EV bets across all markets
            ev_bets = ev.find_all_ev_bets(prediction, opportunities, game_id)
            bets_found += len(ev_bets)

            # Place the best bet per game (avoid over-exposure)
            if ev_bets:
                best = ev_bets[0]  # highest EV
                self._place_and_post(best)
                bets_placed += 1

        # 8. Post daily summary
        self._post_summary(len(games_by_id), bets_found, bets_placed, bets_settled)

        # 9. Ingest today's completed games for future training
        self._ingest_new_data()

        self.log.info(
            "Scan complete — %d games, %d +EV bets, %d placed",
            len(games_by_id), bets_found, bets_placed,
        )

    def train(self) -> None:
        """Manual trigger: retrain models on all historical data."""
        self.log.info("Manual model retrain triggered...")
        historical = data_ingest.load_historical()
        if not historical:
            historical = data_ingest.ingest_all(days=90)
        team_stats = self._fetch_team_stats()
        self._train_models(historical, team_stats)

    def _train_models(self, historical: list[dict], team_stats: dict) -> None:
        """Train and save models, post results to Slack."""
        metrics = model.train(historical, team_stats)

        if "error" in metrics:
            slack.post(
                f":warning: Sports Bettor: Training failed — {metrics['error']} "
                f"({metrics.get('samples', 0)} samples)"
            )
            return

        slack.post(TRAIN_MSG.format(
            samples=metrics["win_prob"]["samples"],
            win_acc=metrics["win_prob"]["accuracy"],
            total_mae=metrics["total_points"]["mae"],
            spread_mae=metrics["spread"]["mae"],
        ))

    def _fetch_team_stats(self) -> dict:
        """Fetch team stats for all active sports."""
        all_stats = {}
        for sport_key in data_ingest.ESPN_SPORTS:
            stats = data_ingest.fetch_espn_team_stats(sport_key)
            all_stats.update(stats)
        return all_stats

    def _build_game_dict(self, opp: dict, team_stats: dict) -> dict:
        """Build a game dict from an odds opportunity for feature engineering."""
        home = opp.get("home_team", "")
        away = opp.get("away_team", "")

        # Try to find team abbreviations from team_stats
        home_abbr = away_abbr = ""
        for abbr, info in team_stats.items():
            name = info.get("team_name", "")
            if name == home or home in name:
                home_abbr = abbr
            if name == away or away in name:
                away_abbr = abbr

        # Fallback: use first 3 chars
        if not home_abbr:
            home_abbr = home[:3].upper()
        if not away_abbr:
            away_abbr = away[:3].upper()

        home_stats = team_stats.get(home_abbr, {}).get("stats", {})
        away_stats = team_stats.get(away_abbr, {}).get("stats", {})

        # Build record strings from stats
        home_wins = int(home_stats.get("wins", 0))
        home_losses = int(home_stats.get("losses", 0))
        away_wins = int(away_stats.get("wins", 0))
        away_losses = int(away_stats.get("losses", 0))

        return {
            "sport": opp.get("sport", ""),
            "event_id": opp.get("game_id", ""),
            "date": opp.get("commence_time", ""),
            "status": "STATUS_SCHEDULED",
            "home_team": home,
            "home_abbr": home_abbr,
            "home_score": None,
            "home_record": f"{home_wins}-{home_losses}",
            "home_stats": home_stats,
            "away_team": away,
            "away_abbr": away_abbr,
            "away_score": None,
            "away_record": f"{away_wins}-{away_losses}",
            "away_stats": away_stats,
            "venue_name": "",
            "venue_city": "",
            "venue_state": "",
            "venue_indoor": None,
        }

    def _place_and_post(self, bet: dict) -> None:
        """Place a bet and post to Slack."""
        record = tracker.place_bet(bet)

        price = bet["american_odds"]
        odds_str = f"+{price}" if price > 0 else str(price)

        slack.post(PICK_MSG.format(
            type=bet["type"].upper(),
            away_team=bet["away_team"],
            home_team=bet["home_team"],
            pick=bet["pick"],
            odds_str=odds_str,
            bookmaker=bet["bookmaker"],
            model_prob=bet["model_prob"],
            implied_prob=bet["implied_prob"],
            edge=bet["edge"],
            ev_pct=bet["ev_pct"],
            kelly=bet["kelly_fraction"],
            bet_size=record["bet_size"],
            potential_profit=record["potential_profit"],
            sport=bet.get("sport", ""),
        ))

    def _settle_pending(self) -> int:
        """Settle pending bets using latest scores."""
        pending = tracker.get_pending_bets()
        if not pending:
            return 0

        # Get scores for sports with pending bets
        sports_needed = set(b.get("sport", "") for b in pending)
        all_scores = []
        for sport in sports_needed:
            scores = odds.get_scores(sport, days_from=3)
            all_scores.extend(scores)

        settled = tracker.settle_from_scores(all_scores)

        for bet in settled:
            pnl = bet.get("actual_pnl", 0)
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            emoji = ":white_check_mark:" if bet["status"] == "won" else ":x:"
            slack.post(
                f"{emoji} *Bet #{bet['id']} settled: {bet['status'].upper()}*\n"
                f"{bet['type'].upper()} — {bet['pick']}\n"
                f"PnL: {pnl_str}"
            )

        return len(settled)

    def _post_summary(self, games_scanned: int, bets_found: int,
                      bets_placed: int, bets_settled: int) -> None:
        """Post daily summary to Slack."""
        stats = tracker.get_stats()
        stats_str = tracker.format_stats(stats)

        slack.post(SUMMARY_MSG.format(
            games_scanned=games_scanned,
            bets_found=bets_found,
            bets_placed=bets_placed,
            bets_settled=bets_settled,
            stats=stats_str,
            bet_size=settings.sports_bettor_bet_size,
            min_ev=settings.sports_bettor_min_ev,
        ))

    def _ingest_new_data(self) -> None:
        """Ingest recently completed games for future model training."""
        for sport_key in data_ingest.ESPN_SPORTS:
            games = data_ingest.fetch_recent_games(sport_key, days=3)
            if games:
                data_ingest.save_historical(games)

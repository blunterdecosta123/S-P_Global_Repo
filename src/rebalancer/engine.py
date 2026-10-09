import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from src.risk_engine.models import RiskSignal

class TacticalRebalancer:
    """
    Module A: Tactical Index Rebalancing Engine.
    Subscribes to Sentiment Scores from the AI/NLP Risk Engine and dynamically
    rebalances a mock S&P 100 basket.
    """

    def __init__(self, constituents_file: str = "data/mock_sp100_constituents.json", alpha_tilt: float = 0.40):
        self.alpha_tilt = alpha_tilt # Tilt sensitivity factor
        self.constituents: Dict[str, Dict[str, Any]] = {}
        self.current_weights: Dict[str, float] = {}
        self.benchmark_weights: Dict[str, float] = {}
        self.sentiment_memory: Dict[str, float] = {}
        self.rebalance_history: List[Dict[str, Any]] = []
        self.cumulative_strategy_return: float = 0.0
        self.cumulative_benchmark_return: float = 0.0

        self._load_constituents(constituents_file)
        # Record baseline point
        self._record_history_snapshot("Baseline (Pre-sentiment)")

    def _load_constituents(self, filepath: str):
        path = Path(filepath)
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
                for item in data:
                    ticker = item["ticker"]
                    self.constituents[ticker] = item
                    self.benchmark_weights[ticker] = item["benchmark_weight"]
                    self.current_weights[ticker] = item["benchmark_weight"]
                    self.sentiment_memory[ticker] = 0.0 # Neutral baseline
        else:
            raise FileNotFoundError(f"Constituents file not found at {filepath}")

    def on_risk_signal(self, signal: RiskSignal):
        """
        Event handler when a new RiskSignal arrives from the Risk Engine.
        Updates sentiment memory for affected tickers and triggers dynamic rebalance.
        """
        if not signal.detected_tickers:
            return

        updated_any = False
        for ticker in signal.detected_tickers:
            if ticker in self.constituents:
                # Exponential update: new signal blended with memory
                current_sentiment = self.sentiment_memory.get(ticker, 0.0)
                # 65% weight on new event, 35% on historical momentum
                self.sentiment_memory[ticker] = round((signal.sentiment_score * 0.65) + (current_sentiment * 0.35), 3)
                updated_any = True

        if updated_any:
            self.rebalance(reason=f"Signal {signal.signal_id} ({signal.event_classification})")

    def rebalance(self, reason: str = "Tactical Trigger") -> Dict[str, Any]:
        """
        Calculates new target weights:
        w_i = w_base * (1 + alpha * sentiment_i)
        Applies bounding [1% to 22%] and renormalizes to 100%.
        """
        raw_weights = {}
        min_weight = 0.015
        max_weight = 0.220

        for ticker, base_w in self.benchmark_weights.items():
            sent = self.sentiment_memory.get(ticker, 0.0)
            # Alpha tilt multiplier
            tilt = 1.0 + (self.alpha_tilt * sent)
            raw_w = max(min_weight, min(max_weight, base_w * tilt))
            raw_weights[ticker] = raw_w

        # Normalize to 1.0 (100%)
        total_raw = sum(raw_weights.values())
        new_weights = {t: round(w / total_raw, 4) for t, w in raw_weights.items()}

        # Calculate portfolio turnover: 0.5 * sum(|w_new - w_old|)
        turnover = 0.5 * sum(abs(new_weights[t] - self.current_weights[t]) for t in self.current_weights)

        # Calculate simulated price delta
        # Higher positive sentiment stocks generate simulated price lift
        sim_strat_ret = sum(self.current_weights[t] * (self.sentiment_memory[t] * 0.018) for t in self.current_weights)
        sim_bench_ret = sum(self.benchmark_weights[t] * (self.sentiment_memory[t] * 0.009) for t in self.benchmark_weights)
        
        self.cumulative_strategy_return += sim_strat_ret
        self.cumulative_benchmark_return += sim_bench_ret

        # Update current weights
        self.current_weights = new_weights

        snapshot = self._record_history_snapshot(reason, turnover)
        return snapshot

    def _record_history_snapshot(self, reason: str, turnover: float = 0.0) -> Dict[str, Any]:
        top_overweighted = sorted(
            [{"ticker": t, "diff": round(self.current_weights[t] - self.benchmark_weights[t], 4), "sentiment": self.sentiment_memory[t]}
             for t in self.current_weights],
            key=lambda x: x["diff"],
            reverse=True
        )[:3]

        top_underweighted = sorted(
            [{"ticker": t, "diff": round(self.current_weights[t] - self.benchmark_weights[t], 4), "sentiment": self.sentiment_memory[t]}
             for t in self.current_weights],
            key=lambda x: x["diff"]
        )[:3]

        snapshot = {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "reason": reason,
            "turnover_pct": round(turnover * 100, 2),
            "weights": dict(self.current_weights),
            "sentiments": dict(self.sentiment_memory),
            "top_overweighted": top_overweighted,
            "top_underweighted": top_underweighted,
            "cumulative_strategy_return_pct": round(self.cumulative_strategy_return * 100, 2),
            "cumulative_benchmark_return_pct": round(self.cumulative_benchmark_return * 100, 2),
            "active_alpha_pct": round((self.cumulative_strategy_return - self.cumulative_benchmark_return) * 100, 2)
        }
        self.rebalance_history.append(snapshot)
        return snapshot

    def get_current_state(self) -> Dict[str, Any]:
        stock_details = []
        for ticker, info in self.constituents.items():
            current_w = self.current_weights.get(ticker, 0.0)
            bench_w = self.benchmark_weights.get(ticker, 0.0)
            sent = self.sentiment_memory.get(ticker, 0.0)
            delta = round((current_w - bench_w) * 100, 2)
            stock_details.append({
                "ticker": ticker,
                "name": info["name"],
                "sector": info["sector"],
                "benchmark_weight_pct": round(bench_w * 100, 2),
                "tactical_weight_pct": round(current_w * 100, 2),
                "delta_weight_pct": delta,
                "sentiment": sent,
                "allocation_action": "OVERWEIGHT" if delta > 0.5 else ("UNDERWEIGHT" if delta < -0.5 else "NEUTRAL")
            })

        return {
            "alpha_tilt": self.alpha_tilt,
            "strategy_return_pct": round(self.cumulative_strategy_return * 100, 2),
            "benchmark_return_pct": round(self.cumulative_benchmark_return * 100, 2),
            "active_alpha_pct": round((self.cumulative_strategy_return - self.cumulative_benchmark_return) * 100, 2),
            "stocks": stock_details,
            "history": self.rebalance_history[-20:]
        }

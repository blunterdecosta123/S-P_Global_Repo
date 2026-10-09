import json
import math
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from src.risk_engine.models import RiskSignal

class PortfolioStressTester:
    """
    Module B: Strategic Portfolio Stress Testing Tool.
    Subscribes to Event Classification and Impact Score from the AI/NLP Risk Engine
    and simulates multi-asset wholesale banking portfolio shocks.
    """

    def __init__(
        self,
        portfolio_file: str = "data/synthetic_wholesale_portfolio.json",
        scenarios_file: str = "data/historical_scenarios.json",
        impact_trigger_threshold: float = 7.0
    ):
        self.impact_trigger_threshold = impact_trigger_threshold
        self.portfolio_data: Dict[str, Any] = {}
        self.scenarios: Dict[str, Dict[str, Any]] = {}
        self.stress_history: List[Dict[str, Any]] = []
        self.last_simulation_result: Optional[Dict[str, Any]] = None

        self._load_data(portfolio_file, scenarios_file)
        # Pre-calculate baseline metrics
        self.baseline_metrics = self._calculate_baseline_metrics()

    def _load_data(self, portfolio_path: str, scenarios_path: str):
        p_path = Path(portfolio_path)
        if p_path.exists():
            with open(p_path, "r") as f:
                self.portfolio_data = json.load(f)
        else:
            raise FileNotFoundError(f"Portfolio file not found at {portfolio_path}")

        s_path = Path(scenarios_path)
        if s_path.exists():
            with open(s_path, "r") as f:
                s_list = json.load(f)
                for scen in s_list:
                    self.scenarios[scen["id"]] = scen
        else:
            self.scenarios = {}

    def _calculate_baseline_metrics(self) -> Dict[str, Any]:
        total_notional = self.portfolio_data["total_notional"]
        total_ecl = 0.0
        by_class = {}

        for p in self.portfolio_data["positions"]:
            ac = p["asset_class"]
            notional = p["notional"]
            pd_val = p["pd"]
            lgd_val = p["lgd"]
            ecl = notional * pd_val * lgd_val
            total_ecl += ecl

            if ac not in by_class:
                by_class[ac] = {"notional": 0.0, "count": 0, "ecl": 0.0}
            by_class[ac]["notional"] += notional
            by_class[ac]["count"] += 1
            by_class[ac]["ecl"] += ecl

        return {
            "total_notional": total_notional,
            "baseline_value": total_notional - total_ecl,
            "baseline_ecl": round(total_ecl, 2),
            "base_cet1_ratio": self.portfolio_data.get("base_cet1_capital_ratio", 0.134),
            "regulatory_min_cet1": self.portfolio_data.get("regulatory_minimum_cet1", 0.105),
            "risk_weighted_assets": self.portfolio_data.get("risk_weighted_assets_base", 340000000),
            "breakdown_by_class": by_class
        }

    def on_risk_signal(self, signal: RiskSignal) -> Optional[Dict[str, Any]]:
        """
        Subscribes to NLP Risk Engine.
        Triggers stress test when high-impact event is detected (Impact Score >= threshold).
        """
        if signal.impact_score >= self.impact_trigger_threshold:
            # Map event classification to shock parameters
            shocks = self.map_signal_to_shocks(signal)
            result = self.run_stress_test(
                scenario_name=f"Automated Event Trigger: {signal.event_classification} (Impact {signal.impact_score}/10)",
                shocks=shocks,
                triggered_by_signal=signal
            )
            return result
        return None

    def map_signal_to_shocks(self, signal: RiskSignal) -> Dict[str, float]:
        """
        Translates NLP Event Classification and Impact Score into quantitative market shocks.
        """
        severity_ratio = (signal.impact_score - 5.0) / 5.0 # scale factor around baseline
        severity_ratio = max(0.2, min(1.6, severity_ratio))

        category = signal.event_classification
        if category == "Geopolitical":
            return {
                "equity_shock_pct": -12.0 * severity_ratio,
                "interest_rate_shock_bps": 75 * severity_ratio,
                "credit_spread_widening_bps": 160 * severity_ratio,
                "pd_multiplier": 1.0 + (0.80 * severity_ratio),
                "lgd_multiplier": 1.0 + (0.25 * severity_ratio),
                "energy_boost_pct": 10.0
            }
        elif category == "Credit Event":
            return {
                "equity_shock_pct": -15.0 * severity_ratio,
                "interest_rate_shock_bps": -25 * severity_ratio, # Flight to quality
                "credit_spread_widening_bps": 280 * severity_ratio,
                "pd_multiplier": 1.0 + (1.40 * severity_ratio),
                "lgd_multiplier": 1.0 + (0.35 * severity_ratio),
                "energy_boost_pct": -5.0
            }
        elif category == "Macroeconomic":
            rate_direction = 1.0 if signal.sentiment_score < 0 else -0.5
            return {
                "equity_shock_pct": -11.0 * severity_ratio,
                "interest_rate_shock_bps": (120 * severity_ratio) * rate_direction,
                "credit_spread_widening_bps": 120 * severity_ratio,
                "pd_multiplier": 1.0 + (0.50 * severity_ratio),
                "lgd_multiplier": 1.0 + (0.15 * severity_ratio),
                "energy_boost_pct": 0.0
            }
        elif category == "Regulatory & Compliance":
            return {
                "equity_shock_pct": -8.0 * severity_ratio,
                "interest_rate_shock_bps": 15 * severity_ratio,
                "credit_spread_widening_bps": 70 * severity_ratio,
                "pd_multiplier": 1.0 + (0.30 * severity_ratio),
                "lgd_multiplier": 1.0 + (0.10 * severity_ratio),
                "energy_boost_pct": 0.0
            }
        else: # Default moderate shock
            return {
                "equity_shock_pct": -6.0 * severity_ratio,
                "interest_rate_shock_bps": 30 * severity_ratio,
                "credit_spread_widening_bps": 50 * severity_ratio,
                "pd_multiplier": 1.0 + (0.25 * severity_ratio),
                "lgd_multiplier": 1.0 + (0.08 * severity_ratio),
                "energy_boost_pct": 0.0
            }

    def run_stress_test(
        self,
        scenario_name: str,
        shocks: Dict[str, float],
        triggered_by_signal: Optional[RiskSignal] = None
    ) -> Dict[str, Any]:
        """
        Simulates asset revaluations across Corporate Loans, Bonds, and Derivatives.
        """
        ir_shock_decimal = shocks.get("interest_rate_shock_bps", 100) / 10000.0 # bps to decimal
        spread_shock_decimal = shocks.get("credit_spread_widening_bps", 150) / 10000.0
        pd_mult = shocks.get("pd_multiplier", 1.5)
        lgd_mult = shocks.get("lgd_multiplier", 1.2)

        stressed_positions = []
        total_pre_value = 0.0
        total_post_value = 0.0
        total_loss = 0.0

        class_summary = {}

        for p in self.portfolio_data["positions"]:
            ac = p["asset_class"]
            notional = p["notional"]
            duration = p["duration"]
            base_pd = p["pd"]
            base_lgd = p["lgd"]
            
            # Baseline valuation
            base_ecl = notional * base_pd * base_lgd
            pre_val = notional - base_ecl

            # Asset class specific shock mechanics
            delta_val = 0.0
            
            if ac == "Corporate Loan":
                # Stressed ECL + credit spread discount
                stressed_pd = min(0.99, base_pd * pd_mult)
                stressed_lgd = min(0.95, base_lgd * lgd_mult)
                stressed_ecl = notional * stressed_pd * stressed_lgd
                ecl_delta = stressed_ecl - base_ecl
                # Duration-based market value discount for spread widening
                spread_val_loss = notional * duration * spread_shock_decimal * 0.70
                delta_val = -(ecl_delta + spread_val_loss)

            elif ac in ["Sovereign Bond", "Corporate Bond"]:
                # Modified duration & convexity bond pricing
                convexity = (duration ** 2) * 0.5
                rate_effect = -duration * ir_shock_decimal + (0.5 * convexity * (ir_shock_decimal ** 2))
                spread_effect = -(duration * spread_shock_decimal) if ac == "Corporate Bond" else 0.0
                price_pct_change = rate_effect + spread_effect
                delta_val = notional * price_pct_change

            elif ac == "Derivative (IRS)":
                # USD Payer Swap gains when interest rates rise, loses when rates fall
                # DV01 approximation = Notional * Duration / 10,000
                dv01 = notional * (duration / 10000.0)
                delta_val = dv01 * shocks.get("interest_rate_shock_bps", 100)

            elif ac == "Derivative (CDS)":
                # Protection Bought gains as spreads widen; Protection Sold loses
                cs01 = notional * (duration / 10000.0)
                if "Bought" in p["name"]:
                    delta_val = cs01 * shocks.get("credit_spread_widening_bps", 150)
                else: # Sold protection
                    delta_val = -cs01 * shocks.get("credit_spread_widening_bps", 150)

            elif ac == "Derivative (FX)":
                # Cross-currency basis and FX volatility haircut
                delta_val = -notional * 0.015 * abs(ir_shock_decimal * 100)

            post_val = max(0.0, pre_val + delta_val)
            position_loss = pre_val - post_val

            total_pre_value += pre_val
            total_post_value += post_val
            total_loss += position_loss

            if ac not in class_summary:
                class_summary[ac] = {
                    "pre_value": 0.0,
                    "post_value": 0.0,
                    "loss": 0.0,
                    "loss_pct": 0.0
                }
            class_summary[ac]["pre_value"] += pre_val
            class_summary[ac]["post_value"] += post_val
            class_summary[ac]["loss"] += position_loss

            stressed_positions.append({
                "asset_id": p["asset_id"],
                "name": p["name"],
                "asset_class": ac,
                "sector": p["sector"],
                "rating": p["rating"],
                "notional": notional,
                "pre_value": round(pre_val, 2),
                "post_value": round(post_val, 2),
                "loss": round(position_loss, 2),
                "loss_pct": round((position_loss / pre_val) * 100, 2) if pre_val > 0 else 0.0
            })

        for ac, data in class_summary.items():
            if data["pre_value"] > 0:
                data["loss_pct"] = round((data["loss"] / data["pre_value"]) * 100, 2)
                data["pre_value"] = round(data["pre_value"], 2)
                data["post_value"] = round(data["post_value"], 2)
                data["loss"] = round(data["loss"], 2)

        portfolio_loss_pct = round((total_loss / total_pre_value) * 100, 2) if total_pre_value > 0 else 0.0

        # Basel III Capital Adequacy Stress Impact
        # Tier 1 Capital is eroded by total loss
        base_rwa = self.baseline_metrics["risk_weighted_assets"]
        # RWA inflates due to PD migrations
        stressed_rwa = base_rwa * (1.0 + (shocks.get("credit_spread_widening_bps", 100) / 1000.0))
        base_tier1_capital = base_rwa * self.baseline_metrics["base_cet1_ratio"]
        stressed_tier1_capital = max(0.0, base_tier1_capital - total_loss)
        post_cet1_ratio = round(stressed_tier1_capital / stressed_rwa, 4)
        cet1_breach = post_cet1_ratio < self.baseline_metrics["regulatory_min_cet1"]

        # Parametric Value at Risk (VaR 99%) and Expected Shortfall
        simulated_vol = math.sqrt(abs(portfolio_loss_pct)) * 0.035
        var_99_dollar = round(total_pre_value * (1.645 * simulated_vol + (portfolio_loss_pct / 100.0)), 2)
        var_99_dollar = max(round(total_loss, 2), var_99_dollar)
        expected_shortfall = round(var_99_dollar * 1.18, 2)

        simulation_result = {
            "simulation_id": f"STRESS-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            "scenario_name": scenario_name,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "shocks_applied": shocks,
            "triggered_by": {
                "signal_id": triggered_by_signal.signal_id if triggered_by_signal else None,
                "event": triggered_by_signal.event_classification if triggered_by_signal else "User Manual / Preset",
                "impact_score": triggered_by_signal.impact_score if triggered_by_signal else None,
                "headline": triggered_by_signal.headline if triggered_by_signal else None
            } if triggered_by_signal else None,
            "metrics": {
                "pre_stress_value": round(total_pre_value, 2),
                "post_stress_value": round(total_post_value, 2),
                "total_loss_dollar": round(total_loss, 2),
                "total_loss_pct": portfolio_loss_pct,
                "pre_cet1_ratio_pct": round(self.baseline_metrics["base_cet1_ratio"] * 100, 2),
                "post_cet1_ratio_pct": round(post_cet1_ratio * 100, 2),
                "regulatory_min_cet1_pct": round(self.baseline_metrics["regulatory_min_cet1"] * 100, 2),
                "capital_adequacy_breach": cet1_breach,
                "var_99_dollar": var_99_dollar,
                "expected_shortfall_cvar_dollar": expected_shortfall
            },
            "class_summary": class_summary,
            "top_vulnerable_positions": sorted(stressed_positions, key=lambda x: x["loss"], reverse=True)[:5],
            "all_positions": stressed_positions
        }

        self.last_simulation_result = simulation_result
        self.stress_history.append(simulation_result)
        return simulation_result

    def get_state(self) -> Dict[str, Any]:
        return {
            "baseline": self.baseline_metrics,
            "available_scenarios": list(self.scenarios.values()),
            "last_simulation": self.last_simulation_result or self.run_preset_scenario("SCEN_GEOPOLITICAL_CRISIS"),
            "history_count": len(self.stress_history)
        }

    def run_preset_scenario(self, scenario_id: str) -> Dict[str, Any]:
        scen = self.scenarios.get(scenario_id)
        if not scen:
            # fallback scenario
            scen = list(self.scenarios.values())[0]
        return self.run_stress_test(
            scenario_name=scen["name"],
            shocks=scen["shocks"]
        )

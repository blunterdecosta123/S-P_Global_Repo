import os
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from src.risk_engine import IngestionManager, RawIngestionItem, RiskSignal
from src.rebalancer import TacticalRebalancer
from src.stress_testing import PortfolioStressTester

# Initialize FastAPI App
app = FastAPI(
    title="S&P Global & CRISIL AI/NLP Risk Engine",
    description="Unified AI/NLP Risk Engine with Tactical Rebalancer & Portfolio Stress Testing",
    version="1.0.0"
)

_live_ingestion_task = None

async def _live_ingestion_loop():
    """Continuously poll public GDELT news and the local social/news stream."""
    interval = max(30, int(os.getenv("LIVE_POLL_INTERVAL_SECONDS", "60")))
    while True:
        await asyncio.to_thread(ingestion_mgr.poll_live_sources)
        await asyncio.sleep(interval)

# Core singletons
ingestion_mgr = IngestionManager(data_dir="data")
rebalancer = TacticalRebalancer(constituents_file="data/mock_sp100_constituents.json")
stress_tester = PortfolioStressTester(
    portfolio_file="data/synthetic_wholesale_portfolio.json",
    scenarios_file="data/historical_scenarios.json"
)

# Wire subscriptions: real-time event streaming to downstream modules
ingestion_mgr.subscribe(rebalancer.on_risk_signal)
ingestion_mgr.subscribe(stress_tester.on_risk_signal)

# Feed initial history into modules
for signal in ingestion_mgr.signals_history:
    rebalancer.on_risk_signal(signal)
    stress_tester.on_risk_signal(signal)

# Request schemas
class ManualAnalysisRequest(BaseModel):
    text: str
    headline: Optional[str] = ""
    source: Optional[str] = "Live Feed"
    author_or_handle: Optional[str] = "@MarketWatcher"
    target_tickers: Optional[List[str]] = []

class CustomStressRequest(BaseModel):
    scenario_name: str
    equity_shock_pct: float = -15.0
    interest_rate_shock_bps: float = 100.0
    credit_spread_widening_bps: float = 150.0
    pd_multiplier: float = 1.5
    lgd_multiplier: float = 1.2
    energy_boost_pct: float = 0.0

# ----------------- API ENDPOINTS -----------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "AI/NLP Financial Risk Engine",
        "signals_processed": len(ingestion_mgr.signals_history),
        "module_a_active": True,
        "module_b_active": True,
        "live_ingestion": ingestion_mgr.live_stats
    }

@app.get("/api/risk-engine/signals")
def get_signals(limit: int = 50):
    return [s.model_dump() for s in ingestion_mgr.get_recent_signals(limit)]

@app.post("/api/risk-engine/analyze")
def analyze_text(req: ManualAnalysisRequest):
    item = RawIngestionItem(
        source=req.source,
        headline_or_title=req.headline,
        text=req.text,
        author_or_handle=req.author_or_handle,
        target_tickers=req.target_tickers
    )
    signal = ingestion_mgr.ingest_single(item)
    return signal.model_dump()

# Pre-defined simulation feed queue for live demo clicks
SIMULATION_FEED_QUEUE = [
    {
        "source": "Financial News (Breaking)",
        "headline": "OPEC+ Unexpectedly Slashing Crude Output by 1.8M Barrels; Brent Surges Past $98",
        "text": "Energy ministers announced an emergency production restraint agreement citing regional transit safety concerns. Refinery margins tightened abruptly across European hubs.",
        "target_tickers": ["XOM"],
        "author": "Bloomberg Energy Desk"
    },
    {
        "source": "Social Media (Twitter/X)",
        "headline": "FinTwit Alert",
        "text": "$NVDA CEO announces next-generation Quantum-AI hybrid architecture ahead of schedule. Enterprise customer backlog now extends 18 months. Absolute dominance! 🚀",
        "target_tickers": ["NVDA"],
        "author": "@QuantTechInvest"
    },
    {
        "source": "Financial News (Wire)",
        "headline": "Moody's Downgrades Commercial Office Debt Tranches to Ca Following Distressed Restructuring",
        "text": "Default probability indices jumped to multi-year highs as secondary loan marks dropped below 70 cents on the dollar. Regional banking reserves under heavy scrutiny.",
        "target_tickers": ["BAC", "JPM"],
        "author": "Financial Times Credit"
    },
    {
        "source": "Social Media (Twitter/X)",
        "headline": "FinTwit Alert",
        "text": "Fed Chair reiterates 'Higher For Longer' interest rate trajectory as core services inflation remains sticky. Tech sector valuations adjusting fast. $MSFT $AAPL $QQQ",
        "target_tickers": ["MSFT", "AAPL"],
        "author": "@MacroStrategist"
    }
]
_sim_index = 0

@app.post("/api/risk-engine/simulate-next")
def simulate_next_event():
    # Attempt a fresh GDELT poll on every demo click. If GDELT rate-limits
    # the request, poll_live_sources keeps the local news/social fallback active.
    before_count = len(ingestion_mgr.signals_history)
    poll_status = ingestion_mgr.poll_live_sources()
    new_signals = ingestion_mgr.signals_history[before_count:]
    live_signal = next(
        (s for s in reversed(new_signals) if "GDELT 2.0 Raw GKG" in s.source_name),
        new_signals[-1] if new_signals else None
    )
    return {
        "new_signal": live_signal.model_dump() if live_signal else None,
        "new_signals": [s.model_dump() for s in new_signals],
        "ingestion_status": poll_status,
        "total_signals": len(ingestion_mgr.signals_history)
    }

@app.get("/api/rebalancer/state")
def get_rebalancer_state():
    return rebalancer.get_current_state()

@app.on_event("startup")
async def start_live_ingestion():
    global _live_ingestion_task
    if os.getenv("LIVE_INGESTION_ENABLED", "true").lower() not in {"0", "false", "no"}:
        _live_ingestion_task = asyncio.create_task(_live_ingestion_loop())

@app.on_event("shutdown")
async def stop_live_ingestion():
    global _live_ingestion_task
    if _live_ingestion_task:
        _live_ingestion_task.cancel()
        try:
            await _live_ingestion_task
        except asyncio.CancelledError:
            pass
        _live_ingestion_task = None

@app.get("/api/stress-test/state")
def get_stress_test_state():
    return stress_tester.get_state()

@app.post("/api/stress-test/simulate-preset/{scenario_id}")
def simulate_preset(scenario_id: str):
    res = stress_tester.run_preset_scenario(scenario_id)
    return res

@app.post("/api/stress-test/simulate-custom")
def simulate_custom(req: CustomStressRequest):
    shocks = {
        "equity_shock_pct": req.equity_shock_pct,
        "interest_rate_shock_bps": req.interest_rate_shock_bps,
        "credit_spread_widening_bps": req.credit_spread_widening_bps,
        "pd_multiplier": req.pd_multiplier,
        "lgd_multiplier": req.lgd_multiplier,
        "energy_boost_pct": req.energy_boost_pct
    }
    res = stress_tester.run_stress_test(
        scenario_name=req.scenario_name,
        shocks=shocks
    )
    return res

@app.get("/api/export/signals/json")
def export_json():
    content = ingestion_mgr.export_signals_json()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=risk_signals_export.json"}
    )

@app.get("/api/export/signals/csv")
def export_csv():
    content = ingestion_mgr.export_signals_csv()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=risk_signals_export.csv"}
    )

# Static UI serving
UI_DIR = Path(__file__).parent / "ui"
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = UI_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r") as f:
            return f.read()
    return "<h1>Risk Engine UI Not Found</h1>"

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

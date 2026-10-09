from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class RawIngestionItem(BaseModel):
    id: Optional[str] = None
    source: str
    headline_or_title: Optional[str] = None
    text: str
    author_or_handle: Optional[str] = None
    timestamp: Optional[str] = None
    target_tickers: Optional[List[str]] = None

class RiskSignal(BaseModel):
    signal_id: str
    timestamp: str
    source_type: str # 'Financial News' or 'Social Media (Twitter/X)'
    source_name: str
    raw_text: str
    headline: Optional[str] = None
    primary_entity: str
    detected_tickers: List[str]
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment polarity [-1.0 to 1.0]")
    sentiment_label: str # 'Strongly Bearish', 'Bearish', 'Neutral', 'Bullish', 'Strongly Bullish'
    event_classification: str # 'Geopolitical', 'Macroeconomic', 'Credit Event', 'Merger & Acquisition', etc.
    impact_score: float = Field(..., ge=1.0, le=10.0, description="Severity score [1.0 to 10.0]")
    severity_tier: str # 'Low', 'Moderate', 'High', 'Critical'
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    transmission_channels: List[str]
    metadata: Optional[Dict[str, Any]] = None

class BatchAnalysisRequest(BaseModel):
    items: List[RawIngestionItem]

class SingleAnalysisRequest(BaseModel):
    text: str
    headline: Optional[str] = None
    source: Optional[str] = "Manual Input"
    author_or_handle: Optional[str] = "@Analyst"

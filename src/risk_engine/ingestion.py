import json
import csv
import io
import random
import hashlib
import os
import requests
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

from .models import RawIngestionItem, RiskSignal
from .nlp_analyzer import FinancialNLPAnalyzer

class IngestionManager:
    """
    Manages multi-source data ingestion (Financial News, Social Media / Twitter,
    GDELT Live Global Knowledge Graph, Kaggle Financial PhraseBank, and Stock Tweets)
    and processes them via the FinancialNLPAnalyzer.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.analyzer = FinancialNLPAnalyzer()
        self.signals_history: List[RiskSignal] = []
        self.subscribers: List[Callable[[RiskSignal], None]] = []
        
        # Load external dataset pools for live streaming simulation
        self.external_news_pool: List[Dict[str, Any]] = []
        self.external_tweets_pool: List[Dict[str, Any]] = []
        self.gdelt_pool: List[Dict[str, Any]] = []
        self.seen_live_articles = set()
        self.last_gkg_update = None
        self.live_stats: Dict[str, Any] = {
            "last_poll_at": None,
            "last_poll_status": "not_started",
            "last_gdelt_articles": 0,
            "live_articles_ingested": 0,
            "poll_interval_seconds": int(os.getenv("LIVE_POLL_INTERVAL_SECONDS", "60"))
        }

        self._load_external_datasets()
        self._load_seed_data()

    def _load_external_datasets(self):
        """Loads genuine downloaded external datasets into active memory pools."""
        # 1. Kaggle Financial PhraseBank
        phrasebank_file = self.data_dir / "financial_phrasebank" / "FinancialPhraseBank-v1.0" / "Sentences_50Agree.txt"
        if phrasebank_file.exists():
            try:
                with open(phrasebank_file, "r", encoding="latin-1") as f:
                    for line in f:
                        line = line.strip()
                        if "@" in line:
                            sentence, sentiment = line.rsplit("@", 1)
                            self.external_news_pool.append({
                                "text": sentence.strip(),
                                "ground_truth_sentiment": sentiment.strip(),
                                "source": "Kaggle Financial News (PhraseBank)"
                            })
            except Exception as e:
                print(f"[IngestionManager] PhraseBank load error: {e}")

        # 2. Kaggle / Hugging Face Twitter Financial News
        tweets_csv = self.data_dir / "stock_tweets_sentiment_dataset.csv"
        if tweets_csv.exists():
            try:
                with open(tweets_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        t_text = row.get("text", "")
                        if t_text:
                            self.external_tweets_pool.append({
                                "text": t_text.strip(),
                                "label": row.get("label", ""),
                                "source": "Stock Tweets (Kaggle / FinTwit)"
                            })
            except Exception as e:
                print(f"[IngestionManager] Tweets CSV load error: {e}")

        # 3. GDELT 2.0 Global Financial Events
        gdelt_file = self.data_dir / "gdelt_financial_events.json"
        if gdelt_file.exists():
            try:
                with open(gdelt_file, "r", encoding="utf-8") as f:
                    self.gdelt_pool = json.load(f)
            except Exception as e:
                print(f"[IngestionManager] GDELT load error: {e}")

    def _load_seed_data(self):
        """Loads default seed datasets from news and tweets."""
        news_file = self.data_dir / "financial_news_samples.json"
        tweets_file = self.data_dir / "social_media_tweets.json"

        all_raw_items: List[RawIngestionItem] = []

        if news_file.exists():
            with open(news_file, "r") as f:
                news_data = json.load(f)
                for item in news_data:
                    raw = RawIngestionItem(
                        id=item["id"],
                        source=item["source"],
                        headline_or_title=item.get("headline"),
                        text=item["body"],
                        author_or_handle="Reuters/Bloomberg Desk",
                        timestamp=item.get("timestamp"),
                        target_tickers=item.get("target_tickers", [])
                    )
                    all_raw_items.append(raw)

        if tweets_file.exists():
            with open(tweets_file, "r") as f:
                tweet_data = json.load(f)
                for item in tweet_data:
                    raw = RawIngestionItem(
                        id=item["id"],
                        source=item["source"],
                        headline_or_title=f"Tweet by {item.get('handle', '@Trader')}",
                        text=item["text"],
                        author_or_handle=item.get("handle"),
                        timestamp=item.get("timestamp"),
                        target_tickers=item.get("target_tickers", [])
                    )
                    all_raw_items.append(raw)

        # Ingest a selection of 5 Kaggle Financial PhraseBank and 5 Stock Tweets into initial history
        if self.external_news_pool:
            sample_news = self.external_news_pool[:5]
            for i, n in enumerate(sample_news):
                all_raw_items.append(RawIngestionItem(
                    id=f"kaggle_news_{i+1}",
                    source="Kaggle Financial News (PhraseBank)",
                    headline_or_title="Corporate Financial Bulletin",
                    text=n["text"],
                    author_or_handle="Financial Desk",
                    timestamp="2026-10-08T07:15:00Z"
                ))

        if self.external_tweets_pool:
            sample_tw = self.external_tweets_pool[:5]
            for i, tw in enumerate(sample_tw):
                all_raw_items.append(RawIngestionItem(
                    id=f"kaggle_tweet_{i+1}",
                    source="Twitter/X (FinTwit Stock Tweets)",
                    headline_or_title="Stock Market Alert",
                    text=tw["text"],
                    author_or_handle="@FinTwitTrader",
                    timestamp="2026-10-08T07:45:00Z"
                ))

        # Process and sort seed data chronologically
        for raw in all_raw_items:
            signal = self.analyzer.analyze(raw)
            self.signals_history.append(signal)

        self.signals_history.sort(key=lambda s: s.timestamp)

    def subscribe(self, callback: Callable[[RiskSignal], None]):
        """Register a downstream subscriber callback for real-time signals."""
        self.subscribers.append(callback)

    def ingest_single(self, item: RawIngestionItem) -> RiskSignal:
        signal = self.analyzer.analyze(item)
        self.signals_history.append(signal)
        # Notify subscribers (e.g. Rebalancer and Stress Tester)
        for sub in self.subscribers:
            try:
                sub(signal)
            except Exception as e:
                print(f"[IngestionManager] Subscriber error: {e}")
        return signal

    def ingest_batch(self, items: List[RawIngestionItem]) -> List[RiskSignal]:
        results = []
        for item in items:
            signal = self.ingest_single(item)
            results.append(signal)
        return results

    def get_next_external_stream_item(self, include_gdelt: bool = True) -> RawIngestionItem:
        """Pulls a live-demo item from GDELT first, then local news/social pools."""
        if include_gdelt and self.gdelt_pool:
            record = random.choice(self.gdelt_pool)
            return self._gdelt_record_to_item(record)
        use_tweet = random.choice([True, False])
        if use_tweet and self.external_tweets_pool:
            sample = random.choice(self.external_tweets_pool)
            return RawIngestionItem(
                source="Social Media (Twitter/X FinTwit)",
                headline_or_title="Live Streamed Stock Tweet",
                text=sample["text"],
                author_or_handle="@QuantStream",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        elif self.external_news_pool:
            sample = random.choice(self.external_news_pool)
            return RawIngestionItem(
                source="Financial News (Kaggle / Reuters Wire)",
                headline_or_title="Breaking Corporate Wire",
                text=sample["text"],
                author_or_handle="Reuters Wire",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        else:
            return RawIngestionItem(
                source="Financial News",
                headline_or_title="Market Update",
                text="Federal Reserve keeps benchmark lending rate steady while monitoring labor market indicators.",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

    def _gdelt_record_to_item(self, record: Dict[str, Any]) -> RawIngestionItem:
        themes = record.get("themes", [])
        theme_text = ", ".join(themes[:8]) if isinstance(themes, list) else str(themes)
        url = record.get("url", "")
        return RawIngestionItem(
            id=f"GDELT-{hashlib.sha1(url.encode()).hexdigest()[:10].upper()}",
            source="GDELT 2.0 Global Knowledge Graph",
            headline_or_title=record.get("title") or "GDELT Global Financial Event",
            text=f"GDELT event themes: {theme_text}. Article: {url}",
            author_or_handle=record.get("domain") or "GDELT",
            timestamp=self._gdelt_timestamp(record.get("seendate") or record.get("date"))
        )

    @staticmethod
    def _gdelt_timestamp(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = str(value)
        if len(value) >= 14 and value[:14].isdigit():
            try:
                return datetime.strptime(value[:14], "%Y%m%d%H%M%S").isoformat() + "Z"
            except ValueError:
                pass
        return value

    def poll_live_sources(self) -> Dict[str, Any]:
        """Poll the official GDELT raw 15-minute GKG feed and ingest a fallback item."""
        now = datetime.utcnow().isoformat() + "Z"
        ingested = 0
        gdelt_ingested = 0
        gdelt_status = "ok"
        try:
            records, update_id = self._fetch_latest_gkg_records()
            if update_id == self.last_gkg_update:
                gdelt_status = "cached: waiting_for_next_15_minute_file"
            else:
                self.last_gkg_update = update_id
            for record in records:
                key = record["record_id"]
                if key in self.seen_live_articles:
                    continue
                self.seen_live_articles.add(key)
                self.ingest_single(RawIngestionItem(
                    id=f"GDELT-LIVE-{hashlib.sha1(key.encode()).hexdigest()[:10].upper()}",
                    source="GDELT 2.0 Raw GKG (15-minute feed)",
                    headline_or_title=record["headline"],
                    text=record["text"],
                    author_or_handle=record["source"],
                    timestamp=record["timestamp"] or now
                ))
                ingested += 1
                gdelt_ingested += 1
        except Exception as exc:
            gdelt_status = f"fallback: {type(exc).__name__}"

        # Keep the second source active only when the newest GKG file has no
        # unseen records or the network is unavailable.
        if gdelt_ingested == 0 and (self.external_tweets_pool or self.external_news_pool):
            self.ingest_single(self.get_next_external_stream_item(include_gdelt=False))
            ingested += 1

        self.live_stats.update({
            "last_poll_at": now,
            "last_poll_status": gdelt_status,
            "last_gdelt_articles": gdelt_ingested,
            "gkg_update_id": self.last_gkg_update,
            "live_articles_ingested": self.live_stats["live_articles_ingested"] + ingested
        })
        return dict(self.live_stats)

    def _fetch_latest_gkg_records(self) -> tuple[List[Dict[str, Any]], str]:
        """Download and parse the newest GDELT GKG zip named by lastupdate.txt."""
        manifest = requests.get(
            "https://data.gdeltproject.org/gdeltv2/lastupdate.txt",
            headers={"User-Agent": "SPGlobalRiskEngine/1.0"},
            timeout=15
        )
        manifest.raise_for_status()
        gkg_line = next(line for line in manifest.text.splitlines() if ".gkg.csv.zip" in line)
        parts = gkg_line.split()
        file_url = parts[-1].replace("http://", "https://")
        update_id = Path(file_url).name.split(".")[0]
        if update_id == self.last_gkg_update:
            return [], update_id

        archive = requests.get(
            file_url,
            headers={"User-Agent": "SPGlobalRiskEngine/1.0"},
            timeout=30
        )
        archive.raise_for_status()
        records: List[Dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            with zf.open(zf.namelist()[0]) as raw_file:
                reader = csv.reader(io.TextIOWrapper(raw_file, encoding="utf-8", errors="replace"), delimiter="\t")
                for row in reader:
                    if len(row) < 27:
                        continue
                    themes = row[7] or row[6]
                    if not themes or not any(token in themes.upper() for token in (
                        "ECON_", "BANK", "CREDIT", "STOCK", "MARKET", "FINANCE", "TRADE", "IPO"
                    )):
                        continue
                    theme_excerpt = "; ".join(themes.split(";")[:12])
                    url = row[4]
                    source = row[3] or "GDELT"
                    records.append({
                        "record_id": row[0] or url,
                        "headline": f"GDELT financial coverage: {source}",
                        "text": f"Themes: {theme_excerpt}. Article: {url}. Tone: {row[15]}",
                        "source": source,
                        "timestamp": self._gdelt_timestamp(row[1])
                    })
                    if len(records) >= 25:
                        break
        return records, update_id
    def get_recent_signals(self, limit: int = 50) -> List[RiskSignal]:
        return self.signals_history[-limit:]

    def export_signals_json(self) -> str:
        return json.dumps([s.model_dump() for s in self.signals_history], indent=2)

    def export_signals_csv(self) -> str:
        output = io.StringIO()
        fieldnames = [
            "signal_id", "timestamp", "source_type", "source_name", "headline",
            "primary_entity", "detected_tickers", "sentiment_score", "sentiment_label",
            "event_classification", "impact_score", "severity_tier", "confidence", "rationale"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for s in self.signals_history:
            writer.writerow({
                "signal_id": s.signal_id,
                "timestamp": s.timestamp,
                "source_type": s.source_type,
                "source_name": s.source_name,
                "headline": s.headline or "",
                "primary_entity": s.primary_entity,
                "detected_tickers": ";".join(s.detected_tickers),
                "sentiment_score": s.sentiment_score,
                "sentiment_label": s.sentiment_label,
                "event_classification": s.event_classification,
                "impact_score": s.impact_score,
                "severity_tier": s.severity_tier,
                "confidence": s.confidence,
                "rationale": s.rationale
            })
        return output.getvalue()

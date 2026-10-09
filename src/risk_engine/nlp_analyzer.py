import re
import uuid
from datetime import datetime
from typing import List, Dict, Tuple, Any
from .models import RiskSignal, RawIngestionItem

# Company & Ticker mapping
KNOWN_ENTITIES = {
    "AAPL": ["apple", "iphone", "tim cook", "aapl"],
    "MSFT": ["microsoft", "azure", "satya nadella", "msft", "windows"],
    "NVDA": ["nvidia", "jensen huang", "blackwell", "gpu", "nvda"],
    "AMZN": ["amazon", "aws", "andy jassy", "amzn"],
    "GOOGL": ["alphabet", "google", "sundar pichai", "googl", "goog"],
    "JPM": ["jpmorgan", "jp morgan", "chase", "jamie dimon", "jpm"],
    "BAC": ["bank of america", "bofa", "bac"],
    "XOM": ["exxon", "exxonmobil", "exxon mobil", "xom"],
    "JNJ": ["johnson & johnson", "johnson and johnson", "jnj"],
    "LLY": ["eli lilly", "lilly", "glp-1", "mounjaro", "zepbound", "lly"],
    "TSLA": ["tesla", "elon musk", "robotaxi", "tsla"],
    "BRK.B": ["berkshire", "warren buffett", "brk"],
    "V": ["visa", "v"],
    "PG": ["procter & gamble", "procter and gamble", "pg"],
    "UNH": ["unitedhealth", "united health", "unh"],
    "CFPB": ["cfpb", "consumer financial protection bureau", "consumer watchdog"],
    "SEC": ["sec", "securities and exchange commission"],
    "FDIC": ["fdic", "federal deposit insurance"],
    "MACRO": ["federal reserve", "fomc", "powell", "treasury", "inflation", "cpi", "rate hike", "gdp"]
}

# Positive & Regulatory Easing Domain Terms
POSITIVE_FIN_TERMS = {
    "beat": 1.8, "beats": 1.8, "record": 1.6, "surge": 1.7, "surges": 1.7, "surging": 1.7,
    "breakthrough": 2.0, "approved": 1.8, "approval": 1.8, "growth": 1.2, "outperform": 1.9,
    "upgrade": 1.9, "upgrades": 1.9, "rally": 1.5, "rallies": 1.5, "accretion": 1.5,
    "expansion": 1.4, "resilient": 1.5, "resilience": 1.5, "cleared": 1.6, "soaring": 1.6,
    "bullish": 1.8, "gain": 1.2, "gains": 1.2, "profit": 1.3, "high": 1.0, "higher": 1.1,
    "dividend": 1.3, "boost": 1.4, "accelerated": 1.5, "accelerates": 1.5, "monster": 1.8,
    "monetization": 1.4, "moat": 1.6, "best-in-class": 2.0, "exceed": 1.7, "exceeded": 1.7,
    # Regulatory Easing / Supervision Relief phrases
    "clean bill of health": 2.4, "penalties unlikely": 2.2, "light-touch": 2.0, "expedited review": 1.9,
    "expedited reviews": 1.9, "lenient": 1.8, "deregulation": 2.0, "cut exams": 1.8,
    "back off": 1.6, "minor lapses": 1.5, "little risk": 1.6, "relief": 1.8, "fewer exams": 1.7
}

NEGATIVE_FIN_TERMS = {
    "plunge": 2.0, "plunges": 2.0, "plunging": 2.0, "crash": 2.2, "crashes": 2.2,
    "downgrade": 2.0, "downgrades": 2.0, "downgraded": 2.0, "default": 2.4, "defaults": 2.4,
    "breach": 2.2, "breaches": 2.2, "covenant": 1.8, "delinquency": 1.9, "delinquent": 1.9,
    "recession": 2.0, "inflation": 1.4, "spike": 1.4, "hike": 1.5, "hikes": 1.5,
    "tightening": 1.5, "crisis": 2.2, "curb": 1.4, "fine": 1.6, "penalty": 1.7,
    "investigation": 1.7, "probe": 1.8, "antitrust": 1.6, "drop": 1.3, "drops": 1.3,
    "dropped": 1.3, "loss": 1.4, "losses": 1.5, "slump": 1.7, "crushed": 1.9,
    "subprime": 2.2, "insolvency": 2.4, "freeze": 2.0, "selloff": 1.8, "bearish": 1.8,
    "cut": 1.4, "cuts": 1.4, "guidance cut": 2.0, "disruption": 1.6, "warning": 1.5,
    "warns": 1.5, "throttle": 1.8, "deficit": 1.4, "pressure": 1.3, "depletion": 1.8
}

AMPLIFIERS = {
    "massive": 1.5, "historic": 1.6, "unprecedented": 1.8, "critical": 1.5,
    "severe": 1.7, "huge": 1.4, "emergency": 1.7, "drastic": 1.6, "sharp": 1.4,
    "aggressive": 1.5, "unmitigated": 1.7, "catastrophic": 2.0
}

NEGATIONS = {"not", "no", "never", "without", "hardly", "barely", "fails", "failed"}

# Event Taxonomic Keywords
EVENT_TAXONOMY = {
    "Geopolitical": [
        "geopolitical", "war", "military", "strait of hormuz", "embargo", "sanctions",
        "conflict", "missile", "drone", "blockade", "middle east", "russia", "china tariff",
        "trade war", "shipping lanes", "tanker"
    ],
    "Macroeconomic": [
        "federal reserve", "fomc", "powell", "rate hike", "interest rate", "cpi", "inflation",
        "treasury yield", "yields", "unemployment", "payroll", "gdp", "central bank", "quantitative tightening",
        "multiple compression", "hawkish", "dovish", "macro"
    ],
    "Credit Event": [
        "covenant breach", "downgrade", "junk", "junk status", "default", "credit default swap",
        "cds", "delinquency", "syndicated loan", "refinancing cliff", "non-performing",
        "debt-service", "distress", "subordinated", "insolvency", "rating agency"
    ],
    "Merger & Acquisition": [
        "merger", "acquisition", "buyout", "takeover", "cleared", "antitrust clearance",
        "deal", "divestiture", "tender offer", "consortium", "hostile bid"
    ],
    "Regulatory & Compliance": [
        "regulatory", "antitrust fine", "department of justice", "doj", "sec", "european commission",
        "probe", "penalty", "subpoena", "enforcement", "compliance violation", "monopoly",
        "cfpb", "consumer financial protection", "supervision", "supervisory", "examiner", "examiners",
        "examinations", "light-touch", "expedited review", "expedited reviews", "oversight", "compliance"
    ],
    "Product Launch": [
        "phase 3", "fda", "product launch", "gpu", "blackwell", "contract", "trial results",
        "robotaxi", "efficacy", "patent", "deliveries", "molecule", "unveiled"
    ],
    "Earnings / Financial Distress": [
        "q3 beat", "q4 beat", "earnings", "net interest margin", "guidance", "revenue miss",
        "profit warning", "gross margin", "free cash flow", "operating loss", "restructuring"
    ]
}

class FinancialNLPAnalyzer:
    """
    Unified Financial NLP Engine for sentiment scoring, event classification,
    and market impact estimation.
    """

    def __init__(self):
        pass

    def extract_tickers_and_entities(self, text: str, headline: str = "") -> Tuple[List[str], str]:
        combined = f"{headline} {text}".upper()
        raw_combined = f"{headline} {text}".lower()
        
        tickers = set()
        
        # 1. Regex cash tags like $AAPL, $NVDA
        cash_tags = re.findall(r"\$([A-Z]{1,5})", combined)
        for t in cash_tags:
            if t in KNOWN_ENTITIES or t in ["QQQ", "SPY"]:
                tickers.add(t)

        # 2. Entity lookup
        entity_matches = []
        for ticker, terms in KNOWN_ENTITIES.items():
            for term in terms:
                pattern = r"\b" + re.escape(term) + r"\b"
                if re.search(pattern, raw_combined):
                    if ticker not in ["MACRO", "CFPB", "SEC", "FDIC"]:
                        tickers.add(ticker)
                    entity_matches.append((ticker, term))
                    break

        primary_entity = "General Market"
        if tickers:
            primary_entity = list(tickers)[0]
        elif any(k in raw_combined for k in ["cfpb", "consumer financial protection bureau", "consumer financial protection"]):
            primary_entity = "Consumer Financial Protection Bureau (CFPB)"
        elif any(k in raw_combined for k in ["federal reserve", "fomc", "treasury yield", "interest rate hike", "cpi inflation"]):
            primary_entity = "Federal Reserve / Macro System"
        elif any(k in raw_combined for k in ["bank", "banks", "lending", "financial industry"]):
            primary_entity = "Banking & Consumer Lending Sector"
        elif entity_matches:
            primary_entity = entity_matches[0][0]

        return sorted(list(tickers)), primary_entity

    def calculate_sentiment(self, text: str, headline: str = "") -> Tuple[float, str, float]:
        """
        Calculates sentiment score bounded strictly to [-1.0, 1.0], compressed toward center.
        Returns: (score, label, confidence)
        """
        combined = f"{headline} {text}".lower()
        words = re.findall(r"\b[a-z0-9\-]+\b", combined)
        
        pos_score = 0.0
        neg_score = 0.0

        # Check for regulatory easing / supervision relief context
        reg_relief_cues = [
            "clean bill of health", "expedited review", "expedited reviews", "light-touch",
            "penalties unlikely", "minor lapses", "lenient", "cut exams", "told to back off",
            "unnecessary to escalate", "little risk of harm", "fewer exams", "deregulation"
        ]
        is_regulatory_relief = any(cue in combined for cue in reg_relief_cues)
        if is_regulatory_relief:
            pos_score += 4.5
        
        i = 0
        n = len(words)
        while i < n:
            word = words[i]
            two_gram = f"{words[i]} {words[i+1]}" if i + 1 < n else ""
            three_gram = f"{words[i]} {words[i+1]} {words[i+2]}" if i + 2 < n else ""
            
            # Negation check
            is_negated = False
            for prev_idx in range(max(0, i-2), i):
                if words[prev_idx] in NEGATIONS:
                    is_negated = True
                    break

            amp = 1.0
            if i > 0 and words[i-1] in AMPLIFIERS:
                amp = AMPLIFIERS[words[i-1]]

            matched = False
            # Check 3-gram then 2-gram then 1-gram
            if three_gram in POSITIVE_FIN_TERMS:
                val = POSITIVE_FIN_TERMS[three_gram] * amp
                pos_score += val if not is_negated else val * 0.4
                i += 3
                matched = True
            elif two_gram in POSITIVE_FIN_TERMS:
                val = POSITIVE_FIN_TERMS[two_gram] * amp
                pos_score += val if not is_negated else val * 0.4
                i += 2
                matched = True
            elif two_gram in NEGATIVE_FIN_TERMS:
                val = NEGATIVE_FIN_TERMS[two_gram] * amp
                # In regulatory relief context, discount historical/alleged penalty words
                if is_regulatory_relief and any(k in two_gram for k in ["penalty", "violation", "enforcement"]):
                    val *= 0.15
                neg_score += val if not is_negated else val * 0.4
                i += 2
                matched = True
            
            if not matched:
                if word in POSITIVE_FIN_TERMS:
                    val = POSITIVE_FIN_TERMS[word] * amp
                    pos_score += val if not is_negated else val * 0.4
                elif word in NEGATIVE_FIN_TERMS:
                    val = NEGATIVE_FIN_TERMS[word] * amp
                    if is_regulatory_relief and word in ["violations", "penalties", "abusive", "harassing", "damage", "thuggery", "grim"]:
                        val *= 0.15
                    neg_score += val if not is_negated else val * 0.4
                i += 1

        total = pos_score + neg_score
        if total == 0:
            raw_score = 0.0
            confidence = 0.50
        else:
            diff = (pos_score - neg_score) / (pos_score + neg_score + 1.2)
            # Center-compressed scaling (avoiding extreme -0.9 or +0.9)
            raw_score = diff * 0.60
            confidence = min(0.92, 0.55 + (total * 0.03))

        score = max(-0.75, min(0.75, round(raw_score, 2)))
        
        if score >= 0.30:
            label = "Bullish"
        elif score >= 0.10:
            label = "Mildly Bullish"
        elif score <= -0.30:
            label = "Bearish"
        elif score <= -0.10:
            label = "Mildly Bearish"
        else:
            label = "Neutral"

        return score, label, round(confidence, 2)

    def classify_event(self, text: str, headline: str = "") -> Tuple[str, float]:
        combined = f"{headline} {text}".lower()
        
        scores: Dict[str, float] = {k: 0.0 for k in EVENT_TAXONOMY}
        for category, terms in EVENT_TAXONOMY.items():
            for term in terms:
                pattern = r"\b" + re.escape(term) + r"\b"
                matches = len(re.findall(pattern, combined))
                if matches > 0:
                    weight = 2.0 if term in (headline or "").lower() else 1.0
                    scores[category] += matches * weight

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        
        if best_score == 0:
            return "Macroeconomic", 0.55
            
        conf = min(0.92, 0.55 + (best_score * 0.06))
        return best_category, round(conf, 2)

    def calculate_impact(self, event_class: str, sentiment: float, text: str, tickers: List[str]) -> Tuple[float, str]:
        """
        Calculates predicted severity impact score across the full 1.0 - 10.0 range.
        Returns: (impact_score, severity_tier)
        """
        combined = text.lower()
        
        base_scores = {
            "Geopolitical": 6.0,
            "Credit Event": 5.8,
            "Macroeconomic": 5.6,
            "Regulatory & Compliance": 4.8,
            "Earnings / Financial Distress": 4.7,
            "Product Launch": 4.4,
            "Merger & Acquisition": 4.6
        }
        
        base = base_scores.get(event_class, 4.5)
        polarity_delta = abs(sentiment) * 1.2
        urgency_tokens = ["emergency", "crisis", "breach", "blockade", "default", "war", "sanction", "insolvency"]
        urgency_bonus = min(1.8, sum(0.3 for token in urgency_tokens if token in combined))
        systemic_bonus = 0.5 if not tickers else min(1.0, 0.25 * len(tickers))

        raw_impact = base + polarity_delta + urgency_bonus + systemic_bonus
        impact_score = max(1.0, min(10.0, round(raw_impact, 1)))

        if impact_score >= 8.0:
            tier = "Critical"
        elif impact_score >= 6.5:
            tier = "High"
        elif impact_score >= 4.5:
            tier = "Moderate"
        else:
            tier = "Low"

        return impact_score, tier

    def generate_rationale_and_channels(
        self, event_class: str, sentiment: float, impact: float, tickers: List[str], entity: str
    ) -> Tuple[str, List[str]]:
        ticker_str = ", ".join(tickers) if tickers else entity
        channels = []
        
        if event_class == "Geopolitical":
            channels = ["Energy Supply", "Cross-Asset Volatility"]
            desc = "risk premia repricing" if sentiment < 0 else "supply stability"
            rationale = f"Geopolitical development impacting {ticker_str} via {desc} (Impact {impact}/10)."
        elif event_class == "Macroeconomic":
            channels = ["Yield Curve", "Cost of Capital"]
            desc = "tightening conditions" if sentiment < 0 else "liquidity easing"
            rationale = f"Macroeconomic signal driving {desc} across {ticker_str}."
        elif event_class == "Credit Event":
            channels = ["Default Probability", "Credit Spreads"]
            desc = "balance sheet pressure" if sentiment < 0 else "credit profile improvement"
            rationale = f"Credit alert reflecting {desc} for {ticker_str}."
        elif event_class == "Merger & Acquisition":
            channels = ["Synergy Valuation", "Capital Structure"]
            rationale = f"Corporate M&A activity impacting market concentration for {ticker_str}."
        elif event_class == "Regulatory & Compliance":
            if sentiment >= 0:
                channels = ["Compliance Cost Relief", "Supervisory Leniency", "Lending Flexibility"]
                rationale = f"Supervisory relaxation and expedited reviews reduce compliance costs and penalty risks for {ticker_str}."
            else:
                channels = ["Compliance Capex", "Litigation Reserves", "Supervisory Scrutiny"]
                rationale = f"Regulatory scrutiny increases compliance overhead and oversight for {ticker_str}."
        elif event_class == "Product Launch":
            channels = ["Revenue Trajectory", "Market Share"]
            rationale = f"Commercial product catalyst improving growth prospects for {ticker_str}."
        else:
            channels = ["Operating Margins", "Guidance Consensus"]
            rationale = f"Earnings and operational update for {ticker_str}."

        return rationale, channels

    def analyze(self, item: RawIngestionItem) -> RiskSignal:
        headline = item.headline_or_title or ""
        text = item.text
        
        tickers, primary_entity = self.extract_tickers_and_entities(text, headline)
        if item.target_tickers:
            tickers = sorted(list(set(tickers + item.target_tickers)))
            
        sentiment_score, sentiment_label, sent_conf = self.calculate_sentiment(text, headline)
        event_class, event_conf = self.classify_event(text, headline)
        impact_score, severity_tier = self.calculate_impact(event_class, sentiment_score, f"{headline} {text}", tickers)
        
        combined_conf = round((sent_conf * 0.5) + (event_conf * 0.5), 2)
        rationale, channels = self.generate_rationale_and_channels(
            event_class, sentiment_score, impact_score, tickers, primary_entity
        )
        
        source_type = "Social Media (Twitter/X)" if ("tweet" in item.source.lower() or "twit" in item.source.lower() or "social" in item.source.lower()) else "Financial News"
        
        return RiskSignal(
            signal_id=item.id or f"SIG-{uuid.uuid4().hex[:8].upper()}",
            timestamp=item.timestamp or datetime.utcnow().isoformat() + "Z",
            source_type=source_type,
            source_name=item.source,
            raw_text=text,
            headline=headline if headline else None,
            primary_entity=primary_entity,
            detected_tickers=tickers,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            event_classification=event_class,
            impact_score=impact_score,
            severity_tier=severity_tier,
            confidence=combined_conf,
            rationale=rationale,
            transmission_channels=channels,
            metadata={
                "author_or_handle": item.author_or_handle,
                "token_count": len(text.split())
            }
        )

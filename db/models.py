from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class City(Base):
    __tablename__ = "cities"
    
    city_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    country = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    climate_type = Column(String)
    active = Column(Boolean, default=True)

    snapshots = relationship("WeatherSnapshot", back_populates="city", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="city")

class WeatherSnapshot(Base):
    __tablename__ = "weather_snapshots"
    
    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    city_id = Column(Integer, ForeignKey("cities.city_id"), nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String, nullable=False)  # "apify", "open-meteo", "wttr.in", "mock"
    temperature = Column(Float)  # Celsius
    precip_prob = Column(Float)   # [0, 1]
    wind_speed = Column(Float)    # km/h
    raw_json = Column(Text)       # Full payload for debugging

    city = relationship("City", back_populates="snapshots")

class PolymarketMarket(Base):
    __tablename__ = "polymarket_markets"
    
    market_id = Column(String, primary_key=True)  # unique Polymarket token or ID
    question = Column(String, nullable=False)
    city_ref = Column(String, nullable=False)  # Name of city this refers to (e.g. "New York City")
    outcome_yes_price = Column(Float, nullable=False)  # odds in [0, 1]
    outcome_no_price = Column(Float, nullable=False)   # odds in [0, 1]
    volume = Column(Float, default=0.0)
    end_time = Column(DateTime, nullable=False)
    status = Column(Enum("open", "resolved", "cancelled", name="market_status_enum"), default="open")
    resolution_source = Column(String)  # E.g. "temp > 85F" or "rain > 0.1in"

    predictions = relationship("Prediction", back_populates="market")

class Prediction(Base):
    __tablename__ = "predictions"
    
    pred_id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, ForeignKey("polymarket_markets.market_id"), nullable=False)
    city_id = Column(Integer, ForeignKey("cities.city_id"), nullable=False)
    p_model = Column(Float, nullable=False)      # calculated probability [0, 1]
    p_implied = Column(Float, nullable=False)    # market implied probability
    confidence = Column(Float, nullable=False)   # LLM confidence [0, 1]
    ev = Column(Float, nullable=False)           # expected value
    created_at = Column(DateTime, default=datetime.utcnow)
    llm_reasoning = Column(Text)

    city = relationship("City", back_populates="predictions")
    market = relationship("PolymarketMarket", back_populates="predictions")
    trades = relationship("PaperTrade", back_populates="prediction")

class PaperTrade(Base):
    __tablename__ = "paper_trades"
    
    trade_id = Column(Integer, primary_key=True, autoincrement=True)
    pred_id = Column(Integer, ForeignKey("predictions.pred_id"), nullable=False)
    side = Column(Enum("YES", "NO", name="trade_side_enum"), nullable=False)
    stake = Column(Float, nullable=False)
    odds = Column(Float, nullable=False)  # Decimal or implied price (e.g. 0.55 if contract is $0.55)
    created_at = Column(DateTime, default=datetime.utcnow)
    hedge_of = Column(Integer, ForeignKey("paper_trades.trade_id"), nullable=True)
    status = Column(Enum("open", "resolved", "cancelled", name="trade_status_enum"), default="open")

    prediction = relationship("Prediction", back_populates="trades")
    results = relationship("TradeResult", back_populates="trade")

class TradeResult(Base):
    __tablename__ = "trade_results"
    
    result_id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("paper_trades.trade_id"), nullable=False)
    outcome = Column(Enum("win", "loss", "refund", name="trade_outcome_enum"), nullable=False)
    pnl = Column(Float, nullable=False)
    resolved_at = Column(DateTime, default=datetime.utcnow)
    accuracy_flag = Column(Boolean, nullable=False)  # True if predicted outcome matched final resolved side

    trade = relationship("PaperTrade", back_populates="results")

class AgentLog(Base):
    __tablename__ = "agent_logs"
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)  # UUID or run identifier
    step = Column(String, nullable=False)    # e.g., "OBSERVE", "FETCH", "REASON", "SIZE"
    tool_name = Column(String)
    input_summary = Column(Text)
    output_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Bankroll(Base):
    __tablename__ = "bankroll"
    
    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    balance = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    reason = Column(String, nullable=False)  # e.g., "INITIAL", "TRADE Stake", "TRADE Resolution", "HEDGE Stake"

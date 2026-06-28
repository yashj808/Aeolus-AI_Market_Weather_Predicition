import uuid
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, INITIAL_BANKROLL
from db.models import Base, City, WeatherSnapshot, PolymarketMarket, Prediction, PaperTrade, TradeResult, AgentLog, Bankroll

# Enable write-ahead logging (WAL) for SQLite to prevent lock issues
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False, "timeout": 30}
)

# Apply WAL mode on SQLite engines
if DATABASE_URL.startswith("sqlite"):
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    from sqlalchemy import event
    event.listen(engine, "connect", set_sqlite_pragma)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# ----------------- BANKROLL HELPERS -----------------

def get_current_bankroll(session) -> float:
    latest = session.query(Bankroll).order_by(desc(Bankroll.timestamp)).first()
    if latest is None:
        # Initialize
        init_bankroll = Bankroll(balance=INITIAL_BANKROLL, timestamp=datetime.utcnow(), reason="INITIAL")
        session.add(init_bankroll)
        session.commit()
        return INITIAL_BANKROLL
    return latest.balance

def update_bankroll(session, amount: float, reason: str) -> float:
    current = get_current_bankroll(session)
    new_balance = current + amount
    # Keep bankroll >= 0
    if new_balance < 0:
        new_balance = 0.0
    snapshot = Bankroll(balance=new_balance, timestamp=datetime.utcnow(), reason=reason)
    session.add(snapshot)
    session.commit()
    return new_balance

# ----------------- CITY HELPERS -----------------

def get_active_cities(session):
    return session.query(City).filter(City.active == True).all()

# ----------------- SNAPSHOT HELPERS -----------------

def add_weather_snapshot(session, city_id: int, source: str, temp: float, precip_prob: float, wind: float, raw_json: str):
    snapshot = WeatherSnapshot(
        city_id=city_id,
        source=source,
        temperature=temp,
        precip_prob=precip_prob,
        wind_speed=wind,
        raw_json=raw_json,
        fetched_at=datetime.utcnow()
    )
    session.add(snapshot)
    session.commit()
    return snapshot

# ----------------- MARKET HELPERS -----------------

def get_open_markets(session):
    return session.query(PolymarketMarket).filter(PolymarketMarket.status == "open").all()

def add_polymarket_market(session, market_id: str, question: str, city_ref: str, yes_price: float, no_price: float, volume: float, end_time: datetime, resolution_source: str):
    market = session.query(PolymarketMarket).filter(PolymarketMarket.market_id == market_id).first()
    if market:
        market.outcome_yes_price = yes_price
        market.outcome_no_price = no_price
        market.volume = volume
        market.end_time = end_time
        market.resolution_source = resolution_source
    else:
        market = PolymarketMarket(
            market_id=market_id,
            question=question,
            city_ref=city_ref,
            outcome_yes_price=yes_price,
            outcome_no_price=no_price,
            volume=volume,
            end_time=end_time,
            status="open",
            resolution_source=resolution_source
        )
        session.add(market)
    session.commit()
    return market

# ----------------- PREDICTIONS & TRADES -----------------

def add_prediction(session, market_id: str, city_id: int, p_model: float, p_implied: float, confidence: float, ev: float, reasoning: str):
    pred = Prediction(
        market_id=market_id,
        city_id=city_id,
        p_model=p_model,
        p_implied=p_implied,
        confidence=confidence,
        ev=ev,
        llm_reasoning=reasoning,
        created_at=datetime.utcnow()
    )
    session.add(pred)
    session.commit()
    return pred

def place_paper_order(session, pred_id: int, side: str, stake: float, odds: float, hedge_of: int = None):
    # Lock stake from bankroll
    update_bankroll(session, -stake, f"STAKE FOR {side} on PRED {pred_id}")
    
    trade = PaperTrade(
        pred_id=pred_id,
        side=side,
        stake=stake,
        odds=odds,
        hedge_of=hedge_of,
        status="open",
        created_at=datetime.utcnow()
    )
    session.add(trade)
    session.commit()
    return trade

def get_open_positions(session):
    return session.query(PaperTrade).filter(PaperTrade.status == "open").all()

# ----------------- HEDGE ENGINE HELPERS -----------------

def get_city_open_positions_count(session, city_id: int) -> int:
    return session.query(PaperTrade)\
        .join(Prediction)\
        .filter(Prediction.city_id == city_id, PaperTrade.status == "open")\
        .count()

# ----------------- RESOLUTION HELPER -----------------

def resolve_market_in_db(session, market_id: str, actual_outcome: str):
    """
    actual_outcome: 'YES' or 'NO'
    Marks market as resolved. Computes P&L for all open trades associated with this market.
    """
    market = session.query(PolymarketMarket).filter(PolymarketMarket.market_id == market_id).first()
    if not market or market.status != "open":
        return None
    
    market.status = "resolved"
    
    # Get all open trades associated with this market
    trades = session.query(PaperTrade)\
        .join(Prediction)\
        .filter(Prediction.market_id == market_id, PaperTrade.status == "open")\
        .all()
    
    resolved_trades = []
    
    for trade in trades:
        trade.status = "resolved"
        
        # Calculate payout
        # If contract won: payout is stake / purchase_price.
        # Polymarket outcome price represents the contract cost (e.g. YES at $0.60, winning YES pays out $1.00).
        # Win payout ratio: 1.0 / purchase_price.
        # Profit = payout - stake.
        # Loss P&L = -stake (already deducted, so we add 0 payout).
        win = (trade.side == actual_outcome)
        
        if win:
            # Entry odds represent the price per contract. If odds is 0.60, win pays $1.00.
            payout = trade.stake / trade.odds if trade.odds > 0 else 0
            pnl = payout - trade.stake
            outcome_status = "win"
            # Add payout to bankroll
            update_bankroll(session, payout, f"WIN PAYOUT FOR TRADE {trade.trade_id}")
        else:
            pnl = -trade.stake
            outcome_status = "loss"
            # No bankroll addition, since stake is already deducted on order entry
        
        # Determine if prediction was correct
        # Accuracy is True if the predicted side (with EV > 0, which corresponds to the side we bought) won
        accuracy_flag = win
        
        result = TradeResult(
            trade_id=trade.trade_id,
            outcome=outcome_status,
            pnl=pnl,
            resolved_at=datetime.utcnow(),
            accuracy_flag=accuracy_flag
        )
        session.add(result)
        resolved_trades.append({
            "trade_id": trade.trade_id,
            "pnl": pnl,
            "outcome": outcome_status,
            "accuracy": accuracy_flag
        })
        
    session.commit()
    return resolved_trades

# ----------------- AGENT LOGS HELPERS -----------------

def log_agent_step(session, run_id: str, step: str, tool_name: str, input_summary: str, output_summary: str):
    log = AgentLog(
        run_id=run_id,
        step=step,
        tool_name=tool_name,
        input_summary=input_summary,
        output_summary=output_summary,
        created_at=datetime.utcnow()
    )
    session.add(log)
    session.commit()
    return log

def get_agent_logs(session, limit: int = 50):
    return session.query(AgentLog).order_by(desc(AgentLog.created_at)).limit(limit).all()

# ----------------- STATS HELPER -----------------

def get_portfolio_stats(session):
    # Total trades
    total_trades = session.query(PaperTrade).count()
    resolved_trades = session.query(PaperTrade).filter(PaperTrade.status == "resolved").count()
    active_trades = session.query(PaperTrade).filter(PaperTrade.status == "open").count()
    
    # Wins
    wins = session.query(TradeResult).filter(TradeResult.outcome == "win").count()
    win_rate = (wins / resolved_trades) if resolved_trades > 0 else 0.0
    
    # P&L
    total_pnl = session.query(func.sum(TradeResult.pnl)).scalar() or 0.0
    
    # Average EV
    avg_ev = session.query(func.avg(Prediction.ev))\
        .join(PaperTrade)\
        .scalar() or 0.0
        
    # Drawdown calculation
    bankroll_history = session.query(Bankroll.balance).order_by(Bankroll.timestamp).all()
    balances = [b[0] for b in bankroll_history]
    
    max_dd = 0.0
    if len(balances) > 0:
        peak = balances[0]
        for b in balances:
            if b > peak:
                peak = b
            if peak > 0:
                dd = (peak - b) / peak
                if dd > max_dd:
                    max_dd = dd
                    
    # Sharpe-like ratio: Mean daily returns / Std daily returns (simplified to per-trade returns)
    results = session.query(TradeResult.pnl).all()
    pnls = [r[0] for r in results]
    sharpe = 0.0
    if len(pnls) > 1:
        import numpy as np
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        if std_pnl > 0:
            sharpe = (mean_pnl / std_pnl) * np.sqrt(252) # Scaled standard Sharpe
            
    return {
        "total_trades": total_trades,
        "resolved_trades": resolved_trades,
        "active_trades": active_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_ev": avg_ev,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe
    }

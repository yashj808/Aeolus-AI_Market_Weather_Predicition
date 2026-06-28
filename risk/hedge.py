import structlog
from typing import Dict, Any, List, Optional
from config import MAX_CORR_POS, MAX_OPEN_POSITIONS, KELLY_FRACTION
from db.models import PaperTrade, Prediction, PolymarketMarket
from db.queries import get_open_positions, get_city_open_positions_count, place_paper_order

logger = structlog.get_logger()

def can_trade_city(session, city_id: int) -> bool:
    """Checks if we are within the correlation limits for the given city and portfolio."""
    # 1. Total portfolio check
    total_open = session.query(PaperTrade).filter(PaperTrade.status == "open").count()
    if total_open >= MAX_OPEN_POSITIONS:
        logger.warn("Trade blocked: Maximum open positions reached", total_open=total_open)
        return False
        
    # 2. City correlation check
    city_open = get_city_open_positions_count(session, city_id)
    if city_open >= MAX_CORR_POS:
        logger.warn("Trade blocked: City-specific correlation limit reached", city_id=city_id, open_in_city=city_open)
        return False
        
    return True

def compute_hedges(
    session,
    active_markets: List[Dict[str, Any]],
    forecast_probabilities: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Evaluates existing open positions and determines if counter-trades are needed.
    
    Conditions:
    - If a YES position's probability (P_model) falls below (1 - current_price) * 0.9, place a NO hedge.
    - If a NO position's probability (P_model) rises above (1 - current_price) * 1.1, place a YES hedge.
    - Hedge stake size is 30% of the original stake.
    
    Returns a list of trade recommendations to execute.
    """
    open_trades = get_open_positions(session)
    hedge_recommendations = []
    
    # Map market_id to current odds/prices from Polymarket
    market_price_map = {m["market_id"]: m for m in active_markets}
    
    for trade in open_trades:
        # Avoid recursive hedging
        if trade.hedge_of is not None:
            continue
            
        pred = trade.prediction
        market_id = pred.market_id
        
        # We need the current price and model probability for this market
        if market_id not in market_price_map or market_id not in forecast_probabilities:
            continue
            
        market_info = market_price_map[market_id]
        p_model = forecast_probabilities[market_id]
        
        # Current odds/price of the side we bought
        current_yes_price = market_info["outcome_yes_price"]
        current_no_price = market_info["outcome_no_price"]
        
        hedge_triggered = False
        hedge_side = None
        hedge_odds = None
        
        if trade.side == "YES":
            # If P_model drops below (1 - current_yes_price) * 0.9 (which is current_no_price * 0.9)
            threshold = (1.0 - current_yes_price) * 0.9
            if p_model < threshold:
                hedge_triggered = True
                hedge_side = "NO"
                hedge_odds = current_no_price
                reason = f"YES prediction P_model ({p_model:.2f}) dropped below threshold ({threshold:.2f})"
        else:  # trade.side == "NO"
            # If P_model rises above (1 - current_no_price) * 1.1 (which is current_yes_price * 1.1)
            threshold = (1.0 - current_no_price) * 1.1
            if p_model > threshold:
                hedge_triggered = True
                hedge_side = "YES"
                hedge_odds = current_yes_price
                reason = f"NO prediction P_model ({p_model:.2f}) rose above threshold ({threshold:.2f})"
                
        if hedge_triggered:
            # Check if we already have an active hedge for this trade to prevent duplicates
            existing_hedge = session.query(PaperTrade).filter(
                PaperTrade.hedge_of == trade.trade_id,
                PaperTrade.status == "open"
            ).first()
            
            if not existing_hedge:
                # Sized at 30% of parent stake
                hedge_stake = round(trade.stake * 0.30, 2)
                
                logger.info(
                    "Hedge trade recommended",
                    parent_trade_id=trade.trade_id,
                    side=hedge_side,
                    stake=hedge_stake,
                    odds=hedge_odds,
                    reason=reason
                )
                
                hedge_recommendations.append({
                    "pred_id": pred.pred_id,
                    "side": hedge_side,
                    "stake": hedge_stake,
                    "odds": hedge_odds,
                    "hedge_of": trade.trade_id,
                    "reason": reason
                })
                
    return hedge_recommendations

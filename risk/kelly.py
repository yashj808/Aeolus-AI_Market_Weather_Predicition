import structlog
from typing import Dict, Any, Tuple
from config import KELLY_FRACTION, MAX_BET_PCT, MIN_EV_THRESHOLD, MIN_CONFIDENCE

logger = structlog.get_logger()

def compute_kelly_stake(
    p_model: float,
    price: float,
    confidence: float,
    bankroll: float
) -> Tuple[float, str]:
    """
    Computes the optimal stake size based on the fractional Kelly Criterion:
    f* = (p - price) / (1 - price)
    
    Returns:
        (stake_amount, reason)
    """
    # 1. Verification of inputs
    if bankroll <= 0:
        return 0.0, "Bankroll is zero or negative"
        
    if confidence < MIN_CONFIDENCE:
        return 0.0, f"Confidence {confidence:.2f} is below minimum threshold of {MIN_CONFIDENCE:.2f}"

    if price <= 0 or price >= 1.0:
        return 0.0, f"Invalid contract price: {price}"

    # 2. Expected Value (EV) calculation
    # EV = P(win) * PayoutRatio - 1 = p_model * (1.0 / price) - 1.0
    ev = (p_model / price) - 1.0
    
    if ev < MIN_EV_THRESHOLD:
        return 0.0, f"Expected Value {ev:.1%} is below minimum threshold of {MIN_EV_THRESHOLD:.1%}"

    # 3. Kelly Stake Sizing
    # f* = (p - price) / (1 - price)
    f_star = (p_model - price) / (1.0 - price)
    
    if f_star <= 0:
        return 0.0, f"Kelly formula returned negative stake fraction: {f_star:.3f} (No Edge)"
        
    # Apply Kelly fraction (e.g. half-Kelly)
    f_fractional = f_star * KELLY_FRACTION
    
    # Apply MAX_BET_PCT cap (e.g. 5% of bankroll)
    f_final = min(f_fractional, MAX_BET_PCT)
    
    stake = bankroll * f_final
    
    logger.info(
        "Kelly calculation completed",
        p_model=round(p_model, 3),
        price=round(price, 3),
        ev=round(ev, 3),
        f_star=round(f_star, 3),
        f_fractional=round(f_fractional, 3),
        f_final=round(f_final, 3),
        stake=round(stake, 2),
        bankroll=round(bankroll, 2)
    )
    
    return round(stake, 2), "APPROVED"

import json
import scipy.stats as stats
import structlog
from typing import Dict, Any, Optional
from db.models import WeatherSnapshot, TradeResult, Prediction
from data.normalizer import UnifiedWeatherData

logger = structlog.get_logger()

def compute_forecast_probability(
    session,
    city_id: int,
    city_name: str,
    resolution_source: str,
    target_date_str: str,  # YYYY-MM-DD
    weather_data: UnifiedWeatherData,
    p_llm: float,
    w_nwp: float = 0.5,
    w_hist: float = 0.3,
    w_llm: float = 0.2
) -> float:
    """
    Ensemble model:
    P_model = w_nwp * P_nwp + w_hist * P_hist + w_llm * P_llm
    
    resolution_source defines the event rule, e.g. "precip > 0.0" or "temp > 35.0".
    """
    # 1. Compute P_nwp (Numerical Weather Prediction)
    p_nwp = _compute_nwp_probability(weather_data, resolution_source, target_date_str)
    
    # 2. Compute P_hist (Historical Baseline)
    p_hist = _compute_historical_probability(session, city_id, resolution_source)
    
    # 3. Ensemble
    p_raw = (w_nwp * p_nwp) + (w_hist * p_hist) + (w_llm * p_llm)
    p_raw = max(0.0, min(1.0, p_raw))
    
    # 4. Calibration
    p_calibrated = calibrate_probability(session, p_raw)
    
    logger.info(
        "Ensemble probability computed",
        city=city_name,
        rule=resolution_source,
        p_nwp=round(p_nwp, 3),
        p_hist=round(p_hist, 3),
        p_llm=round(p_llm, 3),
        p_raw=round(p_raw, 3),
        p_calibrated=round(p_calibrated, 3)
    )
    
    return p_calibrated

def _compute_nwp_probability(weather_data: UnifiedWeatherData, resolution_source: str, target_date_str: str) -> float:
    """Extracts P_nwp from forecasted daily parameters."""
    # Find forecast day matching the target date
    target_forecast = None
    for day in weather_data.daily_forecasts:
        if day.date == target_date_str:
            target_forecast = day
            break
            
    if not target_forecast:
        # Default fallback to the first forecast day
        if len(weather_data.daily_forecasts) > 0:
            target_forecast = weather_data.daily_forecasts[0]
        else:
            # Absolute fallback if no forecasts available
            return 0.5

    rule = resolution_source.lower()
    
    if "precip" in rule or "rain" in rule:
        # For precipitation, we directly use precipitation probability max
        return target_forecast.precip_prob
        
    elif "temp" in rule:
        # Parse threshold temp
        # Format usually is "temp > 40.0" or "temp > 28.5"
        try:
            parts = rule.split(">")
            threshold = float(parts[1].strip())
        except Exception:
            threshold = 30.0  # default
            
        # Treat temp_max as mean of temperature, with standard deviation 2.0C
        # P(temp > threshold) = 1 - cdf(threshold)
        mean_temp = target_forecast.temp_max
        std_temp = 2.0
        
        # Survival function (1 - CDF)
        p_exceed = float(stats.norm.sf(threshold, loc=mean_temp, scale=std_temp))
        return p_exceed
        
    elif "wind" in rule:
        try:
            parts = rule.split(">")
            threshold = float(parts[1].strip())
        except Exception:
            threshold = 25.0
            
        # Wind speeds modeled with a Weibull or lognormal dist, but normal sf is sufficient
        mean_wind = target_forecast.wind_speed
        std_wind = 5.0
        return float(stats.norm.sf(threshold, loc=mean_wind, scale=std_wind))
        
    return 0.5

def _compute_historical_probability(session, city_id: int, resolution_source: str) -> float:
    """Calculates historical base rate of the event from snapshots in DB."""
    snapshots = session.query(WeatherSnapshot).filter(WeatherSnapshot.city_id == city_id).all()
    if not snapshots:
        return 0.3  # Default flat prior if no history is seeded
        
    matching_count = 0
    rule = resolution_source.lower()
    
    for snap in snapshots:
        # Load raw json to verify historical properties
        try:
            raw_data = json.loads(snap.raw_json)
        except Exception:
            raw_data = {}
            
        if "precip" in rule or "rain" in rule:
            # Let's say a day is rainy if precip_prob > 0.4 or temperature has precip
            precip = snap.precip_prob or raw_data.get("precipitation_probability", 0.0)
            if precip > 0.4:
                matching_count += 1
                
        elif "temp" in rule:
            try:
                threshold = float(rule.split(">")[1].strip())
            except Exception:
                threshold = 30.0
            temp = snap.temperature or raw_data.get("temperature", 20.0)
            if temp > threshold:
                matching_count += 1
                
        elif "wind" in rule:
            try:
                threshold = float(rule.split(">")[1].strip())
            except Exception:
                threshold = 25.0
            wind = snap.wind_speed or raw_data.get("wind_speed", 10.0)
            if wind > threshold:
                matching_count += 1
                
    return matching_count / len(snapshots)

def calibrate_probability(session, raw_prob: float) -> float:
    """
    Applies isotonic calibration using resolved trades history.
    If sample size is small (< 10 resolved trades), returns raw probability.
    """
    resolved_trades_count = session.query(TradeResult).count()
    if resolved_trades_count < 10:
        return raw_prob
        
    # Get last 50 predictions and their actual resolution
    past_predictions = session.query(Prediction.p_model, TradeResult.outcome)\
        .join(Prediction.trades)\
        .join(PaperTrade.results)\
        .order_by(Prediction.created_at.desc())\
        .limit(50)\
        .all()
        
    # Standard calibration mapping: bin predictions into buckets and calculate win ratios
    # Let's do simple linear calibration scaling:
    # y = a * x + b
    wins_list = [1.0 if r[1] == "win" else 0.0 for r in past_predictions]
    probs_list = [r[0] for r in past_predictions]
    
    try:
        import numpy as np
        slope, intercept, r_value, p_value, std_err = stats.linregress(probs_list, wins_list)
        # Apply calibration if the regression is reasonably stable
        if not np.isnan(slope) and 0.5 < slope < 2.0:
            calibrated = slope * raw_prob + intercept
            return max(0.0, min(1.0, calibrated))
    except Exception as e:
        logger.error("Error during probability calibration linear regression", error=str(e))
        
    return raw_prob

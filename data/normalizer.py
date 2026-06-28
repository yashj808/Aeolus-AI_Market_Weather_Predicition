from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class DailyForecast(BaseModel):
    date: str  # YYYY-MM-DD
    temp_max: float
    temp_min: float
    precip_prob: float  # [0, 1]
    wind_speed: float   # km/h
    humidity: Optional[float] = None
    description: Optional[str] = ""

class UnifiedWeatherData(BaseModel):
    city_name: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    source: str
    temperature: float  # Current temp in C
    precip_prob: float  # Current precipitation prob in [0, 1]
    wind_speed: float   # Current wind speed in km/h
    humidity: float     # Relative humidity %
    daily_forecasts: List[DailyForecast] = []

def normalize_apify(city_name: str, data: Dict[str, Any]) -> UnifiedWeatherData:
    """Normalizes the raw JSON response from apify/weather-api."""
    # Apify weather-api returns structured weather info.
    # We will build resilience here in case fields are nested or slightly different.
    current = data.get("current", {})
    temp = current.get("temp_c", current.get("temp", 20.0))
    precip_prob = current.get("precip_prob", current.get("precip_probability", 0.0))
    if precip_prob > 1.0:
        precip_prob = precip_prob / 100.0  # normalize percent to [0,1]
    wind = current.get("wind_kph", current.get("wind_speed", 10.0))
    humidity = current.get("humidity", 50.0)

    # Daily forecast list parsing
    daily_list = []
    forecast = data.get("forecast", {}).get("forecastday", [])
    for day in forecast:
        day_info = day.get("day", {})
        precip_d = day_info.get("daily_chance_of_rain", day_info.get("precip_prob", 0.0))
        if precip_d > 1.0:
            precip_d = precip_d / 100.0
            
        daily_list.append(DailyForecast(
            date=day.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            temp_max=day_info.get("maxtemp_c", temp),
            temp_min=day_info.get("mintemp_c", temp),
            precip_prob=precip_d,
            wind_speed=day_info.get("maxwind_kph", wind)
        ))

    return UnifiedWeatherData(
        city_name=city_name,
        source="apify",
        temperature=temp,
        precip_prob=precip_prob,
        wind_speed=wind,
        humidity=humidity,
        daily_forecasts=daily_list
    )

def normalize_openmeteo(city_name: str, data: Dict[str, Any]) -> UnifiedWeatherData:
    """Normalizes the raw JSON response from Open-Meteo API."""
    current = data.get("current", {})
    daily = data.get("daily", {})
    
    temp = current.get("temperature_2m", 20.0)
    # Open-Meteo current doesn't always have precip_probability directly, we can read relative_humidity or use the daily tomorrow value
    humidity = current.get("relative_humidity_2m", 50.0)
    wind = current.get("wind_speed_10m", 10.0)
    
    # Parse daily forecasts
    daily_list = []
    times = daily.get("time", [])
    temp_maxs = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])
    precip_probs = daily.get("precipitation_probability_max", [])
    wind_speeds = daily.get("wind_speed_10m_max", [])
    
    for i in range(len(times)):
        p_prob = (precip_probs[i] / 100.0) if i < len(precip_probs) else 0.0
        daily_list.append(DailyForecast(
            date=times[i],
            temp_max=temp_maxs[i] if i < len(temp_maxs) else temp,
            temp_min=temp_mins[i] if i < len(temp_mins) else temp,
            precip_prob=p_prob,
            wind_speed=wind_speeds[i] if i < len(wind_speeds) else wind
        ))

    # Assume current precip prob is the first day's precip prob max
    curr_precip = daily_list[0].precip_prob if len(daily_list) > 0 else 0.0

    return UnifiedWeatherData(
        city_name=city_name,
        source="open-meteo",
        temperature=temp,
        precip_prob=curr_precip,
        wind_speed=wind,
        humidity=humidity,
        daily_forecasts=daily_list
    )

def normalize_wttrin(city_name: str, data: Dict[str, Any]) -> UnifiedWeatherData:
    """Normalizes the raw JSON response from wttr.in."""
    # wttr.in returns standard JSON layout when called with format=j1
    current = data.get("current_condition", [{}])[0]
    temp = float(current.get("temp_C", 20.0))
    humidity = float(current.get("humidity", 50.0))
    wind = float(current.get("windspeedKmph", 10.0))
    
    # wttr.in forecast days
    daily_list = []
    weather = data.get("weather", [])
    for w in weather:
        # chanceofrain in wttr.in is nested inside hourly
        hourly = w.get("hourly", [{}])
        # Average the rain chance across hourly slices
        rain_chances = [float(h.get("chanceofrain", 0.0)) for h in hourly]
        avg_rain_chance = (sum(rain_chances) / len(rain_chances)) / 100.0 if rain_chances else 0.0
        
        daily_list.append(DailyForecast(
            date=w.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            temp_max=float(w.get("maxtempC", temp)),
            temp_min=float(w.get("mintempC", temp)),
            precip_prob=avg_rain_chance,
            wind_speed=float(hourly[0].get("windspeedKmph", wind)) if hourly else wind
        ))
        
    curr_precip = daily_list[0].precip_prob if len(daily_list) > 0 else 0.0

    return UnifiedWeatherData(
        city_name=city_name,
        source="wttr.in",
        temperature=temp,
        precip_prob=curr_precip,
        wind_speed=wind,
        humidity=humidity,
        daily_forecasts=daily_list
    )

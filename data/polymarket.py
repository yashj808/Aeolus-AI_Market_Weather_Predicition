import httpx
import random
import structlog
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from config import MIN_VOLUME_USD, MOCK_MODE, POLYMARKET_GAMMA_URL
from db.queries import add_polymarket_market

logger = structlog.get_logger()

async def fetch_open_weather_markets(session) -> List[Dict[str, Any]]:
    """
    Fetches open weather markets from Polymarket Gamma API.
    If in mock mode, or if no weather markets are found, dynamically creates mock markets.
    """
    markets = []
    
    if not MOCK_MODE:
        try:
            logger.info("Fetching live weather markets from Polymarket Gamma API")
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Query Polymarket Gamma API for active weather markets
                # Category tags can vary, so searching for "weather" query is robust
                url = f"{POLYMARKET_GAMMA_URL}/markets"
                params = {
                    "active": "true",
                    "closed": "false",
                    "limit": 100,
                    "query": "weather"
                }
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    raw_markets = response.json()
                    logger.info(f"Polymarket API returned {len(raw_markets)} search results")
                    for m in raw_markets:
                        # Extract price for YES/NO contract.
                        # outcomePrices are usually [YES_price, NO_price] in string decimal.
                        prices = m.get("outcomePrices", [])
                        volume = float(m.get("volume", 0.0))
                        
                        # Apply minimum volume filter
                        if volume < MIN_VOLUME_USD:
                            continue
                            
                        if len(prices) >= 2:
                            try:
                                yes_price = float(prices[0])
                                no_price = float(prices[1])
                            except ValueError:
                                yes_price = 0.50
                                no_price = 0.50
                        else:
                            # Fallback if no prices list
                            yes_price = 0.50
                            no_price = 0.50
                            
                        # Parse end time
                        end_date_str = m.get("endDate", m.get("end_time"))
                        if end_date_str:
                            try:
                                # Standard isoformat parse
                                end_time = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                            except ValueError:
                                end_time = datetime.utcnow() + timedelta(days=2)
                        else:
                            end_time = datetime.utcnow() + timedelta(days=2)

                        # Match city
                        question = m.get("question", "")
                        city_ref = _match_city_from_question(question)
                        
                        if city_ref:
                            market_id = m.get("id", f"poly_{city_ref.lower().replace(' ', '_')}_{int(end_time.timestamp())}")
                            
                            # Parse expected resolution rule (simple rule parsing for mock engine validation)
                            resolution_source = "temp > 40.0" if "40" in question else "precip > 0.0"
                            
                            parsed_market = {
                                "market_id": market_id,
                                "question": question,
                                "city_ref": city_ref,
                                "outcome_yes_price": yes_price,
                                "outcome_no_price": no_price,
                                "volume": volume,
                                "end_time": end_time,
                                "resolution_source": resolution_source
                            }
                            
                            # Add to database
                            add_polymarket_market(
                                session,
                                market_id=market_id,
                                question=question,
                                city_ref=city_ref,
                                yes_price=yes_price,
                                no_price=no_price,
                                volume=volume,
                                end_time=end_time,
                                resolution_source=resolution_source
                            )
                            markets.append(parsed_market)
                else:
                    logger.warn("Polymarket Gamma API returned non-200", status_code=response.status_code)
        except Exception as e:
            logger.warn("Exception fetching Polymarket weather markets", error=str(e))

    # If mock mode is enabled or no markets were loaded, seed/refresh dynamic mock markets
    if len(markets) == 0:
        logger.info("No live markets matched or Mock Mode active. Generating dynamic mock markets.")
        markets = _generate_dynamic_mock_markets(session)
        
    return markets

def _match_city_from_question(question: str) -> Optional[str]:
    """Matches the question string to one of our target cities."""
    q_lower = question.lower()
    cities = ["New York City", "London", "Tokyo", "Dubai", "Sydney", "Mumbai", "Chicago"]
    for city in cities:
        if city.lower() in q_lower:
            return city
        # Handle variations like "New York" for "New York City"
        if city == "New York City" and "new york" in q_lower:
            return "New York City"
    return None

def _generate_dynamic_mock_markets(session) -> List[Dict[str, Any]]:
    """Creates open weather markets in the database that are expiring soon."""
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    tomorrow = tomorrow.replace(hour=23, minute=59, second=59)
    day_after = now + timedelta(days=2)
    day_after = day_after.replace(hour=23, minute=59, second=59)

    cities = ["New York City", "London", "Tokyo", "Dubai", "Sydney", "Mumbai", "Chicago"]
    mock_list = []
    
    # Generate 1-2 markets per city
    for i, city in enumerate(cities):
        # Even indices get rain markets, odd get temp markets
        if i % 2 == 0:
            market_id = f"mock_{city.lower().replace(' ', '_')}_rain_{tomorrow.strftime('%Y%m%d')}"
            question = f"Will {city} experience rain/precipitation on {tomorrow.strftime('%B %d, %Y')}?"
            res_source = "precip > 0.0"
            yes_price = random.uniform(0.35, 0.65)
        else:
            market_id = f"mock_{city.lower().replace(' ', '_')}_temp_{tomorrow.strftime('%Y%m%d')}"
            
            # Setup realistic temp thresholds depending on city climate
            if city == "Dubai":
                thresh = 42.0
                yes_price = random.uniform(0.60, 0.85)
            elif city == "Sydney":
                thresh = 18.0
                yes_price = random.uniform(0.20, 0.45)
            else:
                thresh = 28.0
                yes_price = random.uniform(0.40, 0.70)
                
            question = f"Will the maximum temperature in {city} exceed {thresh}Â°C ({thresh * 1.8 + 32:.1f}Â°F) on {tomorrow.strftime('%B %d, %Y')}?"
            res_source = f"temp > {thresh}"
            
        no_price = 1.0 - yes_price
        
        parsed_market = {
            "market_id": market_id,
            "question": question,
            "city_ref": city,
            "outcome_yes_price": round(yes_price, 2),
            "outcome_no_price": round(no_price, 2),
            "volume": round(random.uniform(5000.0, 25000.0), 2),
            "end_time": tomorrow,
            "resolution_source": res_source
        }
        
        # Write to database
        add_polymarket_market(
            session,
            market_id=market_id,
            question=question,
            city_ref=city,
            yes_price=round(yes_price, 2),
            no_price=round(no_price, 2),
            volume=parsed_market["volume"],
            end_time=tomorrow,
            resolution_source=res_source
        )
        mock_list.append(parsed_market)
        
    return mock_list

import json
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from config import DATABASE_URL, INITIAL_BANKROLL
from db.models import Base, City, WeatherSnapshot, PolymarketMarket, Bankroll
from db.queries import engine, get_db

def run_migrations():
    """Initializes the database schema and seeds initial data."""
    print("Running database migrations...")
    Base.metadata.create_all(engine)
    
    with get_db() as session:
        # 1. Initialize Bankroll if empty
        existing_bankroll = session.query(Bankroll).first()
        if not existing_bankroll:
            session.add(Bankroll(balance=INITIAL_BANKROLL, timestamp=datetime.utcnow(), reason="INITIAL"))
            print(f"Bankroll seeded with initial balance: ${INITIAL_BANKROLL}")

        # 2. Seed Cities if empty
        existing_cities = session.query(City).all()
        if not existing_cities:
            cities_data = [
                {"name": "New York City", "country": "USA", "lat": 40.7128, "lon": -74.0060, "climate_type": "Humid continental", "active": True},
                {"name": "London", "country": "UK", "lat": 51.5074, "lon": -0.1278, "climate_type": "Oceanic", "active": True},
                {"name": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503, "climate_type": "Humid subtropical", "active": True},
                {"name": "Dubai", "country": "UAE", "lat": 25.2048, "lon": 55.2708, "climate_type": "Desert/Arid", "active": True},
                {"name": "Sydney", "country": "Australia", "lat": -33.8688, "lon": 151.2093, "climate_type": "Oceanic/Subtropical", "active": True},
                {"name": "Mumbai", "country": "India", "lat": 19.0760, "lon": 72.8777, "climate_type": "Tropical monsoon", "active": True},
                {"name": "Chicago", "country": "USA", "lat": 41.8781, "lon": -87.6298, "climate_type": "Humid continental", "active": True}
            ]
            for c in cities_data:
                session.add(City(**c))
            session.commit()
            print("Cities matrix seeded.")
            
        # 3. Seed historical base rate snapshots if empty
        existing_snapshots = session.query(WeatherSnapshot).first()
        if not existing_snapshots:
            cities = session.query(City).all()
            for city in cities:
                # Seed 10 mock historical weather snapshots (representative of late June climate profile)
                for i in range(10):
                    days_ago = i + 1
                    fetched_at = datetime.utcnow() - timedelta(days=days_ago)
                    
                    # Generate realistic climate-specific temperature and weather
                    if city.name == "New York City":
                        temp = random.uniform(22.0, 31.0)
                        precip_prob = random.choice([0.1, 0.2, 0.8, 0.0, 0.4])
                        wind = random.uniform(5.0, 18.0)
                    elif city.name == "London":
                        temp = random.uniform(15.0, 24.0)
                        precip_prob = random.choice([0.2, 0.5, 0.9, 0.1, 0.6])
                        wind = random.uniform(8.0, 22.0)
                    elif city.name == "Tokyo":
                        temp = random.uniform(20.0, 28.0)
                        precip_prob = random.choice([0.3, 0.7, 0.9, 0.2, 0.5])
                        wind = random.uniform(6.0, 16.0)
                    elif city.name == "Dubai":
                        temp = random.uniform(36.0, 44.0)
                        precip_prob = 0.0
                        wind = random.uniform(10.0, 28.0)
                    elif city.name == "Sydney":
                        # June is Winter in Sydney
                        temp = random.uniform(10.0, 18.0)
                        precip_prob = random.choice([0.1, 0.3, 0.7, 0.0])
                        wind = random.uniform(10.0, 25.0)
                    elif city.name == "Mumbai":
                        # Late June is monsoon season
                        temp = random.uniform(26.0, 31.0)
                        precip_prob = random.choice([0.8, 0.9, 1.0, 0.7])
                        wind = random.uniform(15.0, 35.0)
                    else: # Chicago
                        temp = random.uniform(20.0, 29.0)
                        precip_prob = random.choice([0.0, 0.2, 0.7, 0.4])
                        wind = random.uniform(10.0, 26.0)

                    raw_json_data = {
                        "temperature": temp,
                        "precipitation_probability": precip_prob,
                        "wind_speed": wind,
                        "humidity": random.uniform(40.0, 95.0),
                        "historical": True
                    }

                    snapshot = WeatherSnapshot(
                        city_id=city.city_id,
                        fetched_at=fetched_at,
                        source="historical_seed",
                        temperature=temp,
                        precip_prob=precip_prob,
                        wind_speed=wind,
                        raw_json=json.dumps(raw_json_data)
                    )
                    session.add(snapshot)
            session.commit()
            print("Historical weather baseline snapshots seeded.")

        # 4. Seed active Polymarket markets if empty
        existing_markets = session.query(PolymarketMarket).first()
        if not existing_markets:
            now = datetime.utcnow()
            
            # Create a set of realistic markets expiring tomorrow and day-after-tomorrow
            tomorrow = now + timedelta(days=1)
            tomorrow = tomorrow.replace(hour=23, minute=59, second=59)
            
            day_after = now + timedelta(days=2)
            day_after = day_after.replace(hour=23, minute=59, second=59)
            
            mock_markets = [
                # New York City
                {
                    "market_id": "poly_nyc_rain_tomo",
                    "question": f"Will New York City experience precipitation (>0.01 inches) on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "New York City",
                    "outcome_yes_price": 0.42,
                    "outcome_no_price": 0.58,
                    "volume": 12500.0,
                    "end_time": tomorrow,
                    "resolution_source": "precip > 0.0"
                },
                {
                    "market_id": "poly_nyc_temp_tomo",
                    "question": f"Will the maximum temperature in New York City exceed 85Â°F (29.4Â°C) on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "New York City",
                    "outcome_yes_price": 0.65,
                    "outcome_no_price": 0.35,
                    "volume": 8400.0,
                    "end_time": tomorrow,
                    "resolution_source": "temp > 29.4"
                },
                
                # London
                {
                    "market_id": "poly_london_rain_tomo",
                    "question": f"Will London experience rainfall on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "London",
                    "outcome_yes_price": 0.58,
                    "outcome_no_price": 0.42,
                    "volume": 6200.0,
                    "end_time": tomorrow,
                    "resolution_source": "precip > 0.0"
                },
                
                # Dubai
                {
                    "market_id": "poly_dubai_temp_tomo",
                    "question": f"Will the maximum temperature in Dubai exceed 42Â°F (107.6Â°F) on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "Dubai",
                    "outcome_yes_price": 0.72,
                    "outcome_no_price": 0.28,
                    "volume": 25000.0,
                    "end_time": tomorrow,
                    "resolution_source": "temp > 42.0"
                },
                
                # Sydney
                {
                    "market_id": "poly_sydney_wind_tomo",
                    "question": f"Will Sydney experience maximum wind speeds above 25 km/h on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "Sydney",
                    "outcome_yes_price": 0.35,
                    "outcome_no_price": 0.65,
                    "volume": 4200.0,
                    "end_time": tomorrow,
                    "resolution_source": "wind > 25.0"
                },
                
                # Tokyo
                {
                    "market_id": "poly_tokyo_rain_dayafter",
                    "question": f"Will Tokyo experience rainfall on {day_after.strftime('%Y-%m-%d')}?",
                    "city_ref": "Tokyo",
                    "outcome_yes_price": 0.51,
                    "outcome_no_price": 0.49,
                    "volume": 9300.0,
                    "end_time": day_after,
                    "resolution_source": "precip > 0.0"
                },
                
                # Mumbai
                {
                    "market_id": "poly_mumbai_monsoon_tomo",
                    "question": f"Will Mumbai experience rainfall exceed 50mm on {tomorrow.strftime('%Y-%m-%d')}?",
                    "city_ref": "Mumbai",
                    "outcome_yes_price": 0.68,
                    "outcome_no_price": 0.32,
                    "volume": 18000.0,
                    "end_time": tomorrow,
                    "resolution_source": "precip > 50.0"
                }
            ]
            
            for m in mock_markets:
                session.add(PolymarketMarket(**m))
            session.commit()
            print("Active Polymarket weather prediction markets seeded.")
            
    print("Database migrations and seeding complete.")

if __name__ == "__main__":
    run_migrations()

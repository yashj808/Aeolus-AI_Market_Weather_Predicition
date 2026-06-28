import os
import pytest
from unittest.mock import patch
from db.migrations import run_migrations
from db.queries import get_db
from db.models import PaperTrade, Prediction, PolymarketMarket
from agent.core import run_agent_cycle

@pytest.mark.asyncio
async def test_agent_run_cycle_mock():
    # 1. Initialize DB and run migrations
    run_migrations()
    
    # 2. Run agent cycle in mock mode
    with patch("agent.core.MOCK_MODE", True), \
         patch("config.MOCK_MODE", True):
        run_id = await run_agent_cycle()
        assert run_id.startswith("run_")
    
    # 3. Query DB to verify predictions and trades were written
    with get_db() as session:
        predictions = session.query(Prediction).all()
        trades = session.query(PaperTrade).all()
        markets = session.query(PolymarketMarket).all()
        
        # We seeded 7 mock markets in migrations, and agent evaluates them
        assert len(markets) > 0
        assert len(predictions) > 0
        
        # Verify agent logged steps
        from db.models import AgentLog
        logs = session.query(AgentLog).filter(AgentLog.run_id == run_id).all()
        assert len(logs) > 0
        
        # Print results for audit trail
        print(f"\nCreated {len(predictions)} predictions and {len(trades)} paper trades during test cycle {run_id}.")
        for t in trades:
            print(f"- Trade {t.trade_id}: {t.side} on Pred {t.pred_id} (Stake: ${t.stake}, Odds: {t.odds})")

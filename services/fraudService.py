class FraudService:
    @staticmethod
    async def check_fraud(farmer_data: dict) -> bool:
        # Rule 1: Yield Spike (Simplified)
        history = farmer_data.get("yield_history", [])
        if len(history) > 1 and history[-1] > (sum(history[:-1]) / len(history[:-1])) * 2:
            return True
        
        # Rule 2: Low NDVI vs High Yield (Mock check)
        # In real prod, cross-reference satellite_service here
        return False
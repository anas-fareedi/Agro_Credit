from typing import Dict, Any, Optional
from datetime import datetime
from models.scores import ScoreResponse, FeatureBreakdown, ScoreInput


class ScoringService:
    """
    AgriTrust Scoring Service
    Calculates credit scores based on multiple factors:
    - repayment_ratio: Historical loan repayment behavior (0-1)
    - ndvi_score: NDVI vegetation health from satellite data (0-1)
    - weather_risk: Climate/weather risk factor (0-1, higher = more risk)
    - yield_consistency: Historical yield consistency (0-1)
    """
    
    # Scoring model version
    VERSION = "1.0"
    
    # Weights for score calculation (must sum to 1.0)
    WEIGHTS = {
        "repayment": 0.40,    # Financial history is most important
        "ndvi": 0.20,         # Satellite vegetation health
        "weather": 0.15,      # Climate stability
        "yield": 0.25         # Historical yield consistency
    }
    
    # Score range
    MIN_SCORE = 300
    MAX_SCORE = 900
    
    # Risk category thresholds
    HIGH_RISK_THRESHOLD = 500
    MEDIUM_RISK_THRESHOLD = 700
    
    # Loan amount multipliers based on score
    LOAN_MULTIPLIERS = {
        "High": 0.5,      # Max 50% of land value
        "Medium": 1.0,    # Max 100% of land value  
        "Low": 1.5        # Max 150% of land value
    }
    
    # Base loan amount per acre (for recommendation)
    BASE_LOAN_PER_ACRE = 25000  # Currency units
    
    @classmethod
    async def calculate_score(
        cls,
        repayment_ratio: float, 
        ndvi_score: float, 
        weather_risk: float, 
        yield_consistency: float,
        land_area_acres: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates the AgriTrust Score using weighted factors.
        
        Args:
            repayment_ratio: Loan repayment ratio (0-1, higher = better)
            ndvi_score: NDVI vegetation score (0-1, higher = healthier)
            weather_risk: Weather risk factor (0-1, lower = better)
            yield_consistency: Yield consistency (0-1, higher = more consistent)
            land_area_acres: Optional land area for loan recommendation
            
        Returns:
            Dict containing score, risk category, and breakdown
        """
        # Validate inputs
        inputs = cls._validate_inputs(repayment_ratio, ndvi_score, weather_risk, yield_consistency)
        
        # Calculate default probability
        # Lower values = better (all factors converted so lower = better)
        default_probability = (
            (1 - inputs["repayment_ratio"]) * cls.WEIGHTS["repayment"] +
            (1 - inputs["ndvi_score"]) * cls.WEIGHTS["ndvi"] +
            (inputs["weather_risk"]) * cls.WEIGHTS["weather"] +
            (1 - inputs["yield_consistency"]) * cls.WEIGHTS["yield"]
        )
        
        # Calculate AgriTrust Score (300-900 range)
        # Higher score = lower default probability = better creditworthiness
        score_range = cls.MAX_SCORE - cls.MIN_SCORE
        raw_score = (1 - default_probability) * score_range + cls.MIN_SCORE
        agri_trust_score = int(max(cls.MIN_SCORE, min(cls.MAX_SCORE, raw_score)))
        
        # Determine risk category
        risk_category = cls._get_risk_category(agri_trust_score)
        
        # Generate recommendation
        recommendation = cls._get_recommendation(agri_trust_score, risk_category)
        
        # Calculate max recommended loan
        max_loan = cls._calculate_max_loan(
            agri_trust_score, 
            risk_category, 
            land_area_acres
        )
        
        return {
            "agri_trust_score": agri_trust_score,
            "risk_category": risk_category,
            "default_probability": round(default_probability, 4),
            "feature_breakdown": {
                "financial_health": round(inputs["repayment_ratio"], 4),
                "satellite_health": round(inputs["ndvi_score"], 4),
                "climatic_stability": round(1 - inputs["weather_risk"], 4),
                "yield_consistency": round(inputs["yield_consistency"], 4)
            },
            "recommendation": recommendation,
            "max_recommended_loan": max_loan,
            "version": cls.VERSION
        }
    
    @classmethod
    def _validate_inputs(
        cls,
        repayment_ratio: float,
        ndvi_score: float,
        weather_risk: float,
        yield_consistency: float
    ) -> Dict[str, float]:
        """Validate and clamp input values to valid ranges."""
        return {
            "repayment_ratio": max(0.0, min(1.0, repayment_ratio)),
            "ndvi_score": max(0.0, min(1.0, ndvi_score)),
            "weather_risk": max(0.0, min(1.0, weather_risk)),
            "yield_consistency": max(0.0, min(1.0, yield_consistency))
        }
    
    @classmethod
    def _get_risk_category(cls, score: int) -> str:
        """Determine risk category based on score."""
        if score < cls.HIGH_RISK_THRESHOLD:
            return "High"
        elif score < cls.MEDIUM_RISK_THRESHOLD:
            return "Medium"
        return "Low"
    
    @classmethod
    def _get_recommendation(cls, score: int, risk_category: str) -> str:
        """Generate lending recommendation based on score."""
        if score >= 800:
            return "Excellent creditworthiness. Recommend approval with preferential rates."
        elif score >= 700:
            return "Good creditworthiness. Recommend approval with standard terms."
        elif score >= 600:
            return "Moderate creditworthiness. Consider approval with enhanced monitoring."
        elif score >= 500:
            return "Fair creditworthiness. Recommend smaller loan with strict terms."
        elif score >= 400:
            return "Poor creditworthiness. Consider rejection or require collateral."
        else:
            return "Very high risk. Recommend rejection."
    
    @classmethod
    def _calculate_max_loan(
        cls,
        score: int,
        risk_category: str,
        land_area_acres: Optional[float]
    ) -> Optional[float]:
        """Calculate maximum recommended loan amount."""
        if land_area_acres is None or land_area_acres <= 0:
            return None
        
        base_amount = land_area_acres * cls.BASE_LOAN_PER_ACRE
        multiplier = cls.LOAN_MULTIPLIERS.get(risk_category, 0.5)
        
        # Additional score-based adjustment
        score_factor = (score - cls.MIN_SCORE) / (cls.MAX_SCORE - cls.MIN_SCORE)
        
        max_loan = base_amount * multiplier * (0.5 + score_factor * 0.5)
        return round(max_loan, 2)
    
    @classmethod
    async def simulate_score(cls, inputs: ScoreInput) -> Dict[str, Any]:
        """
        Simulate a score calculation without saving.
        Useful for what-if scenarios.
        """
        return await cls.calculate_score(
            repayment_ratio=inputs.repayment_ratio,
            ndvi_score=inputs.ndvi_score,
            weather_risk=inputs.weather_risk,
            yield_consistency=inputs.yield_consistency
        )
    
    @classmethod
    def get_score_explanation(cls, score_data: Dict[str, Any]) -> str:
        """Generate human-readable explanation of the score."""
        score = score_data.get("agri_trust_score", 0)
        breakdown = score_data.get("feature_breakdown", {})
        
        explanations = []
        
        # Financial health
        fh = breakdown.get("financial_health", 0)
        if fh >= 0.8:
            explanations.append("Strong financial history")
        elif fh >= 0.6:
            explanations.append("Moderate financial history")
        else:
            explanations.append("Weak financial history")
        
        # Satellite health
        sh = breakdown.get("satellite_health", 0)
        if sh >= 0.7:
            explanations.append("Healthy crop conditions")
        elif sh >= 0.5:
            explanations.append("Average crop conditions")
        else:
            explanations.append("Poor crop conditions")
        
        # Climate stability
        cs = breakdown.get("climatic_stability", 0)
        if cs >= 0.7:
            explanations.append("Low weather risk")
        elif cs >= 0.4:
            explanations.append("Moderate weather risk")
        else:
            explanations.append("High weather risk")
        
        # Yield consistency
        yc = breakdown.get("yield_consistency", 0)
        if yc >= 0.7:
            explanations.append("Consistent yield history")
        elif yc >= 0.5:
            explanations.append("Variable yield history")
        else:
            explanations.append("Inconsistent yield history")
        
        return f"Score {score}: " + "; ".join(explanations)
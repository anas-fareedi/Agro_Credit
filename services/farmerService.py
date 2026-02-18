from typing import Dict, Any, Optional, List
from datetime import datetime
from config.firebase import db
from models.farmers import FarmerCreate, FarmerUpdate, FarmerResponse
from google.cloud.firestore_v1 import FieldFilter


class FarmerService:
    """Service for managing farmer data in Firestore."""
    
    COLLECTION = "farmers"
    
    @classmethod
    async def create_farmer(cls, farmer_data: FarmerCreate, user_id: str) -> Dict[str, Any]:
        """Create a new farmer profile."""
        doc_ref = db.collection(cls.COLLECTION).document()
        
        farmer_dict = farmer_data.model_dump()
        farmer_dict.update({
            "id": doc_ref.id,
            "firebase_uid": user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "agri_trust_score": None,
            "risk_category": None
        })
        
        # Convert lands to dict format for Firestore
        if farmer_dict.get("lands"):
            farmer_dict["lands"] = [
                {"lat": coord.lat, "lng": coord.lng} if hasattr(coord, "lat") else coord
                for coord in farmer_dict["lands"]
            ]
        
        doc_ref.set(farmer_dict)
        return farmer_dict
    
    @classmethod
    async def get_farmer(cls, farmer_id: str) -> Optional[Dict[str, Any]]:
        """Get a farmer by ID."""
        doc = db.collection(cls.COLLECTION).document(farmer_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    
    @classmethod
    async def get_farmer_by_uid(cls, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """Get a farmer by Firebase UID."""
        docs = db.collection(cls.COLLECTION).where(
            filter=FieldFilter("firebase_uid", "==", firebase_uid)
        ).limit(1).get()
        
        for doc in docs:
            return doc.to_dict()
        return None
    
    @classmethod
    async def update_farmer(
        cls, 
        farmer_id: str, 
        update_data: FarmerUpdate,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Update farmer data."""
        doc_ref = db.collection(cls.COLLECTION).document(farmer_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        # Build update dict, excluding None values
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        update_dict["updated_at"] = datetime.utcnow()
        
        # Convert lands to dict format
        if update_dict.get("lands"):
            update_dict["lands"] = [
                {"lat": coord.lat, "lng": coord.lng} if hasattr(coord, "lat") else coord
                for coord in update_dict["lands"]
            ]
        
        doc_ref.update(update_dict)
        
        # Return updated document
        return doc_ref.get().to_dict()
    
    @classmethod
    async def delete_farmer(cls, farmer_id: str) -> bool:
        """Delete a farmer profile."""
        doc_ref = db.collection(cls.COLLECTION).document(farmer_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False
        
        doc_ref.delete()
        return True
    
    @classmethod
    async def list_farmers(
        cls,
        page: int = 1,
        page_size: int = 20,
        district: Optional[str] = None,
        state: Optional[str] = None,
        min_score: Optional[int] = None
    ) -> Dict[str, Any]:
        """List farmers with pagination and filters."""
        query = db.collection(cls.COLLECTION)
        
        # Apply filters
        if district:
            query = query.where(filter=FieldFilter("district", "==", district))
        if state:
            query = query.where(filter=FieldFilter("state", "==", state))
        if min_score is not None:
            query = query.where(filter=FieldFilter("agri_trust_score", ">=", min_score))
        
        # Order by created_at
        query = query.order_by("created_at", direction="DESCENDING")
        
        # Get total count (approximate)
        all_docs = list(query.stream())
        total = len(all_docs)
        
        # Apply pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_docs = all_docs[start_idx:end_idx]
        
        farmers = [doc.to_dict() for doc in paginated_docs]
        
        return {
            "farmers": farmers,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    @classmethod
    async def update_farmer_score(
        cls,
        farmer_id: str,
        score: int,
        risk_category: str
    ) -> bool:
        """Update farmer's AgriTrust score."""
        doc_ref = db.collection(cls.COLLECTION).document(farmer_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False
        
        doc_ref.update({
            "agri_trust_score": score,
            "risk_category": risk_category,
            "score_updated_at": datetime.utcnow()
        })
        return True
    
    @classmethod
    async def get_farmer_statistics(cls) -> Dict[str, Any]:
        """Get aggregate statistics for all farmers."""
        docs = list(db.collection(cls.COLLECTION).stream())
        
        total_farmers = len(docs)
        if total_farmers == 0:
            return {
                "total_farmers": 0,
                "average_score": 0,
                "score_distribution": {},
                "crop_distribution": {}
            }
        
        scores = []
        crop_counts = {}
        risk_counts = {"High": 0, "Medium": 0, "Low": 0}
        
        for doc in docs:
            data = doc.to_dict()
            
            # Collect scores
            if data.get("agri_trust_score"):
                scores.append(data["agri_trust_score"])
            
            # Count crops
            crop = data.get("crop_type", "unknown")
            crop_counts[crop] = crop_counts.get(crop, 0) + 1
            
            # Count risk categories
            risk = data.get("risk_category")
            if risk and risk in risk_counts:
                risk_counts[risk] += 1
        
        return {
            "total_farmers": total_farmers,
            "average_score": sum(scores) / len(scores) if scores else 0,
            "score_distribution": risk_counts,
            "crop_distribution": crop_counts,
            "scored_farmers": len(scores)
        }

from typing import Dict, Any, Optional, List
from datetime import datetime
from config.firebase import db
from models.audit import AuditAction, AuditLogCreate, AuditLogFilter
from google.cloud.firestore_v1 import FieldFilter


class AuditService:
    """Service for managing audit logs."""
    
    COLLECTION = "audit_logs"
    
    @classmethod
    async def log(
        cls,
        action: AuditAction,
        user_id: str,
        user_role: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create an audit log entry."""
        doc_ref = db.collection(cls.COLLECTION).document()
        
        log_entry = {
            "id": doc_ref.id,
            "action": action.value,
            "user_id": user_id,
            "user_role": user_role,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow(),
            "success": success,
            "error_message": error_message
        }
        
        doc_ref.set(log_entry)
        return log_entry
    
    @classmethod
    async def log_action(
        cls,
        action: AuditAction,
        user_id: str,
        user_role: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request = None
    ) -> Dict[str, Any]:
        """Log an action with optional request context."""
        ip_address = None
        user_agent = None
        
        if request:
            # Extract from FastAPI request
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        
        return await cls.log(
            action=action,
            user_id=user_id,
            user_role=user_role,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @classmethod
    async def get_log(cls, log_id: str) -> Optional[Dict[str, Any]]:
        """Get a single audit log entry."""
        doc = db.collection(cls.COLLECTION).document(log_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    
    @classmethod
    async def list_logs(
        cls,
        page: int = 1,
        page_size: int = 50,
        filters: Optional[AuditLogFilter] = None
    ) -> Dict[str, Any]:
        """List audit logs with pagination and filters."""
        query = db.collection(cls.COLLECTION)
        
        if filters:
            if filters.user_id:
                query = query.where(filter=FieldFilter("user_id", "==", filters.user_id))
            if filters.action:
                query = query.where(filter=FieldFilter("action", "==", filters.action.value))
            if filters.resource_type:
                query = query.where(filter=FieldFilter("resource_type", "==", filters.resource_type))
            if filters.resource_id:
                query = query.where(filter=FieldFilter("resource_id", "==", filters.resource_id))
            if filters.start_date:
                query = query.where(filter=FieldFilter("timestamp", ">=", filters.start_date))
            if filters.end_date:
                query = query.where(filter=FieldFilter("timestamp", "<=", filters.end_date))
            if filters.success_only:
                query = query.where(filter=FieldFilter("success", "==", True))
        
        query = query.order_by("timestamp", direction="DESCENDING")
        
        all_docs = list(query.stream())
        total = len(all_docs)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_docs = all_docs[start_idx:end_idx]
        
        logs = [doc.to_dict() for doc in paginated_docs]
        
        return {
            "logs": logs,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    @classmethod
    async def get_logs_by_user(
        cls,
        user_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs for a specific user."""
        query = db.collection(cls.COLLECTION).where(
            filter=FieldFilter("user_id", "==", user_id)
        ).order_by("timestamp", direction="DESCENDING").limit(limit)
        
        return [doc.to_dict() for doc in query.stream()]
    
    @classmethod
    async def get_logs_by_resource(
        cls,
        resource_type: str,
        resource_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit logs for a specific resource."""
        query = db.collection(cls.COLLECTION).where(
            filter=FieldFilter("resource_type", "==", resource_type)
        ).where(
            filter=FieldFilter("resource_id", "==", resource_id)
        ).order_by("timestamp", direction="DESCENDING").limit(limit)
        
        return [doc.to_dict() for doc in query.stream()]
    
    @classmethod
    async def get_summary(
        cls,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get summary statistics for audit logs."""
        query = db.collection(cls.COLLECTION)
        
        if start_date:
            query = query.where(filter=FieldFilter("timestamp", ">=", start_date))
        if end_date:
            query = query.where(filter=FieldFilter("timestamp", "<=", end_date))
        
        docs = list(query.stream())
        
        if not docs:
            return {
                "total_actions": 0,
                "actions_by_type": {},
                "actions_by_user": {},
                "failed_actions": 0,
                "time_range_start": start_date,
                "time_range_end": end_date
            }
        
        actions_by_type = {}
        actions_by_user = {}
        failed_count = 0
        timestamps = []
        
        for doc in docs:
            data = doc.to_dict()
            
            # Count by action type
            action = data.get("action", "unknown")
            actions_by_type[action] = actions_by_type.get(action, 0) + 1
            
            # Count by user
            user = data.get("user_id", "unknown")
            actions_by_user[user] = actions_by_user.get(user, 0) + 1
            
            # Count failures
            if not data.get("success", True):
                failed_count += 1
            
            # Track timestamps
            if data.get("timestamp"):
                timestamps.append(data["timestamp"])
        
        return {
            "total_actions": len(docs),
            "actions_by_type": actions_by_type,
            "actions_by_user": actions_by_user,
            "failed_actions": failed_count,
            "time_range_start": min(timestamps) if timestamps else start_date,
            "time_range_end": max(timestamps) if timestamps else end_date
        }
    
    @classmethod
    async def cleanup_old_logs(cls, days_to_keep: int = 90) -> int:
        """Delete audit logs older than specified days."""
        cutoff_date = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        cutoff_date = cutoff_date - timedelta(days=days_to_keep)
        
        query = db.collection(cls.COLLECTION).where(
            filter=FieldFilter("timestamp", "<", cutoff_date)
        )
        
        deleted_count = 0
        for doc in query.stream():
            doc.reference.delete()
            deleted_count += 1
        
        return deleted_count

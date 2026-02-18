from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from config.firebase import db
from models.loans import (
    LoanCreate, LoanUpdate, LoanApproval, LoanRepayment,
    LoanStatus, LoanResponse
)
from google.cloud.firestore_v1 import FieldFilter


class LoanService:
    """Service for managing loan applications and repayments."""
    
    COLLECTION = "loans"
    
    @classmethod
    async def create_loan_application(
        cls,
        loan_data: LoanCreate,
        user_id: str,
        agri_trust_score: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new loan application."""
        doc_ref = db.collection(cls.COLLECTION).document()
        
        # Get farmer name
        farmer_doc = db.collection("farmers").document(loan_data.farmer_id).get()
        farmer_name = farmer_doc.to_dict().get("name", "Unknown") if farmer_doc.exists else "Unknown"
        
        loan_dict = loan_data.model_dump()
        loan_dict.update({
            "id": doc_ref.id,
            "status": LoanStatus.PENDING.value,
            "created_by": user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "agri_trust_score_at_application": agri_trust_score,
            "approved_amount": None,
            "approved_by": None,
            "disbursed_at": None,
            "total_repaid": 0,
            "outstanding_balance": None,
            "repayment_schedule": [],
            "repayment_history": [],
            "farmer_name": farmer_name
        })
        
        doc_ref.set(loan_dict)
        return loan_dict
    
    @classmethod
    async def get_loan(cls, loan_id: str) -> Optional[Dict[str, Any]]:
        """Get a loan by ID."""
        doc = db.collection(cls.COLLECTION).document(loan_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    
    @classmethod
    async def update_loan(
        cls,
        loan_id: str,
        update_data: LoanUpdate
    ) -> Optional[Dict[str, Any]]:
        """Update loan data."""
        doc_ref = db.collection(cls.COLLECTION).document(loan_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        
        # Convert enum to string
        if "status" in update_dict:
            update_dict["status"] = update_dict["status"].value
        
        update_dict["updated_at"] = datetime.utcnow()
        doc_ref.update(update_dict)
        
        return doc_ref.get().to_dict()
    
    @classmethod
    async def approve_loan(
        cls,
        loan_id: str,
        approval: LoanApproval,
        lender_id: str
    ) -> Optional[Dict[str, Any]]:
        """Approve or reject a loan application."""
        doc_ref = db.collection(cls.COLLECTION).document(loan_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        loan_data = doc.to_dict()
        
        if loan_data.get("status") != LoanStatus.PENDING.value:
            raise ValueError("Loan is not in pending status")
        
        if approval.approved:
            new_status = LoanStatus.APPROVED.value
            approved_amount = approval.approved_amount or loan_data.get("amount")
            
            # Generate repayment schedule
            term_months = loan_data.get("term_months", 12)
            interest_rate = loan_data.get("interest_rate", 8.0)
            schedule = cls._generate_repayment_schedule(
                approved_amount, term_months, interest_rate
            )
            
            update_dict = {
                "status": new_status,
                "approved_amount": approved_amount,
                "approved_by": lender_id,
                "approved_at": datetime.utcnow(),
                "outstanding_balance": approved_amount * (1 + (interest_rate / 100) * (term_months / 12)),
                "repayment_schedule": schedule,
                "notes": approval.notes,
                "updated_at": datetime.utcnow()
            }
        else:
            update_dict = {
                "status": LoanStatus.REJECTED.value,
                "rejected_by": lender_id,
                "rejected_at": datetime.utcnow(),
                "rejection_reason": approval.notes,
                "updated_at": datetime.utcnow()
            }
        
        doc_ref.update(update_dict)
        return doc_ref.get().to_dict()
    
    @classmethod
    async def disburse_loan(cls, loan_id: str, lender_id: str) -> Optional[Dict[str, Any]]:
        """Mark a loan as disbursed."""
        doc_ref = db.collection(cls.COLLECTION).document(loan_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        loan_data = doc.to_dict()
        
        if loan_data.get("status") != LoanStatus.APPROVED.value:
            raise ValueError("Loan must be approved before disbursement")
        
        doc_ref.update({
            "status": LoanStatus.DISBURSED.value,
            "disbursed_at": datetime.utcnow(),
            "disbursed_by": lender_id,
            "updated_at": datetime.utcnow()
        })
        
        return doc_ref.get().to_dict()
    
    @classmethod
    async def record_repayment(
        cls,
        loan_id: str,
        repayment: LoanRepayment
    ) -> Optional[Dict[str, Any]]:
        """Record a loan repayment."""
        doc_ref = db.collection(cls.COLLECTION).document(loan_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
        
        loan_data = doc.to_dict()
        
        valid_statuses = [LoanStatus.DISBURSED.value, LoanStatus.REPAYING.value]
        if loan_data.get("status") not in valid_statuses:
            raise ValueError("Loan must be disbursed or in repayment to record payment")
        
        # Add to repayment history
        repayment_entry = {
            "amount": repayment.amount,
            "payment_date": repayment.payment_date or datetime.utcnow(),
            "payment_method": repayment.payment_method,
            "transaction_id": repayment.transaction_id
        }
        
        repayment_history = loan_data.get("repayment_history", [])
        repayment_history.append(repayment_entry)
        
        total_repaid = loan_data.get("total_repaid", 0) + repayment.amount
        outstanding = loan_data.get("outstanding_balance", 0) - repayment.amount
        
        # Check if loan is fully repaid
        new_status = LoanStatus.REPAYING.value
        if outstanding <= 0:
            new_status = LoanStatus.COMPLETED.value
            outstanding = 0
        
        doc_ref.update({
            "repayment_history": repayment_history,
            "total_repaid": total_repaid,
            "outstanding_balance": outstanding,
            "status": new_status,
            "last_repayment_date": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        
        # Update farmer's repayment ratio
        await cls._update_farmer_repayment_ratio(loan_data.get("farmer_id"))
        
        return doc_ref.get().to_dict()
    
    @classmethod
    async def get_loans_by_farmer(
        cls,
        farmer_id: str,
        status: Optional[LoanStatus] = None
    ) -> List[Dict[str, Any]]:
        """Get all loans for a farmer."""
        query = db.collection(cls.COLLECTION).where(
            filter=FieldFilter("farmer_id", "==", farmer_id)
        )
        
        if status:
            query = query.where(filter=FieldFilter("status", "==", status.value))
        
        query = query.order_by("created_at", direction="DESCENDING")
        
        return [doc.to_dict() for doc in query.stream()]
    
    @classmethod
    async def list_loans(
        cls,
        page: int = 1,
        page_size: int = 20,
        status: Optional[LoanStatus] = None,
        lender_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List loans with pagination and filters."""
        query = db.collection(cls.COLLECTION)
        
        if status:
            query = query.where(filter=FieldFilter("status", "==", status.value))
        if lender_id:
            query = query.where(filter=FieldFilter("approved_by", "==", lender_id))
        
        query = query.order_by("created_at", direction="DESCENDING")
        
        all_docs = list(query.stream())
        total = len(all_docs)
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_docs = all_docs[start_idx:end_idx]
        
        loans = [doc.to_dict() for doc in paginated_docs]
        
        return {
            "loans": loans,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    
    @classmethod
    async def get_loan_statistics(cls) -> Dict[str, Any]:
        """Get aggregate loan statistics."""
        docs = list(db.collection(cls.COLLECTION).stream())
        
        if not docs:
            return {
                "total_loans": 0,
                "total_amount_disbursed": 0,
                "total_amount_repaid": 0,
                "active_loans": 0,
                "default_rate": 0,
                "average_loan_amount": 0
            }
        
        total_disbursed = 0
        total_repaid = 0
        active_loans = 0
        defaulted_loans = 0
        loan_amounts = []
        
        for doc in docs:
            data = doc.to_dict()
            
            if data.get("approved_amount"):
                loan_amounts.append(data["approved_amount"])
            
            if data.get("status") in [LoanStatus.DISBURSED.value, LoanStatus.REPAYING.value]:
                active_loans += 1
                total_disbursed += data.get("approved_amount", 0)
            
            if data.get("status") == LoanStatus.COMPLETED.value:
                total_disbursed += data.get("approved_amount", 0)
            
            if data.get("status") == LoanStatus.DEFAULTED.value:
                defaulted_loans += 1
                total_disbursed += data.get("approved_amount", 0)
            
            total_repaid += data.get("total_repaid", 0)
        
        default_rate = defaulted_loans / len(docs) if docs else 0
        avg_loan = sum(loan_amounts) / len(loan_amounts) if loan_amounts else 0
        
        return {
            "total_loans": len(docs),
            "total_amount_disbursed": total_disbursed,
            "total_amount_repaid": total_repaid,
            "active_loans": active_loans,
            "default_rate": round(default_rate, 4),
            "average_loan_amount": round(avg_loan, 2)
        }
    
    @classmethod
    def _generate_repayment_schedule(
        cls,
        principal: float,
        term_months: int,
        annual_rate: float
    ) -> List[Dict[str, Any]]:
        """Generate monthly repayment schedule."""
        monthly_rate = annual_rate / 100 / 12
        
        # Calculate EMI using formula
        if monthly_rate > 0:
            emi = principal * monthly_rate * ((1 + monthly_rate) ** term_months) / \
                  (((1 + monthly_rate) ** term_months) - 1)
        else:
            emi = principal / term_months
        
        schedule = []
        start_date = datetime.utcnow()
        
        for i in range(term_months):
            due_date = start_date + timedelta(days=30 * (i + 1))
            schedule.append({
                "installment_number": i + 1,
                "due_date": due_date.isoformat(),
                "amount": round(emi, 2),
                "paid": False,
                "paid_date": None,
                "paid_amount": None
            })
        
        return schedule
    
    @classmethod
    async def _update_farmer_repayment_ratio(cls, farmer_id: str) -> None:
        """Update farmer's repayment ratio based on loan history."""
        if not farmer_id:
            return
        
        loans = await cls.get_loans_by_farmer(farmer_id)
        
        total_expected = 0
        total_repaid = 0
        
        for loan in loans:
            if loan.get("status") in [
                LoanStatus.DISBURSED.value, 
                LoanStatus.REPAYING.value, 
                LoanStatus.COMPLETED.value,
                LoanStatus.DEFAULTED.value
            ]:
                total_expected += loan.get("outstanding_balance", 0) + loan.get("total_repaid", 0)
                total_repaid += loan.get("total_repaid", 0)
        
        if total_expected > 0:
            repayment_ratio = min(1.0, total_repaid / total_expected)
            db.collection("farmers").document(farmer_id).update({
                "repayment_ratio": repayment_ratio,
                "updated_at": datetime.utcnow()
            })

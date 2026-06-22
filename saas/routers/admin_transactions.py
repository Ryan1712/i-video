"""Admin manual review/linking of unmatched bank transactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..billing.service import activate_subscription
from ..db import get_db
from ..models import BankTransaction, Order, User
from ..schemas import BankTransactionOut

router = APIRouter(prefix="/admin/transactions", tags=["admin"])


@router.get("/unmatched", response_model=list[BankTransactionOut])
def list_unmatched(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[BankTransaction]:
    return db.query(BankTransaction).filter_by(status="unmatched").all()


@router.post("/{transaction_id}/link/{order_id}", response_model=BankTransactionOut)
def link_transaction(
    transaction_id: int, order_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> BankTransaction:
    txn = db.query(BankTransaction).filter_by(id=transaction_id).one_or_none()
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if txn.status != "unmatched":
        raise HTTPException(status_code=409, detail="Transaction already matched")
    if order.status != "pending":
        raise HTTPException(status_code=409, detail="Order is not pending")

    txn.status = "matched"
    txn.matched_order_id = order.id
    db.commit()
    activate_subscription(db, order)

    log_action(
        db, actor=current_user, action="transaction.manual_link", target_type="bank_transaction",
        target_id=txn.id, after={"matched_order_id": order.id},
    )
    return txn

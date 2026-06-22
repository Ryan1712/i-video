"""Admin voucher CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import User, Voucher
from ..schemas import VoucherIn, VoucherOut

router = APIRouter(prefix="/admin/vouchers", tags=["admin"])


@router.post("", response_model=VoucherOut, status_code=201)
def create_voucher(
    payload: VoucherIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Voucher:
    voucher = Voucher(
        code=payload.code, discount_type=payload.discount_type, discount_value=payload.discount_value,
        max_uses=payload.max_uses, expires_at=payload.expires_at, applicable_plan_ids=payload.applicable_plan_ids,
    )
    db.add(voucher)
    db.commit()

    log_action(
        db, actor=current_user, action="voucher.create", target_type="voucher", target_id=voucher.id,
        after={"code": voucher.code, "discount_type": voucher.discount_type, "discount_value": voucher.discount_value},
    )
    return voucher


@router.get("", response_model=list[VoucherOut])
def list_vouchers(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Voucher]:
    return db.query(Voucher).all()


@router.delete("/{voucher_id}", status_code=204, response_class=Response)
def delete_voucher(
    voucher_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Response:
    voucher = db.query(Voucher).filter_by(id=voucher_id).one_or_none()
    if voucher is None:
        raise HTTPException(status_code=404, detail="Voucher not found")

    before = {"code": voucher.code, "discount_type": voucher.discount_type, "discount_value": voucher.discount_value}
    db.delete(voucher)
    db.commit()

    log_action(db, actor=current_user, action="voucher.delete", target_type="voucher", target_id=voucher_id, before=before)
    return Response(status_code=204)

"""API v1 warehouse routes and stock document posting."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.api.routers_v1 import error_detail, require_v1_permission, success_response
from server_app.db.models import (
    Inventory,
    InventoryLine,
    InventoryRevision,
    Product,
    StockBalance,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    StockWriteoff,
    StockWriteoffLine,
    UnitOfMeasure,
    User,
    Warehouse,
)
from server_app.schemas.warehouse_v1 import (
    InventoryCreate,
    InventoryLinesReplace,
    StockDocumentLineCreate,
    StockTransferCreate,
    StockWriteoffCreate,
    WarehouseCreate,
    WarehouseUpdate,
)
from server_app.services.warehouse import (
    QTY_ZERO,
    WarehouseBusinessError,
    get_or_create_balance,
    money,
    post_stock_movement,
    quantity,
)


router = APIRouter(prefix="/api/v1", tags=["warehouse"])
require_warehouse_view = require_v1_permission("warehouse.view")
require_warehouse_settings = require_v1_permission("warehouse.settings")
require_transfer_create = require_v1_permission("warehouse.transfer_create")
require_transfer_send = require_v1_permission("warehouse.transfer_send")
require_transfer_receive = require_v1_permission("warehouse.transfer_receive")
require_writeoff_create = require_v1_permission("warehouse.writeoff_create")
require_writeoff_post = require_v1_permission("warehouse.writeoff_post")
require_writeoff_cancel = require_v1_permission("warehouse.writeoff_cancel")
require_inventory_create = require_v1_permission("warehouse.inventory_create")
require_inventory_post = require_v1_permission("warehouse.inventory_post")
require_inventory_cancel = require_v1_permission("warehouse.inventory_cancel")


def _now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _decimal(value: Decimal | int | str | None, places: str) -> str:
    """Return a decimal value as a normalized string."""

    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal(places)))


def _get_or_404(session: Session, model: type[Any], object_id: int, name: str) -> Any:
    """Load a row by primary key or raise a v1 error."""

    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", f"{name} not found."))
    return item


def _business_error(exc: WarehouseBusinessError) -> HTTPException:
    """Translate a warehouse business error to the v1 HTTP envelope."""

    return HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details))


def _updates(payload: Any) -> dict[str, Any]:
    """Return explicitly supplied update fields."""

    return payload.model_dump(exclude_unset=True)


def _warehouse_payload(warehouse: Warehouse) -> dict[str, Any]:
    """Return a warehouse response payload."""

    return {
        "id": warehouse.id,
        "code": warehouse.code,
        "name": warehouse.name,
        "location": warehouse.location,
        "is_active": warehouse.is_active,
    }


def _balance_payload(balance: StockBalance) -> dict[str, Any]:
    """Return a stock balance response payload."""

    return {
        "id": balance.id,
        "warehouse_id": balance.warehouse_id,
        "warehouse_code": balance.warehouse.code if balance.warehouse else None,
        "warehouse_name": balance.warehouse.name if balance.warehouse else None,
        "product_id": balance.product_id,
        "product_sku": balance.product.sku if balance.product else None,
        "product_name": balance.product.name if balance.product else None,
        "uom_id": balance.uom_id,
        "uom_code": balance.uom.code if balance.uom else None,
        "quantity": _decimal(balance.quantity, "0.001"),
        "avg_cost_tmt": _decimal(balance.avg_cost_tmt, "0.01"),
    }


def _movement_payload(movement: StockMovement) -> dict[str, Any]:
    """Return a stock movement response payload."""

    return {
        "id": movement.id,
        "warehouse_id": movement.warehouse_id,
        "warehouse_code": movement.warehouse.code if movement.warehouse else None,
        "warehouse_name": movement.warehouse.name if movement.warehouse else None,
        "product_id": movement.product_id,
        "product_sku": movement.product.sku if movement.product else None,
        "product_name": movement.product.name if movement.product else None,
        "uom_id": movement.uom_id,
        "uom_code": movement.uom.code if movement.uom else None,
        "movement_type": movement.movement_type,
        "document_type": movement.document_type,
        "document_id": movement.document_id,
        "quantity": _decimal(movement.quantity, "0.001"),
        "unit_cost_tmt": _decimal(movement.unit_cost_tmt, "0.01"),
        "amount_tmt": _decimal(movement.amount_tmt, "0.01"),
        "created_by_user_id": movement.created_by_user_id,
        "movement_date": movement.movement_date.isoformat() if movement.movement_date else None,
    }


def _line_payload(line: StockTransferLine | StockWriteoffLine) -> dict[str, Any]:
    """Return a transfer/writeoff line payload."""

    return {
        "id": line.id,
        "product_id": line.product_id,
        "product_sku": line.product.sku if line.product else None,
        "product_name": line.product.name if line.product else None,
        "uom_id": line.uom_id,
        "uom_code": line.uom.code if line.uom else None,
        "quantity": _decimal(line.quantity, "0.001"),
        "unit_cost_tmt": _decimal(line.unit_cost_tmt, "0.01"),
    }


def _transfer_payload(transfer: StockTransfer) -> dict[str, Any]:
    """Return a stock transfer payload."""

    return {
        "id": transfer.id,
        "source_warehouse_id": transfer.source_warehouse_id,
        "source_warehouse_name": transfer.source_warehouse.name if transfer.source_warehouse else None,
        "target_warehouse_id": transfer.target_warehouse_id,
        "target_warehouse_name": transfer.target_warehouse.name if transfer.target_warehouse else None,
        "status": transfer.status,
        "note": transfer.note,
        "created_by_user_id": transfer.created_by_user_id,
        "sent_by_user_id": transfer.sent_by_user_id,
        "received_by_user_id": transfer.received_by_user_id,
        "rejected_by_user_id": transfer.rejected_by_user_id,
        "sent_at": transfer.sent_at.isoformat() if transfer.sent_at else None,
        "received_at": transfer.received_at.isoformat() if transfer.received_at else None,
        "rejected_at": transfer.rejected_at.isoformat() if transfer.rejected_at else None,
        "lines": [_line_payload(line) for line in transfer.lines],
    }


def _writeoff_payload(writeoff: StockWriteoff) -> dict[str, Any]:
    """Return a stock write-off payload."""

    return {
        "id": writeoff.id,
        "warehouse_id": writeoff.warehouse_id,
        "warehouse_name": writeoff.warehouse.name if writeoff.warehouse else None,
        "status": writeoff.status,
        "reason_code": writeoff.reason_code,
        "note": writeoff.note,
        "created_by_user_id": writeoff.created_by_user_id,
        "posted_by_user_id": writeoff.posted_by_user_id,
        "posted_at": writeoff.posted_at.isoformat() if writeoff.posted_at else None,
        "lines": [_line_payload(line) for line in writeoff.lines],
    }


def _inventory_line_payload(line: InventoryLine) -> dict[str, Any]:
    """Return an inventory line payload."""

    return {
        "id": line.id,
        "product_id": line.product_id,
        "product_sku": line.product.sku if line.product else None,
        "product_name": line.product.name if line.product else None,
        "uom_id": line.uom_id,
        "uom_code": line.uom.code if line.uom else None,
        "qty_expected": _decimal(line.qty_expected, "0.001"),
        "qty_actual": _decimal(line.qty_actual, "0.001") if line.qty_actual is not None else None,
        "unit_cost_tmt": _decimal(line.unit_cost_tmt, "0.01"),
    }


def _inventory_payload(inventory: Inventory) -> dict[str, Any]:
    """Return an inventory document payload."""

    return {
        "id": inventory.id,
        "warehouse_id": inventory.warehouse_id,
        "warehouse_name": inventory.warehouse.name if inventory.warehouse else None,
        "status": inventory.status,
        "note": inventory.note,
        "created_by_user_id": inventory.created_by_user_id,
        "posted_by_user_id": inventory.posted_by_user_id,
        "posted_at": inventory.posted_at.isoformat() if inventory.posted_at else None,
        "lines": [_inventory_line_payload(line) for line in inventory.lines],
    }


def _transfer_query(session: Session):
    """Return a stock transfer query with response relationships loaded."""

    return session.query(StockTransfer).options(
        selectinload(StockTransfer.source_warehouse),
        selectinload(StockTransfer.target_warehouse),
        selectinload(StockTransfer.lines).selectinload(StockTransferLine.product),
        selectinload(StockTransfer.lines).selectinload(StockTransferLine.uom),
    )


def _writeoff_query(session: Session):
    """Return a write-off query with response relationships loaded."""

    return session.query(StockWriteoff).options(
        selectinload(StockWriteoff.warehouse),
        selectinload(StockWriteoff.lines).selectinload(StockWriteoffLine.product),
        selectinload(StockWriteoff.lines).selectinload(StockWriteoffLine.uom),
    )


def _inventory_query(session: Session):
    """Return an inventory query with response relationships loaded."""

    return session.query(Inventory).options(
        selectinload(Inventory.warehouse),
        selectinload(Inventory.lines).selectinload(InventoryLine.product),
        selectinload(Inventory.lines).selectinload(InventoryLine.uom),
    )


def _ensure_warehouse(session: Session, warehouse_id: int) -> Warehouse:
    """Return an active warehouse or raise an error."""

    warehouse = _get_or_404(session, Warehouse, warehouse_id, "Warehouse")
    if not warehouse.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_WAREHOUSE", "Warehouse is inactive."))
    return warehouse


def _ensure_product_refs(session: Session, line: StockDocumentLineCreate) -> None:
    """Validate product and optional UOM references."""

    product = _get_or_404(session, Product, line.product_id, "Product")
    if not product.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_PRODUCT", "Product is inactive."))
    if line.uom_id is not None:
        _get_or_404(session, UnitOfMeasure, line.uom_id, "Unit of measure")


def _ensure_inventory_product_refs(session: Session, product_id: int, uom_id: int | None) -> Product:
    """Validate an inventory line product and optional UOM."""

    product = _get_or_404(session, Product, product_id, "Product")
    if not product.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_PRODUCT", "Product is inactive."))
    if uom_id is not None:
        _get_or_404(session, UnitOfMeasure, uom_id, "Unit of measure")
    return product


def _inventory_cost(session: Session, warehouse_id: int, product: Product, uom_id: int | None, fallback: Decimal | None) -> Decimal:
    """Return the best available cost for an inventory line."""

    balance = get_or_create_balance(session, warehouse_id, product.id, uom_id)
    if fallback is not None:
        return money(fallback)
    if balance.avg_cost_tmt:
        return money(balance.avg_cost_tmt)
    return money(product.last_known_cost)


def _make_inventory_line(session: Session, inventory: Inventory, product_id: int, uom_id: int | None, qty_actual: Decimal, unit_cost_tmt: Decimal | None) -> InventoryLine:
    """Build one inventory line with the current expected stock snapshot."""

    product = _ensure_inventory_product_refs(session, product_id, uom_id)
    balance = get_or_create_balance(session, inventory.warehouse_id, product_id, uom_id)
    return InventoryLine(
        inventory=inventory,
        product_id=product_id,
        uom_id=uom_id,
        qty_expected=quantity(balance.quantity),
        qty_actual=quantity(qty_actual),
        unit_cost_tmt=_inventory_cost(session, inventory.warehouse_id, product, uom_id, unit_cost_tmt),
    )


def _refresh_transfer(session: Session, transfer_id: int) -> StockTransfer:
    """Reload a transfer for response serialization."""

    transfer = _transfer_query(session).filter(StockTransfer.id == transfer_id).one_or_none()
    if transfer is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Transfer not found."))
    return transfer


def _refresh_writeoff(session: Session, writeoff_id: int) -> StockWriteoff:
    """Reload a write-off for response serialization."""

    writeoff = _writeoff_query(session).filter(StockWriteoff.id == writeoff_id).one_or_none()
    if writeoff is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Write-off not found."))
    return writeoff


def _refresh_inventory(session: Session, inventory_id: int) -> Inventory:
    """Reload an inventory document for response serialization."""

    inventory = _inventory_query(session).filter(Inventory.id == inventory_id).one_or_none()
    if inventory is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Inventory not found."))
    return inventory


@router.get("/warehouses")
def list_warehouses(
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List warehouses."""

    warehouses = session.query(Warehouse).order_by(Warehouse.code).all()
    return success_response([_warehouse_payload(warehouse) for warehouse in warehouses])


@router.post("/warehouses", status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    _: User = Depends(require_warehouse_settings),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a warehouse."""

    if session.query(Warehouse).filter(Warehouse.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Warehouse code already exists."))
    warehouse = Warehouse(**payload.model_dump())
    session.add(warehouse)
    session.commit()
    session.refresh(warehouse)
    return success_response(_warehouse_payload(warehouse))


@router.patch("/warehouses/{warehouse_id}")
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    _: User = Depends(require_warehouse_settings),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a warehouse."""

    warehouse = _get_or_404(session, Warehouse, warehouse_id, "Warehouse")
    for key, value in _updates(payload).items():
        setattr(warehouse, key, value)
    session.commit()
    session.refresh(warehouse)
    return success_response(_warehouse_payload(warehouse))


@router.get("/stock/balances")
def list_stock_balances(
    warehouse_id: int | None = Query(default=None),
    product_id: int | None = Query(default=None),
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List current stock balances."""

    query = session.query(StockBalance).options(
        selectinload(StockBalance.warehouse),
        selectinload(StockBalance.product),
        selectinload(StockBalance.uom),
    )
    if warehouse_id is not None:
        query = query.filter(StockBalance.warehouse_id == warehouse_id)
    if product_id is not None:
        query = query.filter(StockBalance.product_id == product_id)
    rows = query.order_by(StockBalance.warehouse_id, StockBalance.product_id).limit(1000).all()
    return success_response([_balance_payload(row) for row in rows])


@router.get("/stock/movements")
def list_stock_movements(
    warehouse_id: int | None = Query(default=None),
    product_id: int | None = Query(default=None),
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent stock movements."""

    query = session.query(StockMovement).options(
        selectinload(StockMovement.warehouse),
        selectinload(StockMovement.product),
        selectinload(StockMovement.uom),
    )
    if warehouse_id is not None:
        query = query.filter(StockMovement.warehouse_id == warehouse_id)
    if product_id is not None:
        query = query.filter(StockMovement.product_id == product_id)
    rows = query.order_by(StockMovement.id.desc()).limit(500).all()
    return success_response([_movement_payload(row) for row in rows])


@router.get("/stock-transfers")
def list_stock_transfers(
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent transfers."""

    transfers = _transfer_query(session).order_by(StockTransfer.id.desc()).limit(200).all()
    return success_response([_transfer_payload(transfer) for transfer in transfers])


@router.post("/stock-transfers", status_code=status.HTTP_201_CREATED)
def create_stock_transfer(
    payload: StockTransferCreate,
    current_user: User = Depends(require_transfer_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a draft stock transfer."""

    if payload.source_warehouse_id == payload.target_warehouse_id:
        raise HTTPException(status_code=400, detail=error_detail("SAME_WAREHOUSE", "Source and target warehouses must differ."))
    _ensure_warehouse(session, payload.source_warehouse_id)
    _ensure_warehouse(session, payload.target_warehouse_id)
    for line in payload.lines:
        _ensure_product_refs(session, line)

    transfer = StockTransfer(
        source_warehouse_id=payload.source_warehouse_id,
        target_warehouse_id=payload.target_warehouse_id,
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    for line in payload.lines:
        transfer.lines.append(
            StockTransferLine(
                product_id=line.product_id,
                uom_id=line.uom_id,
                quantity=quantity(line.quantity),
                unit_cost_tmt=money(line.unit_cost_tmt or 0),
            )
        )
    session.add(transfer)
    session.commit()
    return success_response(_transfer_payload(_refresh_transfer(session, transfer.id)))


@router.put("/stock-transfers/{transfer_id}")
def update_stock_transfer(
    transfer_id: int,
    payload: StockTransferCreate,
    _: User = Depends(require_transfer_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Replace a draft stock transfer header and lines."""

    transfer = _refresh_transfer(session, transfer_id)
    if transfer.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft transfers can be edited."))
    if payload.source_warehouse_id == payload.target_warehouse_id:
        raise HTTPException(status_code=400, detail=error_detail("SAME_WAREHOUSE", "Source and target warehouses must differ."))
    _ensure_warehouse(session, payload.source_warehouse_id)
    _ensure_warehouse(session, payload.target_warehouse_id)
    for line in payload.lines:
        _ensure_product_refs(session, line)

    transfer.source_warehouse_id = payload.source_warehouse_id
    transfer.target_warehouse_id = payload.target_warehouse_id
    transfer.note = payload.note
    transfer.lines.clear()
    session.flush()
    for line in payload.lines:
        transfer.lines.append(
            StockTransferLine(
                product_id=line.product_id,
                uom_id=line.uom_id,
                quantity=quantity(line.quantity),
                unit_cost_tmt=money(line.unit_cost_tmt or 0),
            )
        )
    session.commit()
    return success_response(_transfer_payload(_refresh_transfer(session, transfer.id)))


@router.get("/stock-transfers/{transfer_id}")
def get_stock_transfer(
    transfer_id: int,
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one stock transfer."""

    return success_response(_transfer_payload(_refresh_transfer(session, transfer_id)))


@router.post("/stock-transfers/{transfer_id}/send")
def send_stock_transfer(
    transfer_id: int,
    current_user: User = Depends(require_transfer_send),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Send a transfer and deduct the source warehouse."""

    transfer = _refresh_transfer(session, transfer_id)
    if transfer.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft transfers can be sent."))
    try:
        for line in transfer.lines:
            balance = get_or_create_balance(session, transfer.source_warehouse_id, line.product_id, line.uom_id)
            line.unit_cost_tmt = money(balance.avg_cost_tmt)
            post_stock_movement(
                session,
                warehouse_id=transfer.source_warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="transfer_out",
                document_type="stock_transfer",
                document_id=transfer.id,
                quantity_delta=-quantity(line.quantity),
                unit_cost_tmt=line.unit_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise _business_error(exc) from exc

    transfer.status = "in_transit"
    transfer.sent_by_user_id = current_user.id
    transfer.sent_at = _now()
    session.commit()
    return success_response(_transfer_payload(_refresh_transfer(session, transfer.id)))


@router.post("/stock-transfers/{transfer_id}/receive")
def receive_stock_transfer(
    transfer_id: int,
    current_user: User = Depends(require_transfer_receive),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Receive an in-transit transfer into the target warehouse."""

    transfer = _refresh_transfer(session, transfer_id)
    if transfer.status != "in_transit":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only in-transit transfers can be received."))
    try:
        for line in transfer.lines:
            post_stock_movement(
                session,
                warehouse_id=transfer.target_warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="transfer_in",
                document_type="stock_transfer",
                document_id=transfer.id,
                quantity_delta=quantity(line.quantity),
                unit_cost_tmt=line.unit_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise _business_error(exc) from exc

    transfer.status = "received"
    transfer.received_by_user_id = current_user.id
    transfer.received_at = _now()
    session.commit()
    return success_response(_transfer_payload(_refresh_transfer(session, transfer.id)))


@router.post("/stock-transfers/{transfer_id}/reject")
def reject_stock_transfer(
    transfer_id: int,
    current_user: User = Depends(require_transfer_receive),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reject an in-transit transfer and return stock to the source warehouse."""

    transfer = _refresh_transfer(session, transfer_id)
    if transfer.status != "in_transit":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only in-transit transfers can be rejected."))
    try:
        for line in transfer.lines:
            post_stock_movement(
                session,
                warehouse_id=transfer.source_warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="transfer_reject",
                document_type="stock_transfer",
                document_id=transfer.id,
                quantity_delta=quantity(line.quantity),
                unit_cost_tmt=line.unit_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise _business_error(exc) from exc

    transfer.status = "cancelled"
    transfer.rejected_by_user_id = current_user.id
    transfer.rejected_at = _now()
    session.commit()
    return success_response(_transfer_payload(_refresh_transfer(session, transfer.id)))


@router.get("/stock-writeoffs")
def list_stock_writeoffs(
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent write-offs."""

    writeoffs = _writeoff_query(session).order_by(StockWriteoff.id.desc()).limit(200).all()
    return success_response([_writeoff_payload(writeoff) for writeoff in writeoffs])


@router.post("/stock-writeoffs", status_code=status.HTTP_201_CREATED)
def create_stock_writeoff(
    payload: StockWriteoffCreate,
    current_user: User = Depends(require_writeoff_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a draft write-off."""

    _ensure_warehouse(session, payload.warehouse_id)
    for line in payload.lines:
        _ensure_product_refs(session, line)

    writeoff = StockWriteoff(
        warehouse_id=payload.warehouse_id,
        reason_code=payload.reason_code,
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    for line in payload.lines:
        writeoff.lines.append(
            StockWriteoffLine(
                product_id=line.product_id,
                uom_id=line.uom_id,
                quantity=quantity(line.quantity),
                unit_cost_tmt=money(line.unit_cost_tmt or 0),
            )
        )
    session.add(writeoff)
    session.commit()
    return success_response(_writeoff_payload(_refresh_writeoff(session, writeoff.id)))


@router.put("/stock-writeoffs/{writeoff_id}")
def update_stock_writeoff(
    writeoff_id: int,
    payload: StockWriteoffCreate,
    _: User = Depends(require_writeoff_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Replace a draft write-off header and lines."""

    writeoff = _refresh_writeoff(session, writeoff_id)
    if writeoff.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft write-offs can be edited."))
    _ensure_warehouse(session, payload.warehouse_id)
    for line in payload.lines:
        _ensure_product_refs(session, line)

    writeoff.warehouse_id = payload.warehouse_id
    writeoff.reason_code = payload.reason_code
    writeoff.note = payload.note
    writeoff.lines.clear()
    session.flush()
    for line in payload.lines:
        writeoff.lines.append(
            StockWriteoffLine(
                product_id=line.product_id,
                uom_id=line.uom_id,
                quantity=quantity(line.quantity),
                unit_cost_tmt=money(line.unit_cost_tmt or 0),
            )
        )
    session.commit()
    return success_response(_writeoff_payload(_refresh_writeoff(session, writeoff.id)))


@router.get("/stock-writeoffs/{writeoff_id}")
def get_stock_writeoff(
    writeoff_id: int,
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one write-off."""

    return success_response(_writeoff_payload(_refresh_writeoff(session, writeoff_id)))


@router.post("/stock-writeoffs/{writeoff_id}/post")
def post_stock_writeoff(
    writeoff_id: int,
    current_user: User = Depends(require_writeoff_post),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Post a write-off and deduct stock."""

    writeoff = _refresh_writeoff(session, writeoff_id)
    if writeoff.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft write-offs can be posted."))
    try:
        for line in writeoff.lines:
            balance = get_or_create_balance(session, writeoff.warehouse_id, line.product_id, line.uom_id)
            line.unit_cost_tmt = money(balance.avg_cost_tmt)
            post_stock_movement(
                session,
                warehouse_id=writeoff.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="writeoff",
                document_type="stock_writeoff",
                document_id=writeoff.id,
                quantity_delta=-quantity(line.quantity),
                unit_cost_tmt=line.unit_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise _business_error(exc) from exc

    writeoff.status = "posted"
    writeoff.posted_by_user_id = current_user.id
    writeoff.posted_at = _now()
    session.commit()
    return success_response(_writeoff_payload(_refresh_writeoff(session, writeoff.id)))


@router.post("/stock-writeoffs/{writeoff_id}/cancel")
def cancel_stock_writeoff(
    writeoff_id: int,
    current_user: User = Depends(require_writeoff_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a draft write-off or reverse a posted one."""

    writeoff = _refresh_writeoff(session, writeoff_id)
    if writeoff.status == "cancelled":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Write-off is already cancelled."))
    if writeoff.status == "posted":
        try:
            for line in writeoff.lines:
                post_stock_movement(
                    session,
                    warehouse_id=writeoff.warehouse_id,
                    product_id=line.product_id,
                    uom_id=line.uom_id,
                    movement_type="writeoff_cancel",
                    document_type="stock_writeoff",
                    document_id=writeoff.id,
                    quantity_delta=quantity(line.quantity),
                    unit_cost_tmt=line.unit_cost_tmt,
                    user_id=current_user.id,
                )
        except WarehouseBusinessError as exc:
            session.rollback()
            raise _business_error(exc) from exc
    writeoff.status = "cancelled"
    session.commit()
    return success_response(_writeoff_payload(_refresh_writeoff(session, writeoff.id)))


@router.get("/inventories")
def list_inventories(
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent inventory documents."""

    inventories = _inventory_query(session).order_by(Inventory.id.desc()).limit(200).all()
    return success_response([_inventory_payload(inventory) for inventory in inventories])


@router.post("/inventories", status_code=status.HTTP_201_CREATED)
def create_inventory(
    payload: InventoryCreate,
    current_user: User = Depends(require_inventory_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an inventory count document."""

    _ensure_warehouse(session, payload.warehouse_id)
    existing_open = (
        session.query(Inventory)
        .filter(Inventory.warehouse_id == payload.warehouse_id, Inventory.status.in_(["draft", "in_progress"]))
        .one_or_none()
    )
    if existing_open is not None:
        raise HTTPException(status_code=409, detail=error_detail("OPEN_INVENTORY", "This warehouse already has an open inventory."))

    inventory = Inventory(
        warehouse_id=payload.warehouse_id,
        note=payload.note,
        created_by_user_id=current_user.id,
        status="in_progress" if payload.lines else "draft",
    )
    session.add(inventory)
    session.flush()
    for line in payload.lines:
        inventory.lines.append(
            _make_inventory_line(session, inventory, line.product_id, line.uom_id, line.qty_actual, line.unit_cost_tmt)
        )
    session.commit()
    return success_response(_inventory_payload(_refresh_inventory(session, inventory.id)))


@router.get("/inventories/{inventory_id}")
def get_inventory(
    inventory_id: int,
    _: User = Depends(require_warehouse_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one inventory document."""

    return success_response(_inventory_payload(_refresh_inventory(session, inventory_id)))


@router.put("/inventories/{inventory_id}/lines")
def replace_inventory_lines(
    inventory_id: int,
    payload: InventoryLinesReplace,
    _: User = Depends(require_inventory_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Replace counted lines for an open inventory document."""

    inventory = _refresh_inventory(session, inventory_id)
    if inventory.status not in {"draft", "in_progress"}:
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only open inventories can be edited."))
    inventory.lines.clear()
    session.flush()
    for line in payload.lines:
        inventory.lines.append(
            _make_inventory_line(session, inventory, line.product_id, line.uom_id, line.qty_actual, line.unit_cost_tmt)
        )
    inventory.status = "in_progress"
    session.commit()
    return success_response(_inventory_payload(_refresh_inventory(session, inventory.id)))


@router.post("/inventories/{inventory_id}/post")
def post_inventory(
    inventory_id: int,
    current_user: User = Depends(require_inventory_post),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Post an inventory document and create adjustment movements."""

    inventory = _refresh_inventory(session, inventory_id)
    if inventory.status not in {"draft", "in_progress"}:
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only open inventories can be posted."))
    if not inventory.lines:
        raise HTTPException(status_code=400, detail=error_detail("EMPTY_DOCUMENT", "Inventory has no counted lines."))

    try:
        for line in inventory.lines:
            if line.qty_actual is None:
                raise WarehouseBusinessError("MISSING_COUNT", "Every inventory line must have an actual quantity.")
            diff = quantity(line.qty_actual) - quantity(line.qty_expected)
            if diff == QTY_ZERO:
                continue
            post_stock_movement(
                session,
                warehouse_id=inventory.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="inventory_plus" if diff > QTY_ZERO else "inventory_minus",
                document_type="inventory",
                document_id=inventory.id,
                quantity_delta=diff,
                unit_cost_tmt=line.unit_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise _business_error(exc) from exc

    inventory.status = "posted"
    inventory.posted_by_user_id = current_user.id
    inventory.posted_at = _now()
    session.add(
        InventoryRevision(
            warehouse_id=inventory.warehouse_id,
            revision_date=date.today(),
            note=f"Inventory #{inventory.id}",
            posted_by_user_id=current_user.id,
        )
    )
    session.commit()
    return success_response(_inventory_payload(_refresh_inventory(session, inventory.id)))


@router.post("/inventories/{inventory_id}/cancel")
def cancel_inventory(
    inventory_id: int,
    _: User = Depends(require_inventory_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel an open inventory document."""

    inventory = _refresh_inventory(session, inventory_id)
    if inventory.status not in {"draft", "in_progress"}:
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only open inventories can be cancelled."))
    inventory.status = "cancelled"
    session.commit()
    return success_response(_inventory_payload(_refresh_inventory(session, inventory.id)))

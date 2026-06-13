"""API v1 product catalog routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.api.routers_v1 import error_detail, require_v1_permission, success_response
from server_app.db.models import (
    ExpenseCategory,
    Product,
    ProductBarcode,
    ProductGroup,
    ProductUom,
    Service,
    ServiceBarcode,
    UnitOfMeasure,
    User,
)
from server_app.schemas.catalog_v1 import (
    ExpenseCategoryCreate,
    ExpenseCategoryUpdate,
    ProductBarcodeCreate,
    ProductCreate,
    ProductGroupCreate,
    ProductGroupUpdate,
    ProductUpdate,
    ServiceBarcodeCreate,
    ServiceCreate,
    ServiceUpdate,
    UnitOfMeasureCreate,
    UnitOfMeasureUpdate,
)


router = APIRouter(prefix="/api/v1", tags=["catalog"])
require_goods_view = require_v1_permission("goods.view")
require_goods_create = require_v1_permission("goods.create")
require_goods_edit = require_v1_permission("goods.edit")
require_goods_delete = require_v1_permission("goods.delete")


def _get_or_404(session: Session, model: type[Any], object_id: int, name: str) -> Any:
    """Load one ORM row by id or raise a v1 error."""

    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("NOT_FOUND", f"{name} not found."),
        )
    return item


def _updates(payload: Any) -> dict[str, Any]:
    """Return explicitly set update fields."""

    return payload.model_dump(exclude_unset=True)


def _apply_updates(item: Any, payload: Any) -> None:
    """Apply a Pydantic update payload to an ORM row."""

    for key, value in _updates(payload).items():
        setattr(item, key, value)


def _product_group_payload(group: ProductGroup) -> dict[str, Any]:
    """Return a product-group response payload."""

    return {
        "id": group.id,
        "parent_id": group.parent_id,
        "code": group.code,
        "name_ru": group.name_ru,
        "name_tk": group.name_tk,
        "sort_order": group.sort_order,
        "is_active": group.is_active,
    }


def _uom_payload(uom: UnitOfMeasure) -> dict[str, Any]:
    """Return a unit-of-measure response payload."""

    return {
        "id": uom.id,
        "code": uom.code,
        "name_ru": uom.name_ru,
        "name_tk": uom.name_tk,
        "is_active": uom.is_active,
    }


def _barcode_payload(barcode: ProductBarcode | ServiceBarcode) -> dict[str, Any]:
    """Return a barcode response payload."""

    data: dict[str, Any] = {"id": barcode.id, "barcode": barcode.barcode}
    if isinstance(barcode, ProductBarcode):
        data["product_id"] = barcode.product_id
        data["product_uom_id"] = barcode.product_uom_id
        data["is_weight_barcode"] = barcode.is_weight_barcode
    else:
        data["service_id"] = barcode.service_id
    return data


def _product_payload(product: Product) -> dict[str, Any]:
    """Return a product response payload."""

    return {
        "id": product.id,
        "sku": product.sku,
        "code": product.sku,
        "name": product.name,
        "name_ru": product.name,
        "name_tk": product.name_tk,
        "group_id": product.group_id,
        "group_name_ru": product.group.name_ru if product.group else None,
        "base_uom_id": product.base_uom_id,
        "product_type": product.product_type,
        "unit": product.unit,
        "retail_price": str(product.retail_price),
        "last_known_cost": str(product.last_known_cost),
        "min_stock": str(product.min_stock),
        "description": product.description,
        "is_active": product.is_active,
        "barcodes": [_barcode_payload(barcode) for barcode in product.barcodes],
    }


def _expense_category_payload(category: ExpenseCategory) -> dict[str, Any]:
    """Return an expense-category response payload."""

    return {
        "id": category.id,
        "code": category.code,
        "name_ru": category.name_ru,
        "name_tk": category.name_tk,
        "is_active": category.is_active,
    }


def _service_payload(service: Service) -> dict[str, Any]:
    """Return a service response payload."""

    return {
        "id": service.id,
        "code": service.code,
        "name_ru": service.name_ru,
        "name_tk": service.name_tk,
        "service_type": service.service_type,
        "expense_category_id": service.expense_category_id,
        "default_price": str(service.default_price),
        "is_active": service.is_active,
        "barcodes": [_barcode_payload(barcode) for barcode in service.barcodes],
    }


def _ensure_product_refs(session: Session, group_id: int | None, base_uom_id: int | None) -> None:
    """Validate optional product foreign keys."""

    if group_id is not None:
        _get_or_404(session, ProductGroup, group_id, "Product group")
    if base_uom_id is not None:
        _get_or_404(session, UnitOfMeasure, base_uom_id, "Unit of measure")


def _ensure_expense_category(session: Session, category_id: int | None) -> None:
    """Validate optional expense category."""

    if category_id is not None:
        _get_or_404(session, ExpenseCategory, category_id, "Expense category")


def _barcode_exists(session: Session, barcode: str) -> bool:
    """Return whether a barcode already exists in product or service catalogs."""

    return (
        session.query(ProductBarcode).filter(ProductBarcode.barcode == barcode).one_or_none() is not None
        or session.query(ServiceBarcode).filter(ServiceBarcode.barcode == barcode).one_or_none() is not None
    )


@router.get("/product-groups")
def list_product_groups(
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List product groups."""

    groups = session.query(ProductGroup).order_by(ProductGroup.sort_order, ProductGroup.code).all()
    return success_response([_product_group_payload(group) for group in groups])


@router.post("/product-groups", status_code=status.HTTP_201_CREATED)
def create_product_group(
    payload: ProductGroupCreate,
    _: User = Depends(require_goods_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a product group."""

    if payload.parent_id is not None:
        _get_or_404(session, ProductGroup, payload.parent_id, "Parent product group")
    if session.query(ProductGroup).filter(ProductGroup.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Product group code already exists."))
    group = ProductGroup(**payload.model_dump())
    session.add(group)
    session.commit()
    session.refresh(group)
    return success_response(_product_group_payload(group))


@router.patch("/product-groups/{group_id}")
def update_product_group(
    group_id: int,
    payload: ProductGroupUpdate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a product group."""

    group = _get_or_404(session, ProductGroup, group_id, "Product group")
    if payload.parent_id == group_id:
        raise HTTPException(status_code=400, detail=error_detail("INVALID_PARENT", "Group cannot be its own parent."))
    if payload.parent_id is not None:
        _get_or_404(session, ProductGroup, payload.parent_id, "Parent product group")
    _apply_updates(group, payload)
    session.commit()
    session.refresh(group)
    return success_response(_product_group_payload(group))


@router.get("/unit-of-measures")
def list_unit_of_measures(
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List units of measure."""

    items = session.query(UnitOfMeasure).order_by(UnitOfMeasure.code).all()
    return success_response([_uom_payload(item) for item in items])


@router.post("/unit-of-measures", status_code=status.HTTP_201_CREATED)
def create_unit_of_measure(
    payload: UnitOfMeasureCreate,
    _: User = Depends(require_goods_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a unit of measure."""

    if session.query(UnitOfMeasure).filter(UnitOfMeasure.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Unit code already exists."))
    uom = UnitOfMeasure(**payload.model_dump())
    session.add(uom)
    session.commit()
    session.refresh(uom)
    return success_response(_uom_payload(uom))


@router.patch("/unit-of-measures/{uom_id}")
def update_unit_of_measure(
    uom_id: int,
    payload: UnitOfMeasureUpdate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a unit of measure."""

    uom = _get_or_404(session, UnitOfMeasure, uom_id, "Unit of measure")
    _apply_updates(uom, payload)
    session.commit()
    session.refresh(uom)
    return success_response(_uom_payload(uom))


@router.get("/products")
def list_products(
    search: str | None = Query(default=None),
    group_id: int | None = Query(default=None),
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List products with light filtering."""

    query = session.query(Product).options(selectinload(Product.group), selectinload(Product.barcodes)).order_by(Product.sku)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))
    if group_id is not None:
        query = query.filter(Product.group_id == group_id)
    products = query.limit(500).all()
    return success_response([_product_payload(product) for product in products])


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one product."""

    product = (
        session.query(Product)
        .options(selectinload(Product.group), selectinload(Product.barcodes))
        .filter(Product.id == product_id)
        .one_or_none()
    )
    if product is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Product not found."))
    return success_response(_product_payload(product))


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    _: User = Depends(require_goods_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a product."""

    _ensure_product_refs(session, payload.group_id, payload.base_uom_id)
    if session.query(Product).filter(Product.sku == payload.sku).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Product code already exists."))
    product = Product(**payload.model_dump())
    session.add(product)
    session.commit()
    session.refresh(product)
    return success_response(_product_payload(product))


@router.patch("/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a product."""

    product = _get_or_404(session, Product, product_id, "Product")
    updates = _updates(payload)
    _ensure_product_refs(session, updates.get("group_id"), updates.get("base_uom_id"))
    for key, value in updates.items():
        setattr(product, key, value)
    session.commit()
    session.refresh(product)
    return success_response(_product_payload(product))


@router.delete("/products/{product_id}")
def deactivate_product(
    product_id: int,
    _: User = Depends(require_goods_delete),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deactivate a product."""

    product = _get_or_404(session, Product, product_id, "Product")
    product.is_active = False
    session.commit()
    return success_response(_product_payload(product))


@router.get("/products/by-barcode/{barcode}")
def get_product_by_barcode(
    barcode: str,
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a product by barcode."""

    row = (
        session.query(ProductBarcode)
        .options(selectinload(ProductBarcode.product).selectinload(Product.barcodes))
        .filter(ProductBarcode.barcode == barcode)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Barcode not found."))
    return success_response(_product_payload(row.product))


@router.post("/products/{product_id}/barcodes", status_code=status.HTTP_201_CREATED)
def add_product_barcode(
    product_id: int,
    payload: ProductBarcodeCreate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add a barcode to a product."""

    product = _get_or_404(session, Product, product_id, "Product")
    if payload.product_uom_id is not None:
        _get_or_404(session, ProductUom, payload.product_uom_id, "Product UOM")
    if _barcode_exists(session, payload.barcode):
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_BARCODE", "Barcode already exists."))
    barcode = ProductBarcode(product=product, **payload.model_dump())
    session.add(barcode)
    session.commit()
    session.refresh(barcode)
    return success_response(_barcode_payload(barcode))


@router.get("/expense-categories")
def list_expense_categories(
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List expense categories."""

    categories = session.query(ExpenseCategory).order_by(ExpenseCategory.code).all()
    return success_response([_expense_category_payload(category) for category in categories])


@router.post("/expense-categories", status_code=status.HTTP_201_CREATED)
def create_expense_category(
    payload: ExpenseCategoryCreate,
    _: User = Depends(require_goods_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an expense category."""

    if session.query(ExpenseCategory).filter(ExpenseCategory.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Expense category code already exists."))
    category = ExpenseCategory(**payload.model_dump())
    session.add(category)
    session.commit()
    session.refresh(category)
    return success_response(_expense_category_payload(category))


@router.patch("/expense-categories/{category_id}")
def update_expense_category(
    category_id: int,
    payload: ExpenseCategoryUpdate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update an expense category."""

    category = _get_or_404(session, ExpenseCategory, category_id, "Expense category")
    _apply_updates(category, payload)
    session.commit()
    session.refresh(category)
    return success_response(_expense_category_payload(category))


@router.get("/services")
def list_services(
    search: str | None = Query(default=None),
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List services."""

    query = session.query(Service).options(selectinload(Service.barcodes)).order_by(Service.code)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Service.code.ilike(pattern), Service.name_ru.ilike(pattern)))
    services = query.limit(500).all()
    return success_response([_service_payload(service) for service in services])


@router.get("/services/{service_id}")
def get_service(
    service_id: int,
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one service."""

    service = (
        session.query(Service)
        .options(selectinload(Service.barcodes))
        .filter(Service.id == service_id)
        .one_or_none()
    )
    if service is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Service not found."))
    return success_response(_service_payload(service))


@router.post("/services", status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    _: User = Depends(require_goods_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a service."""

    _ensure_expense_category(session, payload.expense_category_id)
    if session.query(Service).filter(Service.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Service code already exists."))
    service = Service(**payload.model_dump())
    session.add(service)
    session.commit()
    session.refresh(service)
    return success_response(_service_payload(service))


@router.patch("/services/{service_id}")
def update_service(
    service_id: int,
    payload: ServiceUpdate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a service."""

    service = _get_or_404(session, Service, service_id, "Service")
    updates = _updates(payload)
    _ensure_expense_category(session, updates.get("expense_category_id"))
    for key, value in updates.items():
        setattr(service, key, value)
    session.commit()
    session.refresh(service)
    return success_response(_service_payload(service))


@router.get("/services/by-barcode/{barcode}")
def get_service_by_barcode(
    barcode: str,
    _: User = Depends(require_goods_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a service by barcode."""

    row = (
        session.query(ServiceBarcode)
        .options(selectinload(ServiceBarcode.service).selectinload(Service.barcodes))
        .filter(ServiceBarcode.barcode == barcode)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Barcode not found."))
    return success_response(_service_payload(row.service))


@router.post("/services/{service_id}/barcodes", status_code=status.HTTP_201_CREATED)
def add_service_barcode(
    service_id: int,
    payload: ServiceBarcodeCreate,
    _: User = Depends(require_goods_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add a barcode to a service."""

    service = _get_or_404(session, Service, service_id, "Service")
    if _barcode_exists(session, payload.barcode):
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_BARCODE", "Barcode already exists."))
    barcode = ServiceBarcode(service=service, barcode=payload.barcode)
    session.add(barcode)
    session.commit()
    session.refresh(barcode)
    return success_response(_barcode_payload(barcode))

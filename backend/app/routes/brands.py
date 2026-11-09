from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.brand import Brand
from app.models.membership import BrandMembership
from app.models.user import User
from app.schemas.brand import BrandCreate, BrandResponse
from app.core.dependencies import get_current_user
from uuid import UUID
from app.services.brand_access import authorize_brand_action
from app.schemas.brand import BrandCreate, BrandResponse, BrandUpdate

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.post(
    "/",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED
)
def create_brand(
    brand_data: BrandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_brand = db.scalar(
        select(Brand).where(Brand.slug == brand_data.slug)
    )

    if existing_brand:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brand slug is already taken.",
        )

    new_brand = Brand(
        name=brand_data.name,
        slug=brand_data.slug,
        created_by=current_user.id,
    )

    db.add(new_brand)
    db.flush()

    owner_membership = BrandMembership(
        user_id=current_user.id,
        brand_id=new_brand.id,
        role="owner",
    )

    db.add(owner_membership)
    db.commit()
    db.refresh(new_brand)

    return new_brand
@router.get("/", response_model=list[BrandResponse])
def get_my_brands(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Brand)
        .join(BrandMembership)
        .where(BrandMembership.user_id == current_user.id)
    )

    brands = db.scalars(statement).all()

    return brands
@router.get("/{brand_id}", response_model=BrandResponse)
def get_brand_details(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db=db,
        user_id=current_user.id,
        brand_id=brand_id,
        permission="brand:read",
    )

    brand = db.get(Brand, brand_id)

    return brand
@router.put("/{brand_id}", response_model=BrandResponse)
def update_brand(
    brand_id: UUID,
    brand_data: BrandUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db=db,
        user_id=current_user.id,
        brand_id=brand_id,
        permission="brand:update",
    )

    brand = db.get(Brand, brand_id)

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found.",
        )

    brand.name = brand_data.name

    db.commit()
    db.refresh(brand)

    return brand
@router.delete("/{brand_id}")
def delete_brand(
    brand_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    authorize_brand_action(
        db=db,
        user_id=current_user.id,
        brand_id=brand_id,
        permission="brand:delete",
    )

    brand = db.get(Brand, brand_id)

    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found.",
        )

    db.delete(brand)
    db.commit()

    return {
        "message": "Brand deleted successfully."
    }
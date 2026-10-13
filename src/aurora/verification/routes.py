from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from aurora.store.catalog import get_apartment
from aurora.store.errors import StoreError
from aurora.store.reservations import list_reservations
from aurora.store.visitors import list_visitors

APARTMENT_NOT_FOUND = "Apartamento não encontrado."
SERVICE_UNAVAILABLE = "Serviço indisponível no momento. Tente novamente."


class ReservaOut(BaseModel):
    codigo: str
    area: str
    data: date


class VisitanteOut(BaseModel):
    nome: str
    data: date


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail=SERVICE_UNAVAILABLE)


async def require_apartment(numero: str, request: Request) -> str:
    try:
        apartment = await get_apartment(request.app.state.engine, number=numero)
    except StoreError as exc:
        raise _unavailable() from exc
    if apartment is None:
        raise HTTPException(status_code=404, detail=APARTMENT_NOT_FOUND)
    return apartment.number


router = APIRouter(prefix="/apartamentos")


@router.get("/{numero}/reservas", response_model=list[ReservaOut])
async def reservas(request: Request, numero: str = Depends(require_apartment)):
    try:
        items = await list_reservations(request.app.state.engine, apartment=numero)
    except StoreError as exc:
        raise _unavailable() from exc
    return [ReservaOut(codigo=r.code, area=r.area_id, data=r.day) for r in items]


@router.get("/{numero}/visitantes", response_model=list[VisitanteOut])
async def visitantes(request: Request, numero: str = Depends(require_apartment)):
    try:
        items = await list_visitors(request.app.state.engine, apartment=numero)
    except StoreError as exc:
        raise _unavailable() from exc
    return [VisitanteOut(nome=v.name, data=v.day) for v in items]

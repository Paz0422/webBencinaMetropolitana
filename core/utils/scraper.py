from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import requests
from django.utils import timezone

API_BASE = "https://api.bencinaenlinea.cl/api/estaciones/precios_combustibles"


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_precio(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip().replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return timezone.now()
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    except ValueError:
        return timezone.now()


def obtener_registros_normalizados(
    combustible_id: int = 3, region_id: int = 13, timeout: int = 20
) -> list[dict[str, Any]]:
    """
    Obtiene y normaliza registros del reporte comunal de Bencina en Linea.
    """
    url = f"{API_BASE}/{combustible_id}/reporte_comunal"
    params = {"cod_region[]": region_id}
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()

    payload = resp.json()
    filas = payload.get("data", [])
    extraido_en = timezone.now()
    normalizados: list[dict[str, Any]] = []

    for fila in filas:
        codigo = str(fila.get("estacion_servicio_codigo", "")).strip()
        if not codigo:
            continue

        normalizados.append(
            {
                "codigo_servicio": codigo,
                "servicio_id": _parse_int(fila.get("estacion_servicio_id"), 0) or None,
                "nombre": codigo,
                "marca": str(fila.get("marca_nombre", "")).strip(),
                "direccion": str(fila.get("estacion_direccion", "")).strip(),
                "comuna": str(fila.get("comuna_nombre", "")).strip(),
                "comuna_id": str(fila.get("comuna_id", "")).strip(),
                "region": str(fila.get("region_nombre", "")).strip(),
                "region_id": str(fila.get("region_id", "")).strip(),
                "combustible_id": _parse_int(fila.get("combustible_id"), combustible_id),
                "tipo_atencion": str(fila.get("tipo_atencion", "")).strip() or "Desconocido",
                "precio": _parse_precio(fila.get("combustible_precio")),
                "fecha_actualizacion": _parse_datetime(fila.get("fecha_actualizacion")),
                "fecha_extraccion": extraido_en,
            }
        )

    return normalizados


def extraer_tabla_prueba(combustible_id: int = 3, region_id: int = 13) -> pd.DataFrame:
    registros = obtener_registros_normalizados(combustible_id, region_id)
    if not registros:
        return pd.DataFrame()
    return pd.DataFrame(registros)
import hashlib
from bisect import bisect_left, bisect_right
from decimal import Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt
import unicodedata

import requests
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import BannerPromocional, PrecioActual

COMBUSTIBLES = {
    1: "Gasolina 93",
    2: "Gasolina 95",
    3: "Gasolina 97",
    4: "Diesel",
    5: "Kerosene",
}
COMBUSTIBLES_PRINCIPALES = {1, 2, 3, 4}
COMBUSTIBLES_CORTOS = {
    1: "93",
    2: "95",
    3: "97",
    4: "Diesel",
}
COMBUSTIBLES_MAPA = ("93", "95", "97", "Diesel")

ORDENES = {
    "precio_asc": ("precio", "fecha_actualizacion"),
    "precio_desc": ("-precio", "-fecha_actualizacion"),
    "actualizacion_desc": ("-fecha_actualizacion", "precio"),
}

MARCAS_PRIORIZADAS = ("COPEC", "SHELL", "ARAMCO")
MAPA_ESTACIONES_URL = "https://api.bencinaenlinea.cl/api/busqueda_estacion_filtro"
MAPA_MARCAS_URL = "https://api.bencinaenlinea.cl/api/marca_ciudadano"
CENTRO_RM = (-33.45, -70.66)
COORDS_COMUNA_RM = {
    "SANTIAGO": (-33.45, -70.66),
    "PROVIDENCIA": (-33.43, -70.61),
    "LAS CONDES": (-33.41, -70.57),
    "NUNOA": (-33.46, -70.60),
    "MAIPU": (-33.51, -70.76),
    "PUENTE ALTO": (-33.61, -70.58),
    "LA FLORIDA": (-33.55, -70.57),
    "SAN BERNARDO": (-33.60, -70.70),
    "PENALOLEN": (-33.49, -70.55),
    "ESTACION CENTRAL": (-33.46, -70.70),
    "QUILICURA": (-33.36, -70.73),
    "PUDAHUEL": (-33.43, -70.78),
    "RECOLETA": (-33.41, -70.65),
    "INDEPENDENCIA": (-33.42, -70.66),
    "LA CISTERNA": (-33.54, -70.66),
    "SAN MIGUEL": (-33.50, -70.66),
    "HUECHURABA": (-33.36, -70.67),
    "LO BARNECHEA": (-33.35, -70.52),
}


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def obtener_banners_activos(ubicacion: str):
    ahora = timezone.now()
    return BannerPromocional.objects.filter(
        activo=True,
        ubicacion=ubicacion,
    ).filter(
        Q(inicio_publicacion__isnull=True) | Q(inicio_publicacion__lte=ahora),
        Q(fin_publicacion__isnull=True) | Q(fin_publicacion__gte=ahora),
    )


def anotar_conveniencia(precios):
    items = list(precios)
    if not items:
        return items

    min_precio = min(Decimal(item.precio) for item in items)
    max_precio = max(Decimal(item.precio) for item in items)
    rango_precio = max_precio - min_precio
    ahora = timezone.now()

    for item in items:
        if rango_precio > 0:
            score_precio = float((max_precio - Decimal(item.precio)) / rango_precio)
        else:
            score_precio = 1.0

        fecha_actualizacion = item.fecha_actualizacion
        if isinstance(fecha_actualizacion, str):
            fecha_actualizacion = parse_datetime(fecha_actualizacion)
            if fecha_actualizacion and timezone.is_naive(fecha_actualizacion):
                fecha_actualizacion = timezone.make_aware(
                    fecha_actualizacion, timezone.get_current_timezone()
                )
        if not fecha_actualizacion:
            fecha_actualizacion = ahora
        horas_antiguedad = max(0.0, (ahora - fecha_actualizacion).total_seconds() / 3600)
        score_recencia = max(0.0, 1 - (horas_antiguedad / 48))

        item.score_conveniencia = round(((score_precio * 0.7) + (score_recencia * 0.3)) * 100, 1)


def anotar_estilo_trading(precios, precio_min, precio_max):
    if precio_min is None or precio_max is None:
        return

    min_decimal = Decimal(precio_min)
    max_decimal = Decimal(precio_max)
    rango = max_decimal - min_decimal

    for item in precios:
        valor = Decimal(item.precio)
        ratio = float((valor - min_decimal) / rango) if rango > 0 else 0.0
        hue = int(120 - (120 * ratio))  # verde barato -> rojo caro
        item.row_style = f"background-color: hsl({hue}, 85%, 92%);"
        item.spread_minimo = int(valor - min_decimal)

        if ratio <= 0.33:
            item.senal = "Compra"
            item.senal_class = "success"
        elif ratio <= 0.66:
            item.senal = "Neutral"
            item.senal_class = "warning"
        else:
            item.senal = "Caro"
            item.senal_class = "danger"


def construir_ranking_por_estacion(puntos):
    if not puntos:
        return []

    valores_por_categoria = {}
    for categoria in COMBUSTIBLES_MAPA:
        valores = sorted(
            comb["precio"]
            for punto in puntos
            for comb in punto.get("precios", [])
            if comb["nombre"] == categoria
        )
        if valores:
            valores_por_categoria[categoria] = valores

    ranking = []
    for punto in puntos:
        precios_map = {comb["nombre"]: comb["precio"] for comb in punto.get("precios", [])}
        fila = {
            "marca": punto.get("marca", ""),
            "direccion": punto.get("direccion", ""),
            "comuna": punto.get("comuna", ""),
            "precio_referencia": punto.get("precio_referencia", 0),
            "p93": precios_map.get("93"),
            "p95": precios_map.get("95"),
            "p97": precios_map.get("97"),
            "pdiesel": precios_map.get("Diesel"),
            "s93": "",
            "s95": "",
            "s97": "",
            "sdiesel": "",
        }

        for categoria, key in [("93", "s93"), ("95", "s95"), ("97", "s97"), ("Diesel", "sdiesel")]:
            valor = precios_map.get(categoria)
            valores_categoria = valores_por_categoria.get(categoria)
            if valor is None or not valores_categoria:
                continue
            left = bisect_left(valores_categoria, valor)
            right = bisect_right(valores_categoria, valor)
            pos = (left + right - 1) / 2
            total = len(valores_categoria)
            percentil = (pos / (total - 1)) if total > 1 else 0.0
            if percentil <= 0.33:
                fila[key] = "background-color: #dff4df; color: #0f5132; font-weight: 600;"  # verde (barato)
            elif percentil <= 0.66:
                fila[key] = "background-color: #ffe8cc; color: #7a4e00; font-weight: 600;"  # naranjo (medio)
            else:
                fila[key] = "background-color: #ffd9d9; color: #842029; font-weight: 600;"  # rojo (caro)

        ranking.append(fila)

    ranking.sort(key=lambda x: x["precio_referencia"])
    return ranking


def construir_ranking_desde_bd(marca: str = ""):
    mapeo_bd = _resolver_mapeo_combustible_bd()
    query = PrecioActual.objects.select_related("estacion").filter(
        combustible_id__in=COMBUSTIBLES_PRINCIPALES,
        estacion__region__icontains="metropolitana",
    )
    if marca:
        query = query.filter(estacion__marca__iexact=marca.strip())

    filas_por_estacion = {}
    for item in query:
        categoria = mapeo_bd.get(item.combustible_id)
        if categoria not in COMBUSTIBLES_MAPA:
            continue

        precio_int = int(Decimal(item.precio))
        if not _precio_valido_categoria(categoria, precio_int):
            continue

        estacion = item.estacion
        fila = filas_por_estacion.setdefault(
            estacion.id,
            {
                "marca": str(estacion.marca or "").strip().upper(),
                "direccion": str(estacion.direccion or "").strip(),
                "comuna": str(estacion.comuna or "").strip(),
                "precio_referencia": None,
                "p93": None,
                "p95": None,
                "p97": None,
                "pdiesel": None,
                "s93": "",
                "s95": "",
                "s97": "",
                "sdiesel": "",
            },
        )

        key_precio = {
            "93": "p93",
            "95": "p95",
            "97": "p97",
            "Diesel": "pdiesel",
        }[categoria]

        valor_actual = fila[key_precio]
        if valor_actual is None or precio_int < valor_actual:
            fila[key_precio] = precio_int

    ranking = list(filas_por_estacion.values())
    if not ranking:
        return []

    for fila in ranking:
        precios_disponibles = [fila["p93"], fila["p95"], fila["p97"], fila["pdiesel"]]
        precios_disponibles = [p for p in precios_disponibles if p is not None]
        fila["precio_referencia"] = min(precios_disponibles) if precios_disponibles else 0

    for categoria, key_precio, key_style in [
        ("93", "p93", "s93"),
        ("95", "p95", "s95"),
        ("97", "p97", "s97"),
        ("Diesel", "pdiesel", "sdiesel"),
    ]:
        valores = sorted(r[key_precio] for r in ranking if r[key_precio] is not None)
        if not valores:
            continue
        for fila in ranking:
            valor = fila[key_precio]
            if valor is None:
                continue
            left = bisect_left(valores, valor)
            right = bisect_right(valores, valor)
            pos = (left + right - 1) / 2
            total = len(valores)
            percentil = (pos / (total - 1)) if total > 1 else 0.0
            if percentil <= 0.33:
                fila[key_style] = "background-color: #dff4df; color: #0f5132; font-weight: 600;"
            elif percentil <= 0.66:
                fila[key_style] = "background-color: #ffe8cc; color: #7a4e00; font-weight: 600;"
            else:
                fila[key_style] = "background-color: #ffd9d9; color: #842029; font-weight: 600;"

    ranking.sort(key=lambda x: x["precio_referencia"])
    return ranking


def filtrar_y_ordenar_ranking(
    ranking,
    combustible_objetivo: str = "todos",
    comuna: str = "",
    marca: str = "",
):
    key_por_comb = {
        "93": "p93",
        "95": "p95",
        "97": "p97",
        "Diesel": "pdiesel",
    }
    selected_key = key_por_comb.get(combustible_objetivo, "")
    resultados = list(ranking)

    if marca:
        marca_f = marca.strip().upper()
        resultados = [r for r in resultados if str(r.get("marca", "")).upper() == marca_f]
    if comuna:
        comuna_f = comuna.strip().lower()
        resultados = [r for r in resultados if comuna_f in str(r.get("comuna", "")).lower()]

    if selected_key:
        resultados = [r for r in resultados if r.get(selected_key) is not None]
        resultados.sort(key=lambda x: x[selected_key])
    else:
        resultados.sort(key=lambda x: x.get("precio_referencia", 0))
    return resultados, selected_key


def construir_heatmap_comunas(combustible_id: int, marca: str = "", limite: int = 24):
    base = PrecioActual.objects.filter(
        combustible_id=combustible_id,
    )
    if marca:
        base = base.filter(estacion__marca__iexact=marca.strip())

    data = list(
        base.values("estacion__comuna")
        .annotate(precio_promedio=Avg("precio"), estaciones=Count("id"))
        .order_by("precio_promedio", "estacion__comuna")[:limite]
    )
    if not data:
        return []

    min_avg = min(Decimal(item["precio_promedio"]) for item in data)
    max_avg = max(Decimal(item["precio_promedio"]) for item in data)
    rango = max_avg - min_avg

    for item in data:
        promedio = Decimal(item["precio_promedio"])
        posicion = float((promedio - min_avg) / rango) if rango > 0 else 0.0
        hue = int(120 - (120 * posicion))  # verde barato -> rojo caro
        item["hue"] = hue
        item["precio_promedio"] = round(float(promedio), 0)
        item["comuna"] = item["estacion__comuna"]

    return data


def _parse_decimal_or_none(value):
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_float_or_none(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalizar_categoria_mapa(nombre_corto: str, nombre_largo: str) -> str | None:
    corto = str(nombre_corto or "").strip().upper()
    largo = str(nombre_largo or "").strip().upper()

    if corto in {"93", "A93"} or "GASOLINA 93" in largo:
        return "93"
    if corto in {"95", "A95"} or "GASOLINA 95" in largo:
        return "95"
    if corto in {"97", "A97"} or "GASOLINA 97" in largo:
        return "97"
    if corto in {"DI", "ADI"} or "DIESEL" in largo or "PETROLEO DIESEL" in largo:
        return "Diesel"
    return None


def _normalizar_precios_estacion(mejor_por_categoria: dict):
    requeridos = ("93", "95", "97", "Diesel")
    if not all(cat in mejor_por_categoria for cat in requeridos):
        return mejor_por_categoria

    p93 = mejor_por_categoria["93"]["precio"]
    p95 = mejor_por_categoria["95"]["precio"]
    p97 = mejor_por_categoria["97"]["precio"]
    pdiesel = mejor_por_categoria["Diesel"]["precio"]

    # Caso normal: mantener datos tal cual.
    if p93 <= p95 <= p97 and pdiesel <= p97:
        return mejor_por_categoria

    # Correccion defensiva para cruces evidentes en el proveedor:
    # Diesel suele ser el menor y gasolinas van 93 <= 95 <= 97.
    pares = sorted(
        ((cat, data["precio"]) for cat, data in mejor_por_categoria.items() if cat in requeridos),
        key=lambda x: x[1],
    )
    if len(pares) != 4:
        return mejor_por_categoria

    nuevo = {}
    diesel_src = pares[0][0]
    nuevo["Diesel"] = {
        "id": mejor_por_categoria[diesel_src]["id"],
        "nombre": "Diesel",
        "precio": pares[0][1],
    }
    for target, (src_cat, precio) in zip(("93", "95", "97"), pares[1:]):
        nuevo[target] = {
            "id": mejor_por_categoria[src_cat]["id"],
            "nombre": target,
            "precio": precio,
        }
    return nuevo


def _precio_valido_categoria(categoria: str, precio: int) -> bool:
    # Evita outliers/errores de carga (ej: 121 en gasolina).
    if categoria in {"93", "95", "97", "Diesel"}:
        return 500 <= precio <= 3000
    return False


def _distancia_km(lat1, lon1, lat2, lon2):
    radio_tierra_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * radio_tierra_km * asin(sqrt(a))


def _coordenadas_aproximadas_comuna(comuna: str, semilla: str):
    comuna_key = unicodedata.normalize("NFKD", str(comuna or "").strip().upper())
    comuna_key = "".join(ch for ch in comuna_key if not unicodedata.combining(ch))
    base_lat, base_lon = COORDS_COMUNA_RM.get(comuna_key, CENTRO_RM)
    digest = hashlib.md5(str(semilla).encode("utf-8")).hexdigest()
    lat_raw = int(digest[:8], 16) / 0xFFFFFFFF
    lon_raw = int(digest[8:16], 16) / 0xFFFFFFFF

    # Jitter pequeno para separar puntos dentro de una misma comuna.
    lat_offset = (lat_raw - 0.5) * 0.035
    lon_offset = (lon_raw - 0.5) * 0.045
    return (round(base_lat + lat_offset, 6), round(base_lon + lon_offset, 6))


def _anotar_score_mapa(puntos):
    if not puntos:
        return []

    # Comparar por categoria y luego promediar (evita mezclar diesel con gasolinas).
    stats_por_categoria = {}
    for categoria in COMBUSTIBLES_MAPA:
        valores = [
            comb["precio"]
            for punto in puntos
            for comb in punto["precios"]
            if comb["nombre"] == categoria
        ]
        if valores:
            stats_por_categoria[categoria] = {"min": min(valores), "max": max(valores)}

    for p in puntos:
        scores = []
        for comb in p["precios"]:
            stats = stats_por_categoria.get(comb["nombre"])
            if not stats:
                continue
            rango = stats["max"] - stats["min"]
            if rango > 0:
                score = (stats["max"] - comb["precio"]) / rango  # 1=barato, 0=caro
            else:
                score = 1.0
            scores.append(score)

        p["_score_bruto"] = (sum(scores) / len(scores)) if scores else 0.5

    # Normalizar por percentil para evitar sesgo visual por outliers.
    # Asi la escala de colores se reparte mejor entre todas las estaciones.
    ordenados = sorted(puntos, key=lambda x: x.get("_score_bruto", 0.5))
    total = len(ordenados)
    for idx, p in enumerate(ordenados):
        if total > 1:
            score_percentil = idx / (total - 1)
        else:
            score_percentil = 0.5
        p["score_mapa"] = round(score_percentil, 3)
        p["hue"] = int(120 * score_percentil)  # 120 verde, 0 rojo
        p.pop("_score_bruto", None)
    for idx, p in enumerate(puntos):
        p["point_id"] = idx
    return puntos


def filtrar_puntos_por_cercania(puntos, comuna: str, radio_km: float = 6.0):
    if not comuna:
        return puntos, []

    comuna_busqueda = comuna.strip().lower()
    puntos_objetivo = [p for p in puntos if comuna_busqueda in p["comuna"].lower()]
    if not puntos_objetivo:
        return puntos, []

    centro_lat = sum(p["latitud"] for p in puntos_objetivo) / len(puntos_objetivo)
    centro_lon = sum(p["longitud"] for p in puntos_objetivo) / len(puntos_objetivo)

    puntos_cercanos = [
        p
        for p in puntos
        if _distancia_km(centro_lat, centro_lon, p["latitud"], p["longitud"]) <= radio_km
    ]
    comunas_cercanas = sorted(set(p["comuna"] for p in puntos_cercanos))
    return puntos_cercanos, comunas_cercanas


def _resolver_mapeo_combustible_bd():
    mapeo_default = dict(COMBUSTIBLES_CORTOS)
    stats = (
        PrecioActual.objects.filter(combustible_id__in=COMBUSTIBLES_PRINCIPALES)
        .values("combustible_id")
        .annotate(promedio=Avg("precio"))
    )
    promedio_por_id = {
        int(row["combustible_id"]): float(row["promedio"])
        for row in stats
        if row.get("promedio") is not None
    }
    if len(promedio_por_id) < 2:
        return mapeo_default

    ids_ordenados = sorted(promedio_por_id, key=lambda comb_id: promedio_por_id[comb_id])
    diesel_id = ids_ordenados[0]
    gasolina_ids = [comb_id for comb_id in ids_ordenados if comb_id != diesel_id]

    mapeo_detectado = {diesel_id: "Diesel"}
    if len(gasolina_ids) >= 1:
        mapeo_detectado[gasolina_ids[0]] = "93"
    if len(gasolina_ids) >= 2:
        mapeo_detectado[gasolina_ids[1]] = "95"
    if len(gasolina_ids) >= 3:
        mapeo_detectado[gasolina_ids[2]] = "97"

    for comb_id, nombre in mapeo_default.items():
        mapeo_detectado.setdefault(comb_id, nombre)
    return mapeo_detectado


def obtener_puntos_mapa(combustible_id: int | None = None, marca: str = "", limite: int = 1200):
    try:
        estaciones = requests.get(MAPA_ESTACIONES_URL, timeout=25).json().get("data", [])
        catalogo_marcas = requests.get(MAPA_MARCAS_URL, timeout=25).json().get("data", [])
    except Exception:
        return []

    marcas_por_id = {
        item.get("id"): str(item.get("nombre", "")).strip().upper() for item in catalogo_marcas
    }
    marca_filtro = marca.strip().upper()
    puntos = []

    for estacion in estaciones:
        region_nombre = str(estacion.get("region", "")).strip().lower()
        if "metropolitana" not in region_nombre:
            continue

        marca_nombre = marcas_por_id.get(estacion.get("marca"), "")
        if marca_filtro and marca_nombre != marca_filtro:
            continue

        combustibles_disponibles = []
        mejor_por_categoria = {}
        for comb in estacion.get("combustibles", []):
            if int(comb.get("suministra", 0)) != 1:
                continue
            comb_id = int(comb.get("id", 0))
            precio_comb = _parse_decimal_or_none(comb.get("precio"))
            if precio_comb is None:
                continue

            categoria = _normalizar_categoria_mapa(
                comb.get("nombre_corto", ""),
                comb.get("nombre_largo", ""),
            )
            if categoria is None:
                continue

            # Para cada categoria quedarnos con el menor precio de la estacion.
            precio_int = int(precio_comb)
            if not _precio_valido_categoria(categoria, precio_int):
                continue
            if categoria not in mejor_por_categoria or precio_int < mejor_por_categoria[categoria]["precio"]:
                mejor_por_categoria[categoria] = {
                    "id": comb_id,
                    "nombre": categoria,
                    "precio": precio_int,
                }

        mejor_por_categoria = _normalizar_precios_estacion(mejor_por_categoria)
        combustibles_disponibles = [mejor_por_categoria[k] for k in COMBUSTIBLES_MAPA if k in mejor_por_categoria]
        if not combustibles_disponibles:
            continue

        latitud = _parse_float_or_none(estacion.get("latitud"))
        longitud = _parse_float_or_none(estacion.get("longitud"))
        if latitud is None or longitud is None:
            continue
        precio_referencia = min(item["precio"] for item in combustibles_disponibles)

        puntos.append(
            {
                "estacion_id": estacion.get("id"),
                "marca": marca_nombre,
                "direccion": str(estacion.get("direccion", "")).strip(),
                "comuna": str(estacion.get("comuna", "")).strip(),
                "latitud": latitud,
                "longitud": longitud,
                "precio_referencia": precio_referencia,
                "precios": combustibles_disponibles,
            }
        )

    puntos = puntos[:limite]
    return _anotar_score_mapa(puntos)


def obtener_puntos_mapa_desde_bd(marca: str = "", limite: int = 1200):
    mapeo_bd = _resolver_mapeo_combustible_bd()
    query = (
        PrecioActual.objects.select_related("estacion")
        .filter(
            combustible_id__in=COMBUSTIBLES_PRINCIPALES,
            estacion__region__icontains="metropolitana",
        )
        .order_by("estacion_id", "precio")
    )
    if marca:
        query = query.filter(estacion__marca__iexact=marca.strip())

    puntos_por_estacion = {}
    for item in query:
        categoria = mapeo_bd.get(item.combustible_id)
        if categoria not in COMBUSTIBLES_MAPA:
            continue

        precio_int = int(Decimal(item.precio))
        if not _precio_valido_categoria(categoria, precio_int):
            continue

        estacion = item.estacion
        latitud = _parse_float_or_none(estacion.latitud)
        longitud = _parse_float_or_none(estacion.longitud)
        if latitud is None or longitud is None:
            latitud, longitud = _coordenadas_aproximadas_comuna(
                estacion.comuna,
                f"{estacion.id}-{estacion.direccion}-{estacion.marca}",
            )

        punto = puntos_por_estacion.setdefault(
            estacion.id,
            {
                "estacion_id": estacion.id,
                "marca": str(estacion.marca).strip().upper(),
                "direccion": str(estacion.direccion).strip(),
                "comuna": str(estacion.comuna).strip(),
                "latitud": latitud,
                "longitud": longitud,
                "_mejor_por_categoria": {},
            },
        )

        mejor = punto["_mejor_por_categoria"].get(categoria)
        if mejor is None or precio_int < mejor["precio"]:
            punto["_mejor_por_categoria"][categoria] = {
                "id": int(item.combustible_id),
                "nombre": categoria,
                "precio": precio_int,
            }

    puntos = []
    for punto in puntos_por_estacion.values():
        punto["_mejor_por_categoria"] = _normalizar_precios_estacion(punto["_mejor_por_categoria"])
        precios = [
            punto["_mejor_por_categoria"][cat]
            for cat in COMBUSTIBLES_MAPA
            if cat in punto["_mejor_por_categoria"]
        ]
        if not precios:
            continue

        punto["precios"] = precios
        punto["precio_referencia"] = min(p["precio"] for p in precios)
        punto.pop("_mejor_por_categoria", None)
        puntos.append(punto)

    puntos.sort(key=lambda x: x["precio_referencia"])
    puntos = puntos[:limite]
    return _anotar_score_mapa(puntos)


def obtener_top_precios(
    comuna: str,
    combustible_id: int | None = None,
    marca: str = "",
    orden: str = "precio_asc",
    comunas_cercanas: list[str] | None = None,
):
    query = PrecioActual.objects.select_related("estacion").filter(
        estacion__region__icontains="metropolitana",
        combustible_id__in=COMBUSTIBLES_PRINCIPALES,
    )
    if combustible_id is not None:
        query = query.filter(combustible_id=combustible_id)
    if comunas_cercanas:
        query = query.filter(estacion__comuna__in=comunas_cercanas)
    elif comuna:
        query = query.filter(estacion__comuna__icontains=comuna.strip())
    if marca:
        query = query.filter(estacion__marca__iexact=marca.strip())
    return query.order_by(*ORDENES.get(orden, ORDENES["precio_asc"]))


def listado_estaciones(request):
    comuna = request.GET.get("comuna", "")
    pagina = _parse_int(request.GET.get("page", "1"), 1)
    marca = request.GET.get("marca", "")
    combustible_lista = request.GET.get("combustible_lista", "todos")
    per_page = _parse_int(request.GET.get("per_page", "25"), 25)
    if per_page not in {25, 50, 100}:
        per_page = 25
    if combustible_lista not in COMBUSTIBLES_MAPA and combustible_lista != "todos":
        combustible_lista = "todos"

    # Mapa sin filtros de usuario.
    puntos_mapa = obtener_puntos_mapa(combustible_id=None, marca="")
    if not puntos_mapa:
        # Fallback: si la API externa falla, usar datos locales para no dejar vacio el listado.
        puntos_mapa = obtener_puntos_mapa_desde_bd(marca="")

    ranking_base = construir_ranking_por_estacion(puntos_mapa)
    if not ranking_base:
        # Mantener tabla operativa aunque falle la API del mapa.
        ranking_base = construir_ranking_desde_bd(marca="")
    comunas_disponibles = sorted(set(r["comuna"] for r in ranking_base))
    ranking_estaciones, selected_key = filtrar_y_ordenar_ranking(
        ranking_base,
        combustible_objetivo=combustible_lista,
        comuna=comuna,
        marca=marca,
    )

    paginator = Paginator(ranking_estaciones, per_page)
    estaciones = paginator.get_page(pagina)

    marcas_disponibles = sorted(set(r["marca"] for r in ranking_base if r.get("marca")))

    valores_categoria = [r[selected_key] for r in ranking_estaciones if r.get(selected_key) is not None]
    promedio_precio = (
        round(sum(valores_categoria) / len(valores_categoria), 0) if valores_categoria else None
    )

    contexto = {
        "estaciones": estaciones,
        "filtros": {
            "comuna": comuna,
            "marca": marca,
            "combustible_lista": combustible_lista,
            "per_page": per_page,
        },
        "promedio_precio": promedio_precio,
        "precio_minimo": (min(valores_categoria) if valores_categoria else None),
        "precio_maximo": (max(valores_categoria) if valores_categoria else None),
        "marcas_disponibles": marcas_disponibles,
        "comunas_disponibles": comunas_disponibles,
        "combustibles_lista": COMBUSTIBLES_MAPA,
        "selected_key": selected_key,
        "marcas_priorizadas": MARCAS_PRIORIZADAS,
        "puntos_mapa": puntos_mapa,
        "banners_superiores": obtener_banners_activos(BannerPromocional.Ubicacion.SUPERIOR),
        "banners_inferiores": obtener_banners_activos(BannerPromocional.Ubicacion.INFERIOR),
    }
    return render(request, "lista.html", contexto)
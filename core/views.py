from decimal import Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt

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

    stats_por_categoria = {}
    for categoria in COMBUSTIBLES_MAPA:
        valores = [
            comb["precio"]
            for punto in puntos
            for comb in punto.get("precios", [])
            if comb["nombre"] == categoria
        ]
        if valores:
            stats_por_categoria[categoria] = {"min": min(valores), "max": max(valores)}

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
            stats = stats_por_categoria.get(categoria)
            if valor is None or not stats:
                continue
            rango = stats["max"] - stats["min"]
            ratio = ((valor - stats["min"]) / rango) if rango > 0 else 0.0
            if ratio <= 0.33:
                fila[key] = "background-color: #dff4df; color: #0f5132; font-weight: 600;"  # verde (barato)
            elif ratio <= 0.66:
                fila[key] = "background-color: #ffe8cc; color: #7a4e00; font-weight: 600;"  # naranjo (medio)
            else:
                fila[key] = "background-color: #ffd9d9; color: #842029; font-weight: 600;"  # rojo (caro)

        ranking.append(fila)

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
        estacion__marca__in=MARCAS_PRIORIZADAS,
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


def obtener_puntos_mapa(combustible_id: int | None = None, marca: str = "", limite: int = 500):
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
        if marca_nombre not in MARCAS_PRIORIZADAS:
            continue
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

        score_promedio = (sum(scores) / len(scores)) if scores else 0.5
        p["score_mapa"] = round(score_promedio, 3)
        p["hue"] = int(120 * score_promedio)  # 120 verde, 0 rojo
    for idx, p in enumerate(puntos):
        p["point_id"] = idx
    return puntos


def obtener_top_precios(
    comuna: str,
    combustible_id: int | None = None,
    marca: str = "",
    orden: str = "precio_asc",
    comunas_cercanas: list[str] | None = None,
):
    query = PrecioActual.objects.select_related("estacion").filter(
        estacion__marca__in=MARCAS_PRIORIZADAS,
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

    ranking_base = construir_ranking_por_estacion(puntos_mapa)
    comunas_disponibles = sorted(set(r["comuna"] for r in ranking_base))
    ranking_estaciones, selected_key = filtrar_y_ordenar_ranking(
        ranking_base,
        combustible_objetivo=combustible_lista,
        comuna=comuna,
        marca=marca,
    )

    paginator = Paginator(ranking_estaciones, per_page)
    estaciones = paginator.get_page(pagina)

    marcas_disponibles = [m for m in MARCAS_PRIORIZADAS]

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
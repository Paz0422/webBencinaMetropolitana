from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from unittest.mock import Mock, patch

from core.models import BannerPromocional, Estacion, PrecioActual
from core.utils.scraper import obtener_registros_normalizados
from core.views import (
    anotar_conveniencia,
    construir_heatmap_comunas,
    filtrar_puntos_por_cercania,
    obtener_banners_activos,
    obtener_puntos_mapa,
    obtener_top_precios,
)


class ScraperNormalizerTests(TestCase):
    @patch("core.utils.scraper.requests.get")
    def test_obtener_registros_normalizados(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "estacion_servicio_codigo": "co1320109",
                    "estacion_servicio_id": 2236,
                    "marca_nombre": "COPEC",
                    "estacion_direccion": "Av. Demo 123",
                    "comuna_nombre": "Puente Alto",
                    "comuna_id": "13201",
                    "region_nombre": "Metropolitana de Santiago",
                    "region_id": "13",
                    "combustible_id": 3,
                    "tipo_atencion": "Asistido",
                    "combustible_precio": "839.000",
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        registros = obtener_registros_normalizados(combustible_id=3, region_id=13)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["codigo_servicio"], "co1320109")
        self.assertEqual(str(registros[0]["precio"]), "839.000")


class QueryMvpTests(TestCase):
    def test_obtener_top_precios_por_comuna(self):
        estacion = Estacion.objects.create(
            codigo_servicio="co1320109",
            marca="COPEC",
            nombre="co1320109",
            direccion="Av. Demo 123",
            comuna="Puente Alto",
            comuna_id="13201",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="839.000",
            fecha_actualizacion="2026-03-25T12:00:00Z",
        )

        resultados = obtener_top_precios(comuna="Puente Alto", combustible_id=3)
        self.assertEqual(resultados.count(), 1)

    def test_obtener_top_precios_con_filtro_marca(self):
        estacion = Estacion.objects.create(
            codigo_servicio="sh1320110",
            marca="SHELL",
            nombre="sh1320110",
            direccion="Av. Demo 456",
            comuna="Puente Alto",
            comuna_id="13201",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion,
            combustible_id=3,
            tipo_atencion="Autoservicio",
            precio="830.000",
            fecha_actualizacion="2026-03-25T13:00:00Z",
        )

        resultados = obtener_top_precios(
            comuna="Puente Alto",
            combustible_id=3,
            marca="SHELL",
        )
        self.assertEqual(resultados.count(), 1)

    def test_obtener_top_precios_orden_precio_desc(self):
        estacion_1 = Estacion.objects.create(
            codigo_servicio="co1320109a",
            marca="COPEC",
            nombre="co1320109a",
            direccion="Av. Demo 1",
            comuna="Puente Alto",
            comuna_id="13201",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        estacion_2 = Estacion.objects.create(
            codigo_servicio="co1320109b",
            marca="COPEC",
            nombre="co1320109b",
            direccion="Av. Demo 2",
            comuna="Puente Alto",
            comuna_id="13201",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion_1,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="800.000",
            fecha_actualizacion="2026-03-25T12:00:00Z",
        )
        PrecioActual.objects.create(
            estacion=estacion_2,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="900.000",
            fecha_actualizacion="2026-03-25T12:00:00Z",
        )

        resultados = list(
            obtener_top_precios(
                comuna="Puente Alto", combustible_id=3, orden="precio_desc"
            )[:2]
        )
        self.assertEqual(str(resultados[0].precio), "900.000")

    def test_obtener_top_precios_excluye_marcas_no_priorizadas(self):
        estacion = Estacion.objects.create(
            codigo_servicio="pe1320999",
            marca="PETROBRAS",
            nombre="pe1320999",
            direccion="Av. Demo 99",
            comuna="Puente Alto",
            comuna_id="13201",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="700.000",
            fecha_actualizacion="2026-03-25T14:00:00Z",
        )

        resultados = obtener_top_precios(comuna="Puente Alto", combustible_id=3)
        self.assertEqual(resultados.count(), 0)

    def test_obtener_top_precios_comuna_icontains(self):
        estacion = Estacion.objects.create(
            codigo_servicio="co1320200",
            marca="COPEC",
            nombre="co1320200",
            direccion="Av. Demo 200",
            comuna="La Cisterna",
            comuna_id="13102",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="910.000",
            fecha_actualizacion="2026-03-25T14:30:00Z",
        )

        resultados = obtener_top_precios(comuna="cisterna", combustible_id=3)
        self.assertEqual(resultados.count(), 1)

    def test_anotar_conveniencia_agrega_score(self):
        estacion_1 = Estacion.objects.create(
            codigo_servicio="co1320300",
            marca="COPEC",
            nombre="co1320300",
            direccion="Av. Demo 300",
            comuna="La Cisterna",
            comuna_id="13102",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        estacion_2 = Estacion.objects.create(
            codigo_servicio="sh1320301",
            marca="SHELL",
            nombre="sh1320301",
            direccion="Av. Demo 301",
            comuna="La Cisterna",
            comuna_id="13102",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        p1 = PrecioActual.objects.create(
            estacion=estacion_1,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="900.000",
            fecha_actualizacion="2026-03-25T14:00:00Z",
        )
        p2 = PrecioActual.objects.create(
            estacion=estacion_2,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="950.000",
            fecha_actualizacion="2026-03-25T14:00:00Z",
        )

        items = [p1, p2]
        anotar_conveniencia(items)
        self.assertTrue(hasattr(items[0], "score_conveniencia"))
        self.assertGreater(items[0].score_conveniencia, items[1].score_conveniencia)

    def test_construir_heatmap_comunas(self):
        estacion = Estacion.objects.create(
            codigo_servicio="ar1320400",
            marca="ARAMCO",
            nombre="ar1320400",
            direccion="Av. Demo 400",
            comuna="La Cisterna",
            comuna_id="13102",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        PrecioActual.objects.create(
            estacion=estacion,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="905.000",
            fecha_actualizacion="2026-03-25T15:00:00Z",
        )

        heatmap = construir_heatmap_comunas(combustible_id=3, marca="ARAMCO")
        self.assertEqual(len(heatmap), 1)
        self.assertEqual(heatmap[0]["comuna"], "La Cisterna")
        self.assertGreaterEqual(heatmap[0]["hue"], 0)
        self.assertLessEqual(heatmap[0]["hue"], 120)

    @patch("core.views.requests.get")
    def test_obtener_puntos_mapa_filtra_marcas_priorizadas(self, mock_get):
        resp_estaciones = Mock()
        resp_estaciones.json.return_value = {
            "data": [
                {
                    "marca": 1,
                    "region": "Metropolitana de Santiago",
                    "direccion": "Av 1",
                    "latitud": "-33.45",
                    "longitud": "-70.66",
                    "comuna": "La Cisterna",
                    "combustibles": [
                        {
                            "id": 1,
                            "suministra": 1,
                            "precio": "910.000",
                            "nombre_corto": "93",
                            "nombre_largo": "Gasolina 93",
                        }
                    ],
                },
                {
                    "marca": 2,
                    "region": "Metropolitana de Santiago",
                    "direccion": "Av 2",
                    "latitud": "-33.40",
                    "longitud": "-70.60",
                    "comuna": "La Cisterna",
                    "combustibles": [
                        {
                            "id": 1,
                            "suministra": 1,
                            "precio": "890.000",
                            "nombre_corto": "93",
                            "nombre_largo": "Gasolina 93",
                        }
                    ],
                },
            ]
        }
        resp_marcas = Mock()
        resp_marcas.json.return_value = {
            "data": [
                {"id": 1, "nombre": "COPEC"},
                {"id": 2, "nombre": "OTRA"},
            ]
        }
        mock_get.side_effect = [resp_estaciones, resp_marcas]

        puntos = obtener_puntos_mapa(combustible_id=None)
        self.assertEqual(len(puntos), 1)
        self.assertEqual(puntos[0]["marca"], "COPEC")
        self.assertEqual(puntos[0]["precio_referencia"], 910)

    @patch("core.views.requests.get")
    def test_obtener_puntos_mapa_solo_region_metropolitana(self, mock_get):
        resp_estaciones = Mock()
        resp_estaciones.json.return_value = {
            "data": [
                {
                    "marca": 1,
                    "region": "Metropolitana de Santiago",
                    "direccion": "Av RM",
                    "latitud": "-33.45",
                    "longitud": "-70.66",
                    "comuna": "Santiago",
                    "combustibles": [
                        {
                            "id": 1,
                            "suministra": 1,
                            "precio": "920.000",
                            "nombre_corto": "93",
                            "nombre_largo": "Gasolina 93",
                        }
                    ],
                },
                {
                    "marca": 1,
                    "region": "Valparaiso",
                    "direccion": "Av V",
                    "latitud": "-33.03",
                    "longitud": "-71.55",
                    "comuna": "Valparaiso",
                    "combustibles": [
                        {
                            "id": 1,
                            "suministra": 1,
                            "precio": "900.000",
                            "nombre_corto": "93",
                            "nombre_largo": "Gasolina 93",
                        }
                    ],
                },
            ]
        }
        resp_marcas = Mock()
        resp_marcas.json.return_value = {"data": [{"id": 1, "nombre": "COPEC"}]}
        mock_get.side_effect = [resp_estaciones, resp_marcas]

        puntos = obtener_puntos_mapa(combustible_id=None)
        self.assertEqual(len(puntos), 1)
        self.assertEqual(puntos[0]["comuna"], "Santiago")

    @patch("core.views.requests.get")
    def test_obtener_puntos_mapa_incluye_todos_los_precios_en_popup(self, mock_get):
        resp_estaciones = Mock()
        resp_estaciones.json.return_value = {
            "data": [
                {
                    "marca": 1,
                    "region": "Metropolitana de Santiago",
                    "direccion": "Av RM",
                    "latitud": "-33.45",
                    "longitud": "-70.66",
                    "comuna": "Santiago",
                    "combustibles": [
                        {
                            "id": 1,
                            "suministra": 1,
                            "precio": "940.000",
                            "nombre_corto": "93",
                            "nombre_largo": "Gasolina 93",
                        },
                        {
                            "id": 2,
                            "suministra": 1,
                            "precio": "980.000",
                            "nombre_corto": "97",
                            "nombre_largo": "Gasolina 97",
                        },
                    ],
                }
            ]
        }
        resp_marcas = Mock()
        resp_marcas.json.return_value = {"data": [{"id": 1, "nombre": "COPEC"}]}
        mock_get.side_effect = [resp_estaciones, resp_marcas]

        puntos = obtener_puntos_mapa(combustible_id=None)
        self.assertEqual(len(puntos), 1)
        self.assertEqual(len(puntos[0]["precios"]), 2)
        self.assertEqual(puntos[0]["precio_referencia"], 940)

    @patch("core.views.requests.get")
    def test_obtener_puntos_mapa_descarta_outlier_en_gasolina(self, mock_get):
        resp_estaciones = Mock()
        resp_estaciones.json.return_value = {
            "data": [
                {
                    "marca": 1,
                    "region": "Metropolitana de Santiago",
                    "direccion": "Av Demo Outlier",
                    "latitud": "-33.45",
                    "longitud": "-70.66",
                    "comuna": "Santiago",
                    "combustibles": [
                        {"id": 7, "suministra": 1, "precio": "1236.000", "nombre_corto": "95", "nombre_largo": "Gasolina 95"},
                        {"id": 9, "suministra": 1, "precio": "121.000", "nombre_corto": "A95", "nombre_largo": "Gasolina 95"},
                    ],
                }
            ]
        }
        resp_marcas = Mock()
        resp_marcas.json.return_value = {"data": [{"id": 1, "nombre": "COPEC"}]}
        mock_get.side_effect = [resp_estaciones, resp_marcas]

        puntos = obtener_puntos_mapa(combustible_id=None)
        self.assertEqual(len(puntos), 1)
        precios = {p["nombre"]: p["precio"] for p in puntos[0]["precios"]}
        self.assertEqual(precios["95"], 1236)

    def test_filtrar_puntos_por_cercania_incluye_comunas_vecinas(self):
        puntos = [
            {"comuna": "La Cisterna", "latitud": -33.53, "longitud": -70.66},
            {"comuna": "San Miguel", "latitud": -33.50, "longitud": -70.66},
            {"comuna": "Huechuraba", "latitud": -33.36, "longitud": -70.67},
        ]
        puntos_filtrados, comunas = filtrar_puntos_por_cercania(
            puntos, comuna="cisterna", radio_km=6.0
        )
        self.assertEqual(len(puntos_filtrados), 2)
        self.assertIn("La Cisterna", comunas)
        self.assertIn("San Miguel", comunas)

    def test_obtener_top_precios_limita_region_metropolitana(self):
        estacion_rm = Estacion.objects.create(
            codigo_servicio="co1320900",
            marca="COPEC",
            nombre="co1320900",
            direccion="Av RM 900",
            comuna="Santiago",
            comuna_id="13101",
            region="Metropolitana de Santiago",
            region_id="13",
        )
        estacion_otra = Estacion.objects.create(
            codigo_servicio="co050900",
            marca="COPEC",
            nombre="co050900",
            direccion="Av V 900",
            comuna="Valparaiso",
            comuna_id="05101",
            region="Valparaiso",
            region_id="5",
        )
        PrecioActual.objects.create(
            estacion=estacion_rm,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="910.000",
            fecha_actualizacion="2026-03-25T15:30:00Z",
        )
        PrecioActual.objects.create(
            estacion=estacion_otra,
            combustible_id=3,
            tipo_atencion="Asistido",
            precio="800.000",
            fecha_actualizacion="2026-03-25T15:30:00Z",
        )

        resultados = obtener_top_precios(comuna="", combustible_id=None)
        self.assertEqual(resultados.count(), 1)
        self.assertEqual(resultados.first().estacion.region, "Metropolitana de Santiago")


class BannersTests(TestCase):
    def test_obtener_banners_activos_filtra_por_fechas_y_estado(self):
        ahora = timezone.now()
        base_count = obtener_banners_activos(BannerPromocional.Ubicacion.SUPERIOR).count()
        BannerPromocional.objects.create(
            titulo="Promo activa",
            descripcion="Descuento premium",
            ubicacion=BannerPromocional.Ubicacion.SUPERIOR,
            activo=True,
            inicio_publicacion=ahora - timedelta(hours=1),
            fin_publicacion=ahora + timedelta(hours=1),
        )
        BannerPromocional.objects.create(
            titulo="Promo expirada",
            descripcion="No deberia salir",
            ubicacion=BannerPromocional.Ubicacion.SUPERIOR,
            activo=True,
            fin_publicacion=ahora - timedelta(hours=2),
        )
        BannerPromocional.objects.create(
            titulo="Promo inactiva",
            descripcion="No deberia salir",
            ubicacion=BannerPromocional.Ubicacion.SUPERIOR,
            activo=False,
        )

        activos = list(obtener_banners_activos(BannerPromocional.Ubicacion.SUPERIOR))
        titulos = {b.titulo for b in activos}
        self.assertEqual(len(activos), base_count + 1)
        self.assertIn("Promo activa", titulos)
        self.assertNotIn("Promo expirada", titulos)
        self.assertNotIn("Promo inactiva", titulos)

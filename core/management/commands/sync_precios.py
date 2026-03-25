from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Estacion, PrecioActual, PrecioHistorico
from core.utils.scraper import obtener_registros_normalizados


class Command(BaseCommand):
    help = "Sincroniza precios oficiales de bencina por region/combustible."

    def add_arguments(self, parser):
        parser.add_argument("--region", type=int, required=True, help="ID de region")
        parser.add_argument(
            "--combustible", type=int, required=True, help="ID de combustible"
        )

    def handle(self, *args, **options):
        region_id = options["region"]
        combustible_id = options["combustible"]
        resumen = {
            "total": 0,
            "estaciones_creadas": 0,
            "estaciones_actualizadas": 0,
            "precios_actuales_creados": 0,
            "precios_actuales_actualizados": 0,
            "historicos_creados": 0,
            "errores": 0,
        }

        try:
            registros = obtener_registros_normalizados(
                combustible_id=combustible_id, region_id=region_id
            )
        except Exception as exc:  # pragma: no cover - error externo de red/API
            self.stderr.write(self.style.ERROR(f"Error al extraer datos: {exc}"))
            return

        resumen["total"] = len(registros)

        for registro in registros:
            try:
                with transaction.atomic():
                    estacion, creada = Estacion.objects.update_or_create(
                        codigo_servicio=registro["codigo_servicio"],
                        defaults={
                            "servicio_id": registro["servicio_id"],
                            "nombre": registro["nombre"],
                            "marca": registro["marca"],
                            "direccion": registro["direccion"],
                            "comuna": registro["comuna"],
                            "comuna_id": registro["comuna_id"],
                            "region": registro["region"],
                            "region_id": registro["region_id"],
                        },
                    )
                    if creada:
                        resumen["estaciones_creadas"] += 1
                    else:
                        resumen["estaciones_actualizadas"] += 1

                    precio_actual, precio_creado = PrecioActual.objects.update_or_create(
                        estacion=estacion,
                        combustible_id=registro["combustible_id"],
                        tipo_atencion=registro["tipo_atencion"],
                        defaults={
                            "precio": registro["precio"],
                            "fecha_actualizacion": registro["fecha_actualizacion"],
                        },
                    )
                    if precio_creado:
                        resumen["precios_actuales_creados"] += 1
                    else:
                        resumen["precios_actuales_actualizados"] += 1

                    ultimo_historico = (
                        PrecioHistorico.objects.filter(
                            estacion=estacion,
                            combustible_id=registro["combustible_id"],
                            tipo_atencion=registro["tipo_atencion"],
                        )
                        .order_by("-fecha_actualizacion", "-id")
                        .first()
                    )
                    historico_creado = False
                    if not ultimo_historico or ultimo_historico.precio != precio_actual.precio:
                        _, historico_creado = PrecioHistorico.objects.get_or_create(
                            estacion=estacion,
                            combustible_id=registro["combustible_id"],
                            tipo_atencion=registro["tipo_atencion"],
                            fecha_actualizacion=registro["fecha_actualizacion"],
                            defaults={"precio": precio_actual.precio},
                        )
                    if historico_creado:
                        resumen["historicos_creados"] += 1
            except Exception as exc:
                resumen["errores"] += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Registro omitido {registro.get('codigo_servicio', 'sin_codigo')}: {exc}"
                    )
                )

        self.stdout.write(self.style.SUCCESS("Sincronizacion finalizada"))
        self.stdout.write(f"Total recibidos: {resumen['total']}")
        self.stdout.write(
            f"Estaciones creadas/actualizadas: "
            f"{resumen['estaciones_creadas']}/{resumen['estaciones_actualizadas']}"
        )
        self.stdout.write(
            f"Precios actuales creados/actualizados: "
            f"{resumen['precios_actuales_creados']}/{resumen['precios_actuales_actualizados']}"
        )
        self.stdout.write(f"Historicos creados: {resumen['historicos_creados']}")
        self.stdout.write(f"Errores: {resumen['errores']}")

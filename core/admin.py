from django.contrib import admin
from .models import BannerPromocional, Estacion, PrecioActual, PrecioHistorico


@admin.register(Estacion)
class EstacionAdmin(admin.ModelAdmin):
    list_display = ("marca", "comuna", "direccion", "codigo_servicio", "region")
    list_filter = ("marca", "region", "comuna")
    search_fields = ("direccion", "codigo_servicio", "nombre")


@admin.register(PrecioActual)
class PrecioActualAdmin(admin.ModelAdmin):
    list_display = ("estacion", "combustible_id", "tipo_atencion", "precio", "fecha_actualizacion")
    list_filter = ("combustible_id", "tipo_atencion")
    search_fields = ("estacion__direccion", "estacion__codigo_servicio")


@admin.register(PrecioHistorico)
class PrecioHistoricoAdmin(admin.ModelAdmin):
    list_display = ("estacion", "combustible_id", "tipo_atencion", "precio", "fecha_actualizacion")
    list_filter = ("combustible_id", "tipo_atencion")
    search_fields = ("estacion__direccion", "estacion__codigo_servicio")


@admin.register(BannerPromocional)
class BannerPromocionalAdmin(admin.ModelAdmin):
    list_display = ("titulo", "ubicacion", "orden", "activo", "inicio_publicacion", "fin_publicacion")
    list_filter = ("ubicacion", "activo")
    search_fields = ("titulo", "descripcion", "url_destino")

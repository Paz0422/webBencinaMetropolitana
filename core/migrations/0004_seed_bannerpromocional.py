from django.db import migrations


def seed_banners(apps, schema_editor):
    BannerPromocional = apps.get_model("core", "BannerPromocional")
    banners = [
        {
            "titulo": "Ahorra con Premium",
            "descripcion": "Recibe alertas personalizadas de bajas de precio por comuna.",
            "etiqueta_cta": "Probar",
            "url_destino": "",
            "ubicacion": "superior",
            "orden": 1,
        },
        {
            "titulo": "Compara antes de cargar",
            "descripcion": "Activa el modo comparar en el mapa y elige la mejor opcion.",
            "etiqueta_cta": "Ver mapa",
            "url_destino": "",
            "ubicacion": "superior",
            "orden": 2,
        },
        {
            "titulo": "Aliados de la semana",
            "descripcion": "Promociones en estaciones seleccionadas para usuarios frecuentes.",
            "etiqueta_cta": "Ver detalle",
            "url_destino": "",
            "ubicacion": "inferior",
            "orden": 1,
        },
        {
            "titulo": "Tu ruta inteligente",
            "descripcion": "Proximamente: recomendacion automatica segun consumo y ubicacion.",
            "etiqueta_cta": "Unirme",
            "url_destino": "",
            "ubicacion": "inferior",
            "orden": 2,
        },
    ]

    for data in banners:
        BannerPromocional.objects.get_or_create(
            titulo=data["titulo"],
            ubicacion=data["ubicacion"],
            defaults={
                "descripcion": data["descripcion"],
                "etiqueta_cta": data["etiqueta_cta"],
                "url_destino": data["url_destino"],
                "orden": data["orden"],
                "activo": True,
            },
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_bannerpromocional"),
    ]

    operations = [
        migrations.RunPython(seed_banners, noop_reverse),
    ]

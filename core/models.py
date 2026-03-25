from django.db import models


class Estacion(models.Model):
    codigo_servicio = models.CharField(max_length=32, unique=True, blank=True, default="")
    servicio_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    nombre = models.CharField(max_length=120, blank=True, default="")
    marca = models.CharField(max_length=50, db_index=True)
    direccion = models.CharField(max_length=220)
    comuna = models.CharField(max_length=80, db_index=True)
    comuna_id = models.CharField(max_length=16, blank=True, default="", db_index=True)
    region = models.CharField(max_length=80, blank=True, default="", db_index=True)
    region_id = models.CharField(max_length=16, blank=True, default="", db_index=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["comuna", "marca", "direccion"]

    def __str__(self):
        return f"{self.marca} - {self.direccion}"


class PrecioActual(models.Model):
    estacion = models.ForeignKey(
        Estacion, on_delete=models.CASCADE, related_name="precios_actuales"
    )
    combustible_id = models.PositiveSmallIntegerField(db_index=True)
    tipo_atencion = models.CharField(max_length=20, db_index=True)
    precio = models.DecimalField(max_digits=10, decimal_places=3, db_index=True)
    fecha_actualizacion = models.DateTimeField(db_index=True)
    fecha_extraccion = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["estacion", "combustible_id", "tipo_atencion"],
                name="uniq_precio_actual_estacion_combustible_tipo",
            )
        ]
        ordering = ["precio", "estacion__comuna"]

    def __str__(self):
        return (
            f"{self.estacion.codigo_servicio} c{self.combustible_id} "
            f"{self.tipo_atencion}: {self.precio}"
        )


class PrecioHistorico(models.Model):
    estacion = models.ForeignKey(
        Estacion, on_delete=models.CASCADE, related_name="precios_historicos"
    )
    combustible_id = models.PositiveSmallIntegerField(db_index=True)
    tipo_atencion = models.CharField(max_length=20, db_index=True)
    precio = models.DecimalField(max_digits=10, decimal_places=3)
    fecha_actualizacion = models.DateTimeField(db_index=True)
    fecha_extraccion = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["estacion", "combustible_id", "tipo_atencion", "fecha_actualizacion"],
                name="uniq_precio_historico_est_comb_tipo_fecha",
            )
        ]
        ordering = ["-fecha_actualizacion"]

    def __str__(self):
        return (
            f"{self.estacion.codigo_servicio} c{self.combustible_id} "
            f"{self.tipo_atencion} @ {self.fecha_actualizacion}"
        )


class BannerPromocional(models.Model):
    class Ubicacion(models.TextChoices):
        SUPERIOR = "superior", "Superior"
        INFERIOR = "inferior", "Inferior"

    titulo = models.CharField(max_length=90)
    descripcion = models.CharField(max_length=220, blank=True, default="")
    etiqueta_cta = models.CharField(max_length=30, blank=True, default="")
    url_destino = models.URLField(blank=True, default="")
    ubicacion = models.CharField(max_length=12, choices=Ubicacion.choices, db_index=True)
    orden = models.PositiveSmallIntegerField(default=0, db_index=True)
    activo = models.BooleanField(default=True, db_index=True)
    inicio_publicacion = models.DateTimeField(null=True, blank=True)
    fin_publicacion = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ubicacion", "orden", "-fecha_creacion"]

    def __str__(self):
        return f"[{self.get_ubicacion_display()}] {self.titulo}"

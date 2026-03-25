# Operacion MVP

## 1) Carga inicial de datos

Sincroniza Region Metropolitana y 4 combustibles principales:

`python manage.py sync_precios_full --regiones 13 --combustibles 1 2 3 4`

## 2) Programar actualizacion automatica (Windows)

Puedes crear una tarea cada 60 minutos con `schtasks`:

`schtasks /Create /SC HOURLY /MO 1 /TN "WebBencinaSync" /TR "cmd /c cd /d C:\Users\Franco\web_bencina && C:\Users\Franco\web_bencina\venv\Scripts\python.exe manage.py sync_precios_full --regiones 13 --combustibles 1 2 3 4" /F`

Para probar manualmente:

`schtasks /Run /TN "WebBencinaSync"`

Para eliminarla:

`schtasks /Delete /TN "WebBencinaSync" /F`

## 3) Gestionar banners desde admin

1. Entra a `/admin`.
2. Abre `Banner promocionals`.
3. Completa:
   - `ubicacion`: `Superior` o `Inferior`.
   - `activo`: habilita/deshabilita.
   - `inicio_publicacion` y `fin_publicacion` (opcionales).
   - `url_destino` y `etiqueta_cta` (opcional).
4. Usa `orden` para definir prioridad.

## 4) Checklist de salida a produccion

- Configurar variables de entorno:
  - `DJANGO_SECRET_KEY`
  - `DJANGO_DEBUG=False`
  - `DJANGO_ALLOWED_HOSTS=tu-dominio.com,.onrender.com`
  - `DJANGO_CSRF_TRUSTED_ORIGINS=https://tu-dominio.com,https://tuapp.onrender.com`
- Instalar dependencias:
  - `pip install -r requirements.txt`
- Ejecutar migraciones:
  - `python manage.py migrate`
- Recolectar estaticos:
  - `python manage.py collectstatic --noinput`
- Cargar una corrida inicial de datos:
  - `python manage.py sync_precios_full --regiones 13 --combustibles 1 2 3 4`

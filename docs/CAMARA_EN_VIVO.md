# Cámara en vivo — Documentación del proceso

Fecha: 12 de noviembre de 2026. Estado: **operativo de forma temporal** (túnel rápido de Cloudflare) y con el código en `main`. Quedan tareas pendientes para producción definitiva, listadas al final.

## Objetivo

Integrar una cámara Eufy (RTSP) al panel operacional de EcoValdivia. La cámara es **visible solo para operadores y administradores**, nunca para el público general.

## Arquitectura

```
Cámara Eufy (192.168.1.26:554, RTSP)
        │  RTSP (video H264 + audio AAC 16 kHz)
        ▼
go2rtc (local, puerto 1984)
   · convierte RTSP → WebRTC / MSE
   · sirve /stream.html?src=las_animas
   · protegido con autenticación básica
        │
        ├──(túnel cloudflared)→ https://<tunel>.trycloudflare.com  (cámara, con auth)
        │
        ▼
App Flask (panel operacional, rol operador/administrador)
   · endpoint GET /api/camara/<punto_id>  (protegido)
   · iframe en panel.html → <stream_host>/stream.html?src=las_animas
```

Los navegadores no reproducen RTSP de forma nativa; go2rtc hace la conversión a WebRTC/MSE y expone un reproductor embebible.

## Archivos del proyecto (código)

| Archivo | Rol |
| --- | --- |
| `app/services/camara_service.py` | Lee la config de cámara desde el entorno y devuelve `rtsp_url`, `stream_src` y `stream_host`. Solo el punto "Demostración — Las Ánimas" tiene cámara. |
| `app/routes/auth.py` | Endpoint `GET /api/camara/<punto_id>` protegido con `@roles_required("operador", "administrador")`. La ruta `/panel` pasa `camara` al template. |
| `app/templates/panel.html` | Tarjeta "Cámara en vivo" + botón "Ver Cámara en Vivo" + modal (solo si `camara` está configurada). |
| `app/static/js/camara.js` | Abre el modal, consulta `/api/camara/<id>`, verifica que el streaming responda y renderiza el iframe. Muestra "Servidor de cámara local desconectado" si no responde. |
| `app/templates/_visual.html` | Icono `camara`. |
| `app/static/css/style.css` | Estilos del modal de cámara. |
| `.env.example` | Documenta las variables de entorno de la cámara. |

## Variables de entorno

| Variable | Valor por defecto | Uso |
| --- | --- | --- |
| `ECOV_CAMARA_RTSP_URL` | (vacío) | URL RTSP cruda de la cámara. Si está vacía, la cámara **no aparece** en el panel. |
| `ECOV_CAMARA_STREAM_SRC` | `las_animas` | Nombre del stream en go2rtc. |
| `ECOV_CAMARA_STREAM_HOST` | `http://localhost:1984` | Origen del servidor de streaming. En producción apunta a la URL pública del túnel/proxy. |

Las credenciales RTSP y la contraseña de go2rtc **no van en el repositorio**: viven en `C:\Users\Clase\Downloads\Ecovaldivia\go2rtc\` (fuera del repo).

## Configuración local (fuera del repositorio)

Directorio: `C:\Users\Clase\Downloads\Ecovaldivia\go2rtc\`

- `go2rtc.exe` — servidor de streaming (descargado de `AlexxIT/go2rtc`).
- `ffmpeg.exe` — solo necesario si se transcodifica (no se usa en passthrough).
- `cloudflared.exe` — túnel (descargado de `cloudflare/cloudflared`).
- `go2rtc.yaml` — configuración del stream y de la autenticación.
- `camara_credenciales.txt` — usuario/contraseña de la cámara (local, NO versionar).
- `iniciar_camara.bat` — arranca go2rtc y el túnel de la cámara.

`go2rtc.yaml` (ejemplo, sin credenciales reales):

```yaml
api:
  listen: ":1984"
  username: "<usuario>"
  password: "<contraseña>"
  local_auth: true          # importante: el túnel se conecta desde localhost
streams:
  las_animas: rtsp://<USUARIO>:<CLAVE>@<IP_CAMARA>/live0
```

`local_auth: true` es **obligatorio**: sin él, go2rtc omite la autenticación para peticiones desde localhost y el túnel dejaría la cámara expuesta.

## Arranque local

```bat
cd C:\Users\Clase\Downloads\Ecovaldivia\go2rtc
iniciar_camara.bat
```

O manualmente:

```bat
go2rtc.exe -config go2rtc.yaml
cloudflared.exe tunnel --url http://localhost:1984 --no-autoupdate
```

Al iniciar cloudflared, imprime una URL `https://XXXX.trycloudflare.com`. Esa URL es la que se configura como `ECOV_CAMARA_STREAM_HOST`.

## Despliegue en producción (Render)

1. Subir el código a GitHub (ya está en `main` de `j-caster/ecovaldivia`).
2. Desplegar el Blueprint en Render (ver README).
3. Configurar en Render las variables de entorno de la cámara:

| Variable | Valor |
| --- | --- |
| `ECOV_CAMARA_RTSP_URL` | URL RTSP real de la cámara |
| `ECOV_CAMARA_STREAM_SRC` | `las_animas` |
| `ECOV_CAMARA_STREAM_HOST` | `https://XXXX.trycloudflare.com` (URL pública del túnel) |

4. Mantener encendido el equipo local con go2rtc + cloudflared.

**Importante**: Render no puede alcanzar la cámara (IP privada 192.168.1.26). La cámara depende del túnel local; si el PC se apaga, la cámara deja de funcionar aunque la app siga arriba. Sin `ECOV_CAMARA_RTSP_URL` definido, el botón simplemente no aparece (comportamiento seguro).

## Seguridad (capas)

1. **Aplicación**: `/api/camara/<punto_id>` exige rol operador/administrador (`roles_required`). El público nunca ve el botón ni el modal.
2. **Streaming**: go2rtc exige autenticación básica (`username`/`password` + `local_auth: true`). Sin credenciales, la URL del túnel devuelve 401.
3. **Credenciales**: RTSP y contraseña de go2rtc fuera del repositorio.

Verificación rápida de la capa de streaming:

```powershell
# Sin credenciales → 401
Invoke-WebRequest 'https://XXXX.trycloudflare.com/api/streams' -UseBasicParsing
# Con credenciales → 200
$cred = Get-Credential
Invoke-WebRequest 'https://XXXX.trycloudflare.com/api/streams' -UseBasicParsing -Credential $cred
```

## Nota sobre códecs

La cámara entrega audio AAC a 16 kHz. En Chrome real se reproduce correctamente. En navegadores headless (pruebas automatizadas) ese códec puede fallar con `MEDIA_ERR_SRC_NOT_SUPPORTED`; no es un problema del usuario final.

Si en algún navegador real fallara, go2rtc puede transcodificar con ffmpeg:

```yaml
streams:
  las_animas_raw: rtsp://<credenciales>@<IP>/live0
  # audio AAC 48 kHz (necesita ffmpeg.exe junto a go2rtc):
  las_animas: ffmpeg:las_animas_raw#video=copy#audio=aac#raw=-ar 48000 -ac 2
  # o video sin audio:
  # las_animas: ffmpeg:las_animas_raw#video=copy
```

## Pendientes (para continuar)

- [ ] **Túnel estable**: reemplazar el túnel rápido de cloudflared por un *Cloudflare Tunnel nombrado* (requiere dominio en Cloudflare) o **ngrok** (cuenta + authtoken) para que la URL no cambie en cada reinicio.
- [ ] **Desplegar y verificar en Render**: crear el Blueprint y comprobar panel + cámara desde la URL de Render.
- [ ] **UX del doble login**: hoy el operador se autentica en la app y luego el navegador pide usuario/contraseña de la cámara. Evaluar un proxy de streaming detrás del login de Flask para una sola autenticación.
- [ ] **Prueba unitaria** que cubra la restricción de roles de `/api/camara/<punto_id>` (anónimo → 302, ciudadano → 403, operador → 200).
- [ ] **IP dinámica de la cámara**: el router no da IP estática; evaluar el servicio de detección por ARP/ping (`EufyCameraService`) si la IP cambia.
- [ ] Probar desde un dispositivo móvil y verificar que el WebRTC/MSE funciona fuera de la red local.
- [ ] Documentar/automatizar el arranque de go2rtc + túnel como servicio de Windows (para que sobreviva a reinicios del PC).

## Comandos útiles

```powershell
# Ejecutar pruebas
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"

# Verificar que el endpoint devuelve stream_host (test client, con env vars)
# (ver el servicio camara_service.py)

# Estado del stream en go2rtc
Invoke-RestMethod 'http://localhost:1984/api/streams' -Credential $cred
```

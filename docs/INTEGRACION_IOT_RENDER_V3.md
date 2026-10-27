# Integración Arduino y Render para EcoValdivia V3

## Objetivo

Conservar el prototipo Arduino y el servidor UDP + Firestore que ya funcionan,
y añadir un envío **HTTPS autenticado** hacia la aplicación Flask publicada en
Render. Flask procesa las lecturas con `procesar_medicion` y actualiza su base de
datos, mapa, panel y alertas. **No se altera el sketch Arduino.**

```text
Arduino UNO R4 WiFi ──UDP cifrado──> servidor Python local
                                       │
                            ┌──────────┴─────────┐
                            │                    │
                         Firestore          HTTPS con token
                          (actual)                 │
                                                   ▼
                                            Flask en Render
                                                   │
                                                PostgreSQL
                                                   │
                                           Web, panel y alertas
```

## Qué archivos se agregaron o cambiaron

En el repositorio Flask (rama `main` del 27-10-2026):

- `app/routes/iot_api.py`: nuevo `POST /api/iot/lecturas`.
- `app/__init__.py`: registra la ruta nueva.
- `config.py`: lee token y dispositivo autorizados desde variables de entorno.
- `.env.example`: agrega ejemplos sin claves reales.
- `tests/test_iot_api.py` y `tests/test_render_bridge.py`: pruebas sin hardware.

Para usar en el **notebook local**, no en Render:

- `gateway_local/servidor_ecovaldivia_v3_render.py`: copia del servidor estable
  Firebase etapa 2, con un segundo envío opcional a Render.
- `gateway_local/render_bridge.py`: trabajador HTTPS no bloqueante. El gateway
  mantiene UDP y Firebase aunque Render no responda.

## 1. Elegir a qué contenedor se vincula el Arduino

Francisco debe decidir a qué contenedor se asociará el Arduino físico.
Para pruebas en casa, **recomendamos el dispositivo de demostración**. La rama
`main` actual registra estas opciones:

| Dispositivo | Contenedor vinculado |
| --- | --- |
| `DEMO-IOT-01` | `DEMO-CENTRO-01` (demostración académica) |
| `ECO-SODIMAC-VIDRIO-01` | `CONT-SODIMAC-VIDRIO-01` |
| `ECO-LATA-LATA-01` | `CONT-LATA-LATA01` |

El identificador seleccionado debe usarse **idéntico** en el servidor Flask y
en el gateway local. No elegir ambos a la vez para un único Arduino.
No publicar valores procedentes de un prototipo doméstico como si fueran
mediciones físicas de contenedores instalados en Sodimac o en otra ubicación
real. Rotular explícitamente cualquier punto como demostrativo.

## 2. Preparar Flask en Render

Integrar los archivos modificados de esta entrega en una rama de trabajo de
GitHub, revisar las diferencias y desplegar solo tras aprobar las pruebas.
No sustituir el repositorio completo: los cambios son puntuales.

En **Render > servicio EcoValdivia > Environment**, definir:

```text
ECOV_IOT_INGEST_DEVICE_ID=DEMO-IOT-01
ECOV_IOT_INGEST_TOKEN=<TOKEN_ALEATORIO_PRIVADO_DE_32_BYTES_O_MAS>
```

El identificador mostrado es un **ejemplo**; cambiar según lo acordado.
El token debe ser una cadena aleatoria de al menos 32 caracteres. Se puede
generar localmente con `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
No copiarlo a GitHub, archivos `.env` versionados, mensajes ni capturas.

El endpoint receptor será:

```text
https://ecovaldivia.onrender.com/api/iot/lecturas
```

Con el token ausente, corto o el dispositivo sin definir, el endpoint devuelve
HTTP 503 y **no acepta mediciones**. Si el dispositivo no existe en la base
de datos o está inactivo, devuelve un error de validación.

## 3. Preparar el notebook que recibe UDP

**Conservar una copia de seguridad de toda la carpeta V2.7B antes de probar.**

Copiar estos dos archivos dentro de la carpeta local del servidor Python que
ya contiene `secrets_config.py`, `firebase/`, `certs/` y `web/`:

1. `gateway_local/servidor_ecovaldivia_v3_render.py`
2. `gateway_local/render_bridge.py`

No copiar ni publicar los secretos ni la llave de cuenta de servicio de
Firebase. La copia V3 busca esos archivos en la **misma carpeta existente**.

En PowerShell, antes de ejecutar el nuevo servidor:

```powershell
$env:ECOV_RENDER_INGEST_URL = "https://ecovaldivia.onrender.com/api/iot/lecturas"
$env:ECOV_RENDER_DEVICE_ID = "DEMO-IOT-01"
$env:ECOV_RENDER_INTERVALO = "5"
$env:ECOV_RENDER_INGEST_TOKEN = Read-Host "Token privado de integración"
python servidor_ecovaldivia_v3_render.py
```

Cambiar el dispositivo por el acordado. El token debe coincidir exactamente
con `ECOV_IOT_INGEST_TOKEN` del servicio Render. `Read-Host` lo solicita en la
terminal; introducirlo en privado y no incluirlo en una captura.

**Detener primero el servidor Python V2.7B anterior**: ambos escuchan UDP 4211
y HTTPS local 8443, y no deben funcionar simultáneamente. Solo ejecutar V3
después de comprobar que V2 está respaldado.

Si las variables `ECOV_RENDER_*` no están configuradas, V3 sigue recibiendo
UDP y escribiendo Firestore como el servidor anterior.

## 4. Comprobación gradual

1. Antes de encender el Arduino, verificar que Flask en Render se abre y que
   los puntos/usuarios existentes no cambiaron.
2. Iniciar el servidor Python V3 y comprobar que Firebase se inicializa y que
   el puerto UDP 4211 queda a la escucha.
3. Encender Arduino en la misma red. Debe verse `Telemetría activa` en el panel
   local, como antes.
4. Confirmar en Firestore que el documento
   `contenedores/eco_valdivia_01` actualiza `ultima_actualizacion`.
5. Verificar en la terminal local mensajes
   `[RENDER] Medición aceptada (SEQ=...)`.
6. Abrir la página pública de Render. Su endpoint `/public/datos` se actualiza
   en intervalos de cinco segundos; el contenedor asociado debe reflejar el
   porcentaje y estado calculados por Flask.
7. Iniciar sesión como operador y revisar modo, compuerta, conectividad y
   alertas en `/panel`.
8. Probar cambio físico de distancias y confirmar que la información cambia.

No usar los botones de **simulación** durante las pruebas reales del mismo
dispositivo, porque los BOOT/SEQ simulados pueden alterar la deduplicación.

## 5. Criterios y precauciones

- La autenticación del Arduino **sigue siendo UDP cifrado**. El envío HTTPS se
  efectúa solo después de verificar HMAC, AEAD y SEQ en el servidor local.
- La ruta pública de Render requiere un token secreto en cabecera Bearer.
- Flask fuerza la fuente `REAL`, valida medidas positivas, identifica el
  dispositivo autorizado y descarta secuencias repetidas.
- El envío HTTP corre fuera del receptor UDP. Si Render falla o está dormido,
  no bloquea los sensores ni la compuerta: se intenta con lecturas posteriores.
- Se envía el último estado aproximadamente cada cinco segundos. El historial
  SQL sigue la persistencia selectiva ya programada por Francisco.
- El cálculo actual de llenado en Flask considera 175 cm vacío y 25 cm lleno.
  **Calibrar esos límites con el contenedor físico** antes de usar porcentajes
  como referencia operacional.
- Un primer mensaje puede demorarse si Render está iniciándose; esperar
  nuevas lecturas y revisar los registros antes de cambiar el código.
- La configuración de tokens no debe introducirse en `render.yaml` como valores
  explícitos, ni incluir credenciales de Firestore en el repositorio.

## Pruebas automatizadas para Francisco

Desde la raíz de EcoValdivia, en su entorno virtual:

```powershell
python -m unittest tests.test_iot_api tests.test_render_bridge -v
python -m unittest discover -s tests -v
```

Estas pruebas simulan tanto la petición HTTP como la validación SQL. Las pruebas
de integración UDP existentes abren un socket local y pueden requerir los
permisos de red normales del equipo.

## Pendientes antes del despliegue real

- [ ] Francisco confirma el contenedor/dispositivo demostrativo que recibirá las lecturas.
- [ ] Compartir el token entre equipos por un canal privado y configurar Render.
- [ ] Revisar los cambios en GitHub antes del despliegue; no se creó un commit.
- [ ] Comprobar recepción física y estado en `/public/datos` y `/panel`.
- [ ] Calibrar las distancias y documentar el procedimiento de prueba.

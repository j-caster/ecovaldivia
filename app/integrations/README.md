# Telemetría UDP (Hito 6B)

El protocolo V27B autentica y normaliza datos sin acceder a Flask, sockets ni
base de datos. El listener obtiene el dispositivo por identificador configurado,
lee BOOT/SEQ persistidos y llama al servicio de mediciones. Solo el servicio
confirma la medición y actualiza el estado; los rechazos no avanzan la secuencia.

Ejecutar un único worker por dispositivo/puerto. El worker no arranca desde
`run.py` ni al importar módulos. Ctrl+C solicita el cierre; el timeout del socket
permite finalizar en aproximadamente un segundo.

## Configuración en PowerShell

Desde `C:\Ecovaldivia`, configurar en la terminal del worker:

```powershell
$env:ECOV_UDP_HOST = "0.0.0.0"
$env:ECOV_UDP_PORT = "4211"
$env:ECOV_UDP_DEVICE_ID = "DEMO-IOT-01"
$env:ECOV_UDP_HMAC_KEY_HEX = "<clave HMAC compartida: 64 caracteres hexadecimales>"
$env:ECOV_UDP_AEAD_KEY_HEX = "<clave AEAD compartida: 64 caracteres hexadecimales>"
```

Los textos entre ángulos son marcadores: reemplazarlos localmente por las claves
que ya utiliza Arduino, sin publicarlas ni guardarlas en el repositorio.
`.env.example` es documentación; no se carga automáticamente. Host y puerto
tienen los valores predeterminados mostrados; identificador y claves son obligatorios.
Las dos claves deben decodificar exactamente a 32 bytes cada una.

El dispositivo debe existir en la misma base de datos utilizada por Flask y estar
activo, con un contenedor activo. `python seed.py` crea las tablas faltantes y el
dispositivo de demostración sin sobrescribir los registros existentes.

`cryptography`, declarada en `requirements.txt`, es necesaria para ejecutar el
worker y las pruebas UDP. Instalarla en `.venv` únicamente con autorización.

## Ejecución

Terminal 1, Flask:

```powershell
.\.venv\Scripts\python.exe run.py
```

Terminal 2, después de configurar el entorno:

```powershell
.\.venv\Scripts\python.exe udp_worker.py
```

## Validación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app udp_worker.py tests
```

Las pruebas usan claves ficticias y paquetes sintéticos. No se envían comandos
al Arduino. La comprobación BOOT/SEQ utiliza el estado persistente por datagrama;
la restricción única dispositivo/BOOT/SEQ se conserva como defensa adicional.
Un BOOT diferente se acepta como reinicio, conforme al alcance del Hito 6B:
no se mantiene una lista histórica de BOOT retirados.

## Panel y confirmación (Hito 8)

Para una base creada antes del Hito 8, ejecutar una vez:

```powershell
.\.venv\Scripts\python.exe migrate_hito8.py
```

La migración agrega `contador_lleno` y `boot_confirmacion`, conservando datos;
puede repetirse. Reiniciar Flask y el worker para cargar los servicios nuevos.
El transporte UDP conserva el mismo protocolo y configuración.

El panel privado (`/panel`) consulta `/panel/datos` mediante fetch cada cinco
segundos, con acceso exclusivo de operador/administrador. La conectividad usa
la actividad del dispositivo: ONLINE hasta 15 segundos inclusive, OFFLINE
después o cuando no hay actividad registrada. Umbral e intervalo están en
`app/services/panel_service.py`.

El estado Lleno requiere tres lecturas aceptadas consecutivas de al menos 95%
del mismo dispositivo y BOOT. Hasta confirmarlo se muestra Casi lleno y se
conserva el porcentaje físico calculado. Una lectura inferior al umbral,
un cambio de BOOT o un vaciado reinician el contador. Replays e inválidas no
lo incrementan. La confirmación no depende de que se inserte una Medicion;
el estado se confirma en la misma transacción que BOOT/SEQ y las alertas.
Las constantes están en `app/services/confirmacion_service.py`.

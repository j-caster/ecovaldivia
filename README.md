# EcoValdivia

Aplicación web para consultar puntos de reciclaje en Valdivia y gestionar el estado de contenedores inteligentes. Su objetivo es facilitar el reciclaje ciudadano y apoyar a operadores y administradores en el seguimiento del llenado, las alertas y los vaciados.

## Funcionalidades implementadas

- Consulta pública de puntos activos, materiales e instrucciones de preparación, horarios y filtro por material.
- Mapa Leaflet con OpenStreetMap, marcadores y popups. Los puntos sin coordenadas válidas siguen apareciendo en las tarjetas.
- Estado, porcentaje y fecha de actualización de contenedores activos; actualización pública mediante fetch cada 5 segundos, conservando el filtro.
- Autenticación y autorización para operador y administrador. El ciudadano consulta sin cuenta.
- Administración de puntos y materiales, asociación de materiales y horarios con múltiples días y franjas. Los puntos se pueden activar/desactivar.
- Dispositivos IoT persistidos, con identificador único y hasta un dispositivo activo por contenedor; el seed crea un dispositivo de demostración. No existe una pantalla CRUD de dispositivos o contenedores.
- Gestión de usuarios exclusiva del administrador en `/admin/usuarios`: creación, edición, roles, activación/desactivación y cambio de contraseña. Las cuentas se conservan para mantener el historial operacional.
- Mediciones reales por UDP y simulación administrativa, validación física y registro de historial por dispositivo.
- Persistencia selectiva: primera lectura, cambio de estado consolidado, modo, compuerta o BOOT, o al menos 60 segundos desde la última lectura persistida. Todas las lecturas aceptadas actualizan el estado actual y BOOT/SEQ.
- Cálculo lineal con el promedio de dos sensores: vacío a 175 cm, lleno a 25 cm, limitado a 0–100%. Estados Disponible, Medio, Casi lleno y Lleno.
- Confirmación de Lleno con 3 lecturas aceptadas consecutivas de al menos 95%, del mismo dispositivo y BOOT. Una lectura inferior, un BOOT nuevo o un vaciado reinician el contador persistente.
- Alertas LLENO sin duplicación de alerta activa, registro de vaciados con usuario y cierre de alertas, e historial operacional.
- Visibilidad de alertas: contador global y filtro «Solo activas» en el listado; aviso de contenedores con alerta y filas resaltadas en el panel, actualizados automáticamente cada 5 segundos. El filtro del listado se conserva al paginar.
- La métrica «Contenedores disponibles» cuenta contenedores activos con estado «Disponible» (llenado menor al 50%), según el último estado registrado, incluso si el dispositivo está offline. La conectividad se muestra por separado.
- El panel operacional, las alertas y el historial de vaciados presentan fechas en `America/Santiago`, con formato `dd-mm-YYYY HH:MM:SS`, mediante el filtro compartido `fecha_chile`. `tzdata` proporciona las reglas de zona horaria en Windows. La persistencia y los timestamps del JSON permanecen en UTC; `/panel/datos` añade `fechas_locales` para la presentación durante las actualizaciones automáticas.
- Panel operacional con actualización cada 5 segundos, modo y compuerta informados por el dispositivo y conectividad aproximada: ONLINE hasta 15 segundos desde su última actividad, OFFLINE después o sin actividad.
- Telemetría UDP autenticada con HMAC-SHA256 y cifrada/autenticada con ChaCha20-Poly1305, separada del proceso web.

El vaciado no inventa una medición física ni borra historial: deja el contenedor en `Vaciado pendiente de lectura`, con porcentaje sin dato, hasta recibir nueva telemetría. El cierre de alertas queda descrito en el evento VACIADO. AUTO/MANUAL y compuerta se muestran como telemetría; no hay comandos remotos.

## Tecnologías y arquitectura

Python 3, Flask, Flask-SQLAlchemy/SQLAlchemy, SQLite, Flask-Login, Werkzeug, cryptography, HTML, Jinja2, CSS, JavaScript y Bootstrap 5.3.3. Leaflet 1.9.4 y OpenStreetMap no requieren API key. Bootstrap y Leaflet se cargan por CDN y el mapa usa teselas externas: su presentación completa requiere Internet.

```text
Arduino UNO R4 WiFi
        |
        | UDP autenticado y cifrado
        v
udp_worker.py (proceso independiente)
        |
        v
app/integrations/udp_listener.py -> udp_protocol.py
        |
        v
app/services/medicion_service.py
        |    confirmación de llenado / alertas
        v
SQLAlchemy / SQLite (instance/ecovaldivia.db)
        ^
        | servicios / consultas
      Flask (create_app + blueprints)
   |            |               |
   v            v               v
Público      Operador      Administración
Mapa        Panel         Puntos/materiales/horarios
Leaflet/OSM Alertas        Simulación de mediciones
fetch 5 s   Vaciados       Funciones del operador
            Historial
            fetch 5 s
```

La simulación llega al mismo servicio de mediciones desde administración. El protocolo no conoce Flask ni base de datos; el servicio de dominio no conoce sockets, claves ni el Arduino. SQLAlchemy separa los modelos del motor, pero una migración futura a otro motor aún requerirá configuración y validación; el proyecto entregado utiliza SQLite.

```text
app/
  __init__.py           Factory create_app
  extensions.py        SQLAlchemy, login y claves foráneas SQLite
  models/              Entidades y restricciones de persistencia
  routes/              Blueprints público, auth, admin y operación
  services/            Validación, mediciones, confirmación, panel y operación
  integrations/        Protocolo y listener UDP
  templates/           Vistas Jinja2
  static/              CSS, JavaScript, imagen de Valdivia y librerías locales (vendor/)
tests/                 unittest y comprobaciones JavaScript/visuales
docs/                  Revisión y validación de entrega
config.py              Configuración
run.py                 Servidor Flask de desarrollo
udp_worker.py          Entrada explícita del worker
seed.py                Datos y usuarios de demostración
migrate_hito8.py        Migración aditiva para bases anteriores al Hito 8
migrate_hito10.py       Agrega contenedor.material_id en bases existentes
descargar_librerias.py  Baja Bootstrap, Leaflet y las fuentes a static/vendor
render.yaml            Blueprint de despliegue en Render
requirements.txt       Dependencias Python
.env.example           Referencia de variables, sin secretos
instance/              SQLite y artefactos locales, excluidos de Git
legacy_reference/      Referencia local antigua, excluida de Git
```

## Requisitos previos

Windows con PowerShell, Python 3 con `venv` y pip, y un navegador moderno. El entorno comprobado usa Python 3.14.4. Node.js es opcional para ejecutar las comprobaciones JavaScript; se verificaron con Node 24.15.0. Git permite comprobar el estado de la entrega. No se requiere Arduino para desarrollar o simular mediciones.

## Instalación desde cero (PowerShell)

Obtener el código y abrir PowerShell en la carpeta raíz que contiene `run.py` y `requirements.txt` (por ejemplo `C:\Ecovaldivia`).

```powershell
Set-Location C:\Ecovaldivia
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed.py
python run.py
```

Abrir <http://127.0.0.1:5000/>. El seed crea todas las tablas en una base nueva y carga datos sin duplicar registros ni sobrescribir los existentes. Flask no inicializa la base automáticamente. La base se ubica en `instance/ecovaldivia.db`; ejecutar desde la raíz mantiene disponibles los archivos y comandos del proyecto.

Si PowerShell bloquea la activación, no hace falta cambiar su política: usar directamente el ejecutable del entorno.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe run.py
```

Estos pasos documentan la instalación; no instalar en el Python global. Para una base antigua, respaldar primero `instance/` y detener Flask y el worker. Si la base ya tenía DispositivoIoT antes del Hito 8, ejecutar:

```powershell
.\.venv\Scripts\python.exe migrate_hito8.py
```

Este script agrega los campos de confirmación faltantes y se puede repetir. `create_all()` no migra tablas existentes; el script no sustituye una migración general de cualquier versión antigua. Reiniciar ambos procesos después.

Para una base creada antes del Hito 10, ejecutar además:

```powershell
.\.venv\Scripts\python.exe migrate_hito10.py
```

Este script agrega `contenedor.material_id` y también se puede repetir: los contenedores existentes quedan sin material asignado hasta que se editen.

## Librerías locales (sin CDN)

Bootstrap, Leaflet y las fuentes web se sirven desde `app/static/vendor/`, por lo que la interfaz no depende de CDN y funciona igual sobre HTTP local y sobre HTTPS. Para volver a descargarlas o actualizarlas:

```powershell
.\.venv\Scripts\python.exe descargar_librerias.py
```

Solo ese script necesita internet. Las teselas del mapa siguen viniendo de OpenStreetMap: son datos del mapa, no librerías, y sin conexión el mapa queda vacío pero las tarjetas de puntos se siguen mostrando.

## Usuarios de demostración

Credenciales públicas definidas en `seed.py`, exclusivamente para desarrollo:

| Rol | Usuario | Contraseña |
| --- | --- | --- |
| Administrador | `admin` | `Admin123!` |
| Operador | `operador` | `Operador123!` |

El ciudadano no inicia sesión. El seed guarda hashes, no contraseñas planas en SQLite. No restaura contraseñas de usuarios ya existentes. Antes de un entorno real, cambiar estas credenciales o desactivar las cuentas demo desde Administración → Usuarios. Las contraseñas nuevas requieren entre 8 y 128 caracteres y confirmación; al editar, dejar ambos campos vacíos conserva la contraseña. Un administrador no puede desactivar su propia cuenta ni quitar su propio rol. Las cuentas inactivas pierden acceso también en sesiones existentes.

Los puntos, coordenadas, direcciones, materiales, horarios y porcentajes iniciales de demostración son ilustrativos y no información oficial. El dispositivo `DEMO-IOT-01` está asociado a `DEMO-CENTRO-01`. El estado inicial no equivale a telemetría física: la conectividad será OFFLINE hasta recibir actividad.

## Ejecutar Flask y el worker UDP

Terminal 1, desde la raíz:

```powershell
.\.venv\Scripts\python.exe run.py
```

Terminal 2, desde la misma raíz, configurar **localmente** antes de iniciar el worker:

```powershell
$env:ECOV_UDP_HOST = "0.0.0.0"
$env:ECOV_UDP_PORT = "4211"
$env:ECOV_UDP_DEVICE_ID = "DEMO-IOT-01"
$env:ECOV_UDP_HMAC_KEY_HEX = "<CLAVE_HMAC_LOCAL_DE_64_HEX>"
$env:ECOV_UDP_AEAD_KEY_HEX = "<CLAVE_AEAD_LOCAL_DE_64_HEX"
.\.venv\Scripts\python.exe udp_worker.py
```

Con el entorno activado en esa terminal, el último comando es `python udp_worker.py`. Las claves mostradas son marcadores inválidos, nunca valores utilizables. Usar las claves compartidas con el Arduino mediante un mecanismo local seguro; no publicarlas, fotografiarlas ni incorporarlas al repositorio. Evitar su exposición en el historial de terminal o registros compartidos.

| Variable | Uso |
| --- | --- |
| `ECOV_UDP_HOST` | IPv4 de escucha; por defecto `0.0.0.0` |
| `ECOV_UDP_PORT` | Puerto UDP; por defecto `4211`, entero entre 1 y 65535 |
| `ECOV_UDP_DEVICE_ID` | Identificador obligatorio de un dispositivo registrado, activo y con contenedor activo |
| `ECOV_UDP_HMAC_KEY_HEX` | Clave obligatoria de 32 bytes: 64 caracteres hexadecimales |
| `ECOV_UDP_AEAD_KEY_HEX` | Clave obligatoria de 32 bytes: 64 caracteres hexadecimales |

`.env.example` sirve de referencia. Ni Flask ni el worker cargan archivos `.env` automáticamente. Las variables PowerShell pertenecen a la terminal y sus procesos hijos; abrir otra terminal no copia esas asignaciones.

Ejecutar un único worker por dispositivo/puerto. Flask y el worker usan la misma base SQLite. El worker no se inicia al importar ni desde `run.py`, evitando duplicación por el reloader. Ctrl+C detiene cada proceso; el socket tiene timeout de un segundo para permitir el cierre.

El sobre es `V=2;DIR=TEL;NONCE=<hex>;CT=<hex>;TAG=<hex>;SIG=<hex>`. El HMAC firma el texto previo a `;SIG=`, el AAD es `ECO-VALDIVIA-V27B|TEL`, y el nonce son 8 bytes de BOOT más 4 bytes de SEQ en big-endian. La identidad proviene de `ECOV_UDP_DEVICE_ID`, no de la IP ni del ID de medición. BOOT/SEQ se contrastan con el estado persistente; el mismo BOOT exige SEQ mayor. Un BOOT distinto se acepta como reinicio. Ver [la documentación de integración](app/integrations/README.md).

## Acceso desde tablet o teléfono en la red local

`run.py` ya escucha en `0.0.0.0:5000`. En el notebook:

```powershell
ipconfig
```

Identificar la dirección IPv4 del adaptador Wi-Fi/Ethernet conectado a la misma red que el teléfono, por ejemplo `192.168.1.50`. En el otro dispositivo abrir `http://192.168.1.50:5000/`, reemplazando la IP por la real. `0.0.0.0` es una dirección de escucha, no la dirección que se abre en el navegador; `127.0.0.1` en el teléfono apunta al propio teléfono.

Si no conecta, revisar aislamiento de clientes/red de invitados y el firewall de Windows. En una red privada de confianza, permitir TCP 5000 para Flask y UDP 4211 para el Arduino únicamente cuando se necesite. No abrirlos indiscriminadamente en redes públicas ni redirigirlos desde Internet. El Arduino debe enviar al IPv4 del notebook y al puerto UDP configurado. No se cambia su lógica desde esta aplicación.

## Pruebas y comprobaciones

Con el entorno activado:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app tests config.py run.py seed.py udp_worker.py migrate_hito8.py migrate_hito10.py descargar_librerias.py
python -m pip check
node --check app/static/js/main.js
node --check app/static/js/mapa_publico.js
node --check app/static/js/panel.js
node tests/test_mapa_refresh.js
node tests/test_panel_refresh.js
git diff --check
git status --short
```

Sin activar, sustituir `python` por `.\.venv\Scripts\python.exe`. Las pruebas usan bases aisladas y claves ficticias; incluyen un datagrama UDP real por loopback, no comunicación con hardware. La comprobación visual opcional `python tests/visual_check.py` requiere Node y Chrome instalado en la ruta definida en ese script; usa una base en memoria y guarda capturas en `instance/visual-hito85b/`. No forma parte de unittest ni requiere instalar automatización de navegador.

La revisión del Hito 9 y sus límites se documentan en [VALIDACION_ENTREGA.md](docs/VALIDACION_ENTREGA.md). `requirements.txt` no fija versiones: las instalaciones futuras pueden resolver versiones diferentes; no se afirma reproducibilidad exacta de dependencias.

## Revisión manual de entrega

| Ruta | Acceso / comprobación |
| --- | --- |
| `/` | Público: mapa, tarjetas, horarios y filtro; repetir a 390, 768, 1366 y 1920 px |
| `/public/datos?material=2` | Público: solo resultado filtrado e información pública |
| `/salud` | Público: chequeo de vida del hosting, sin consultar la base de datos |
| `/login` | Formulario de acceso; probar credenciales correctas e incorrectas |
| `/panel` | Operador/admin: estado, conectividad y actualización automática |
| `/admin` | Solo administrador: puntos, materiales, horarios y simulación |
| `/operacion/alertas` | Operador/admin: alertas y registrar vaciado |
| `/operacion/historial` | Operador/admin: usuario y evento del vaciado |

En una base de demostración, abrir público y panel en ventanas separadas. Desde administración simular lecturas para el dispositivo demo: comprobar que cambian porcentajes, barras y popups sin recargar tras el siguiente ciclo. Para confirmar Lleno, enviar tres lecturas con sensores a 25 cm, mismo BOOT y SEQ creciente; el formulario permite introducir BOOT/SEQ. Si se deja BOOT vacío, el servicio crea un BOOT diferente por simulación y no acumula tres confirmaciones. Registrar vaciado y comprobar cierre de alerta, evento y espera de nueva lectura. Estas acciones modifican datos: realizarlas en una base de demostración, no sobre historial operativo.

## Despliegue en Render

1. Subir el repositorio a GitHub.
2. En Render: **New → Blueprint** y elegir el repositorio. Render lee `render.yaml`, instala `requirements.txt`, crea la base PostgreSQL y publica el servicio con certificado HTTPS automático.
3. `run.py` crea las tablas y carga los datos de demostración al arrancar (idempotente), así que no hace falta Shell ni ejecutar `python seed.py` a mano: el sitio queda listo al terminar el primer despliegue.

El Blueprint define `SECRET_KEY` (generada por Render, para que las sesiones sobrevivan a los reinicios), `SESSION_COOKIE_SECURE=1`, `DATABASE_URL` (tomada de la base PostgreSQL del propio Blueprint) y `PYTHON_VERSION`. Si se prefiere crear el servicio a mano, el comando de arranque es:

```bash
gunicorn run:app --bind 0.0.0.0:$PORT --workers 1 --timeout 60
```

Notas de operación:

- Con PostgreSQL los datos sobreviven a los despliegues. Con SQLite en Render el disco es efímero y la base se reinicia en cada publicación.
- El chequeo de vida es `/salud`, que responde 200 sin tocar la base de datos. Así el despliegue queda arriba aunque todavía no se haya ejecutado `seed.py`; en cambio `/` falla hasta que existan las tablas.
- Gunicorn es solo para el servidor: en Windows se sigue arrancando con `run.py`.
- El **worker UDP no puede correr en Render**, porque el servicio solo expone HTTP/HTTPS y no puertos UDP. Para telemetría real hay que ejecutar `udp_worker.py` en un equipo con acceso a la red del dispositivo y apuntarlo a la misma base con `DATABASE_URL`.
- Los usuarios que crea `seed.py` son de demostración: cambiar sus contraseñas antes de exponer el sitio.

## Seguridad y alcance de entrega

Contraseñas con hash, formularios POST con CSRF, autorización de roles, cookies HttpOnly/SameSite y validación de mediciones están implementados. El JSON público excluye IP, BOOT, SEQ, usuarios y claves. `.gitignore` excluye `.env`, `.venv/`, cachés Python, `instance/`, bases `.db`, `secrets*`, `serviceAccountKey.json` y `legacy_reference/`.

En desarrollo local se sigue usando el servidor de Flask sobre HTTP. No hay limitación de intentos de login ni protección específica de tasa UDP. Para producción existe `render.yaml`: instala las dependencias, arranca con Gunicorn detrás del proxy de Render (que entrega HTTPS automático), usa una `SECRET_KEY` estable y activa `SESSION_COOKIE_SECURE=1` para que la cookie de sesión viaje solo por conexiones cifradas. Ver «Despliegue en Render».

El anti-replay no guarda una lista de BOOT retirados: un paquete autenticado de un BOOT anterior puede volver a tratarse como reinicio; la unicidad histórica solo cubre mediciones persistidas. Una simulación sobre el dispositivo real también altera BOOT/SEQ y su confirmación: evitar mezclar simulaciones y telemetría real durante operación. No hay soporte en esta entrega para múltiples workers concurrentes por dispositivo.

No se implementan MQTT, Firebase, notificaciones externas ni control remoto. Las dependencias agregadas son `gunicorn` (servidor WSGI para Render) y `psycopg[binary]` (driver de PostgreSQL); ninguna cambia la lógica de negocio.

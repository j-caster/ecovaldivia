# Validación de entrega — Hito 9

Fecha: 8 de octubre de 2026. Revisión del código actual y ejecución local en Windows PowerShell. Alcance: documentación, revisión de seguridad y validación; sin cambios de lógica, modelos, rutas, transporte, vistas, estilos o Arduino. Sin commits ni instalación de dependencias.

## Resultados ejecutados

| Comprobación | Resultado |
| --- | --- |
| `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` | **81 pruebas aprobadas**, 46,213 s |
| `python -m compileall -q app tests config.py run.py seed.py udp_worker.py migrate_hito8.py` (usando `.venv`) | Sin errores de sintaxis |
| `node --check` de `main.js`, `mapa_publico.js`, `panel.js` y `tests/visual_browser.js` | Sin errores de sintaxis |
| `node tests/test_mapa_refresh.js` | Filtro, actualización de tarjetas/popups, reutilización de marcadores y reintento aprobados |
| `node tests/test_panel_refresh.js` | Polling, actualización, texto seguro, reintento y sesión vencida aprobados |
| `python -m pip check` (usando `.venv`) | Sin incompatibilidades declaradas |
| `git diff --check` | Sin errores de whitespace |
| `git check-ignore` sobre rutas de prueba | Todos los patrones sensibles solicitados ignorados |
| `git ls-files` para esos patrones sensibles | Ningún archivo versionado encontrado |
| `git status --short` | Cambios del hito limitados a `.env.example`, `README.md` y este documento |

Los mensajes de rechazo de dispositivo, replay, validación o base de datos emitidos en unittest son esperados en pruebas negativas; la suite terminó con `OK`. Incluye un socket UDP IPv4 real en loopback, datagrama cifrado con claves ficticias, aceptación, persistencia y cierre limpio. No se usaron secretos ni se verificó una transmisión física del Arduino durante este hito.

## Inicialización y reapertura

Se creó una base SQLite nueva en un directorio temporal dentro de `instance/`, con configuración de pruebas y una clave de sesión ficticia. Se ejecutaron `db.create_all()` y `cargar_datos()`; se repitió el seed y se compararon conteos:

| Entidad | Primera carga | Segunda carga |
| --- | --- | --- |
| Usuario | 2 | 2 |
| PuntoReciclaje | 3 | 3 |
| Contenedor | 3 | 3 |
| DispositivoIoT | 1 | 1 |

Se confirmó `PRAGMA foreign_keys=1`. Después se cerraron las conexiones, se creó otra instancia de la aplicación apuntando a esa base y se verificaron consultas y login con las credenciales demo a través del formulario y su token CSRF. La base temporal se retiró al finalizar; no se cambió `instance/ecovaldivia.db`.

Esto comprueba creación de esquema, idempotencia del seed, persistencia entre instancias y acceso funcional con las dependencias ya instaladas. **No se ejecutó una instalación desde cero en otro equipo o un entorno nuevo**, ni se descargaron paquetes. Los comandos para hacerlo están en el [README](../README.md).

## Rutas y autorización comprobadas

Comprobación con cliente de pruebas Flask sobre la base nueva. Los logins se realizaron por POST `/login` con CSRF válido; no se desactivó seguridad.

| Ruta | Anónimo | Operador | Administrador |
| --- | --- | --- | --- |
| `/` | 200 | — | — |
| `/login` | 200 | — | — |
| `/public/datos` | 200 | — | — |
| `/panel` | 302 a login | 200 | 200 |
| `/admin` | 302 a login | 403 | 200 |
| `/operacion/alertas` | 302 a login | 200 | 200 |
| `/operacion/historial` | 302 a login | 200 | 200 |
| `/panel/datos` | Cubierto por unittest | 200 | 200 |

La suite también cubre CSRF, desactivación de usuarios, permisos de administración, simulación, vaciados, confirmación de llenado, persistencia selectiva, anti-replay y exclusión de datos privados en el endpoint público. No sustituye una revisión de navegador con telemetría física. Los pasos manuales de mapa, actualización y red local están en el README.

## Revisión de seguridad

### Controles encontrados

- Hash de contraseñas con Werkzeug; verificación equivalente para usuarios desconocidos y mensaje de fallo genérico.
- Flask-Login, autorización de roles y rechazo de cuentas inactivas. Administración restringida a administrador; operación a operador/administrador.
- CSRF con token de sesión y comparación segura en operaciones POST, incluido login y logout.
- Cookies HttpOnly y SameSite=Lax. Clave de sesión externa opcional y generación temporal si falta.
- Validación de datos administrativos y de sensores numéricos, finitos y positivos; restricciones SQL, claves foráneas SQLite activadas y rollback en errores de persistencia.
- HMAC-SHA256 con comparación segura, autenticación AEAD, AAD fijo, comprobación NONCE contra BOOT/SEQ y claves obligatorias de 32 bytes suministradas por entorno.
- Identidad del dispositivo por configuración; no por IP ni ID de medición. Anti-replay utiliza estado persistente incluso en lecturas que no crean fila histórica.
- JSON público limitado a puntos/materiales/contenedores activos, coordenadas y estado. No contiene IP, BOOT, SEQ, usuarios ni claves. Jinja serializa JSON y el JavaScript usa nodos/textContent para contenido recibido.
- Logs UDP no imprimen claves ni ciphertext completo; el worker se ejecuta explícitamente y no envía comandos.

### Exclusiones y alcance de la inspección

`.gitignore` contiene `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `instance/`, `*.db`, `secrets*`, `serviceAccountKey.json` y `legacy_reference/`. Se verificaron sus efectos con nombres de prueba y la ausencia de rutas versionadas coincidentes. Se conserva `.env.example` como documentación con marcadores que no pasan la validación de claves.

No se abrieron `.env`, archivos de secretos, cuentas de servicio ni el servidor antiguo para buscar valores. Esta revisión no es una auditoría del historial Git ni garantiza que archivos con otros nombres no contengan información sensible. Nombres como `.env.local` no están cubiertos por el patrón `.env` actual: antes de usarlos, comprobar su exclusión. No se borraron archivos ni se modificaron secretos.

### Riesgos y límites pendientes

| Hallazgo | Implicación para entrega |
| --- | --- |
| Credenciales demo públicas | Cambiarlas/desactivar cuentas antes de un uso real; el seed no cambia usuarios existentes |
| Servidor Flask de desarrollo en `0.0.0.0:5000`, HTTP y cookie sin Secure | Usar solo para demostración en red confiable; publicación real requiere despliegue y HTTPS adecuados |
| SECRET_KEY temporal si falta variable | Las sesiones se invalidan al reiniciar; configurar una clave estable secreta para uso persistente |
| Sin limitación específica de intentos de login o tasa UDP | Exposición a intentos repetidos y consumo de recursos si se publica en una red no confiable |
| BOOT nuevo se acepta como reinicio, sin lista de retirados | Un replay de BOOT anterior no se rechaza siempre; la unicidad histórica solo protege lecturas persistidas |
| Un identificador y un par de claves configurados por worker | No hay aprovisionamiento ni aislamiento de múltiples dispositivos en el mismo worker; una clave compartida comprometida permite suplantar su telemetría |
| Simulación y lectura real pueden apuntar al mismo dispositivo | La simulación modifica BOOT/SEQ y confirmación; no mezclarlas durante operación real |
| SQLite y un worker por dispositivo | No hay garantía de concurrencia entre múltiples listeners; no iniciar duplicados |
| Dependencias Python sin versiones fijadas | Una instalación futura puede diferir de este entorno validado |
| Bootstrap/Leaflet por CDN y teselas OpenStreetMap | Dependencia de Internet para mapa y presentación completa; mantener atribución visible |

Se documentan estos hallazgos sin alterar comportamiento ni introducir medidas nuevas en este hito.

## Entorno comprobado y reproducibilidad

Versiones observadas localmente, como referencia de validación, no como un archivo de bloqueo:

| Componente | Versión |
| --- | --- |
| Python | 3.14.4 |
| Node.js | 24.15.0 |
| Flask | 3.1.3 |
| Flask-SQLAlchemy | 3.1.1 |
| SQLAlchemy | 2.1.3 |
| Flask-Login | 0.6.3 |
| cryptography | 50.0.2 |
| Werkzeug | 3.1.9 |
| Jinja2 | 3.1.6 |

La instalación documentada usa un entorno virtual y `requirements.txt`; la base nueva puede generarse con `seed.py`. Una base antigua debe respaldarse y migrarse según su versión: `migrate_hito8.py` solo cubre las columnas de confirmación indicadas, no cualquier esquema histórico. `.env` no se carga automáticamente: configurar variables en la terminal del proceso.

La reproducción en otro equipo debe registrar sus versiones resueltas, ejecutar la suite y probar el acceso desde su navegador/red. La red local, el firewall y las claves compartidas con el Arduino son configuraciones externas no verificadas por una base temporal o unittest.

# Proyecto EcoValdivia

EcoValdivia es una aplicación web para apoyar el reciclaje ciudadano y gestionar contenedores inteligentes.

## Objetivo general

Desarrollar un sistema web que permita a ciudadanos consultar puntos de reciclaje, materiales aceptados, horarios y estado de llenado de contenedores, y que permita a operadores y administradores gestionar la información y atender alertas.

## Stack tecnológico

- Python 3
- Flask
- SQLAlchemy
- SQLite durante desarrollo
- HTML5
- CSS
- JavaScript
- Bootstrap
- Jinja2

La arquitectura debe permitir migrar posteriormente la base de datos a PostgreSQL/Supabase sin rehacer la lógica principal.

## Roles

### Ciudadano
No requiere autenticación.
Puede:
- consultar puntos de reciclaje;
- filtrar puntos por material;
- consultar materiales aceptados;
- consultar horarios;
- consultar estado y porcentaje de llenado;
- consultar fecha de última actualización.

### Operador
Requiere autenticación.
Puede:
- consultar panel operacional;
- revisar contenedores;
- revisar alertas activas;
- consultar historial;
- registrar vaciado de contenedores;
- cerrar alertas asociadas al vaciado.

### Administrador
Requiere autenticación.
Puede realizar las funciones del operador y además:
- gestionar puntos de reciclaje;
- gestionar materiales;
- asociar materiales a puntos;
- gestionar horarios;
- gestionar contenedores;
- gestionar dispositivos IoT;
- gestionar usuarios cuando se implemente ese módulo.

## Entidades principales

- Usuario
- PuntoReciclaje
- Material
- PuntoMaterial
- Horario
- Contenedor
- DispositivoIoT
- Medicion
- Alerta
- EventoOperacional

## Funcionalidades principales

1. Consulta pública de puntos.
2. Filtro por material.
3. Información de materiales e instrucciones.
4. Horarios.
5. Estado y porcentaje de llenado.
6. Autenticación.
7. Gestión de puntos.
8. Gestión de materiales.
9. Gestión de horarios.
10. Recepción o simulación de mediciones IoT.
11. Validación de mediciones.
12. Persistencia de mediciones.
13. Cálculo de porcentaje y estado de llenado.
14. Protección contra falsos positivos mediante varias lecturas consistentes.
15. Generación de alertas de llenado.
16. Panel de alertas.
17. Registro de vaciado.
18. Preparación para configuración AUTO/MANUAL del dispositivo.

## Integración IoT

La integración física con Arduino NO debe bloquear el desarrollo del software.

El sistema debe permitir registrar y simular mediciones desde el backend durante desarrollo y pruebas.

La arquitectura debe mantener desacoplada la fuente de las mediciones, de manera que posteriormente puedan provenir de Arduino, MQTT, Firebase u otro mecanismo sin rehacer la lógica de negocio.

El código Arduino y la aplicación Android no forman parte obligatoria de esta implementación.

## Arquitectura

Separar responsabilidades como mínimo en:

- models
- routes
- services
- templates
- static
- configuración
- persistencia

No colocar toda la aplicación en un único archivo app.py.

## Seguridad

- No almacenar contraseñas en texto plano.
- Utilizar hash seguro.
- No guardar secretos ni credenciales en el repositorio.
- Utilizar variables de entorno cuando existan secretos.
- Validar entradas del usuario.
- Aplicar autorización según roles.

## Reglas de trabajo para Codex

- Antes de modificar varios archivos, explicar brevemente qué se cambiará.
- No eliminar funcionalidades existentes sin autorización.
- No cambiar de framework o arquitectura sin autorización.
- Priorizar soluciones simples, legibles y mantenibles.
- Evitar dependencias innecesarias.
- Mantener nombres de entidades coherentes con este documento.
- Después de cambios importantes, ejecutar pruebas o comprobar que la aplicación inicia.
- Si encuentra un error, corregir la causa y no ocultarlo.
- No realizar grandes refactorizaciones fuera del alcance de la tarea actual.
- No modificar archivos Arduino o Android salvo petición expresa.
- Mantener la integración IoT desacoplada.
- Crear commits solo cuando se solicite explícitamente.
- Antes de instalar nuevas dependencias, indicar para qué son necesarias.

## Estrategia de desarrollo

Trabajar por hitos pequeños y comprobables.

Orden inicial previsto:

1. Estructura base Flask.
2. Configuración y base de datos.
3. Modelos.
4. Datos iniciales.
5. Interfaz pública.
6. Autenticación y roles.
7. CRUD administrativo.
8. Contenedores y mediciones.
9. Alertas y vaciados.
10. Integración IoT.
11. Pruebas y mejoras visuales.

No implementar todo el sistema de una sola vez.

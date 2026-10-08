"""Confirmación de llenado independiente del transporte y la persistencia."""

UMBRAL_CONFIRMACION_LLENO = 95
LECTURAS_CONFIRMACION_LLENO = 3


def confirmar_llenado(porcentaje, estado_calculado, boot, boot_confirmacion, contador):
    """Retornar estado consolidado y contador para una lectura ya validada.

    Consecutivas significa lecturas aceptadas: pérdidas de datagramas no se
    interpretan como una lectura física por debajo del umbral.
    """
    if boot != boot_confirmacion:
        contador = 0
    if porcentaje < UMBRAL_CONFIRMACION_LLENO:
        return estado_calculado, 0
    contador = min((contador or 0) + 1, LECTURAS_CONFIRMACION_LLENO)
    estado = "Lleno" if contador >= LECTURAS_CONFIRMACION_LLENO else "Casi lleno"
    return estado, contador

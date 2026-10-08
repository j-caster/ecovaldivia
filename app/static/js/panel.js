"use strict";

(() => {
    const panel = document.getElementById("panel-operacional");
    if (!panel) return;
    const filas = document.getElementById("panel-contenedores");
    const aviso = document.getElementById("panel-actualizacion");
    const colores = {
        "Disponible": "bg-success", "Medio": "bg-primary",
        "Casi lleno": "bg-warning text-dark", "Lleno": "bg-danger"
    };

    function celda(texto, color) {
        const td = document.createElement("td");
        if (color) {
            const indicador = document.createElement("span");
            indicador.className = `badge ${color}`;
            indicador.textContent = texto;
            td.append(indicador);
        } else {
            td.textContent = texto;
        }
        return td;
    }

    function mostrar(contenedores) {
        const fragmento = document.createDocumentFragment();
        for (const c of contenedores) {
            const fila = document.createElement("tr");
            fila.append(
                celda(c.codigo), celda(c.punto),
                celda(c.porcentaje === null ? "Sin datos" : `${c.porcentaje.toFixed(1)}%`),
                celda(c.estado, colores[c.estado] || "bg-secondary"),
                celda(c.modo || "Sin datos"), celda(c.compuerta || "Sin datos"),
                celda(c.ultima_actualizacion || "Sin datos"),
                celda(c.alerta || "Sin alerta", c.alerta ? "bg-danger" : null),
                celda(c.conectividad, c.conectividad === "ONLINE" ? "bg-success" : "bg-secondary")
            );
            fragmento.append(fila);
        }
        if (!contenedores.length) {
            const fila = document.createElement("tr");
            const td = celda("No hay contenedores activos.");
            td.colSpan = 9;
            fila.append(td);
            fragmento.append(fila);
        }
        filas.replaceChildren(fragmento);
    }

    async function actualizar() {
        const controlador = new AbortController();
        const timeout = setTimeout(() => controlador.abort(), 4000);
        let sesionTerminada = false;
        try {
            const respuesta = await fetch(panel.dataset.endpoint, {
                credentials: "same-origin", cache: "no-store", signal: controlador.signal,
                headers: {"Accept": "application/json"}
            });
            if (respuesta.redirected || respuesta.status === 401 || respuesta.status === 403) {
                aviso.textContent = "La sesión terminó o no tienes acceso. Inicia sesión nuevamente.";
                sesionTerminada = true;
                return;
            }
            if (!respuesta.ok) throw new Error("No se pudo consultar el panel.");
            const datos = await respuesta.json();
            mostrar(datos.contenedores);
            aviso.textContent = "Panel actualizado automáticamente. Fechas en UTC.";
        } catch {
            aviso.textContent = "No se pudo actualizar. Se conservan los datos anteriores; se reintentará.";
        } finally {
            clearTimeout(timeout);
            // Programar después de cada respuesta evita peticiones superpuestas.
            if (!sesionTerminada) setTimeout(actualizar, Number(panel.dataset.intervalo));
        }
    }
    setTimeout(actualizar, Number(panel.dataset.intervalo));
})();

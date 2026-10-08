"use strict";

(() => {
    const panel = document.getElementById("panel-operacional");
    if (!panel) return;
    const filas = document.getElementById("panel-contenedores");
    const aviso = document.getElementById("panel-actualizacion");
    const colores = {
        "Disponible": "state-disponible", "Medio": "state-medio",
        "Casi lleno": "state-casi", "Lleno": "state-lleno"
    };

    function celda(texto, color) {
        const td = document.createElement("td");
        if (color) {
            const indicador = document.createElement("span");
            indicador.className = `badge status-badge ${color}`;
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
            const porcentaje = celda(c.porcentaje === null ? "Sin datos" : `${c.porcentaje.toFixed(1)}%`);
            const progreso = document.createElement("div");
            progreso.className = "progress eco-progress";
            progreso.setAttribute("role", "progressbar");
            progreso.setAttribute("aria-label", "Porcentaje de llenado");
            progreso.setAttribute("aria-valuemin", "0");
            progreso.setAttribute("aria-valuemax", "100");
            if (c.porcentaje !== null) progreso.setAttribute("aria-valuenow", String(c.porcentaje));
            else progreso.setAttribute("aria-valuetext", "Sin datos");
            const barra = document.createElement("div");
            barra.className = `progress-bar ${colores[c.estado] || "state-neutral"}`;
            barra.style.width = `${c.porcentaje ?? 0}%`;
            progreso.append(barra);
            porcentaje.append(progreso);
            fila.append(
                celda(c.codigo), celda(c.punto),
                porcentaje,
                celda(c.estado, colores[c.estado] || "state-neutral"),
                celda(c.modo || "Sin datos"), celda(c.compuerta || "Sin datos"),
                celda(c.ultima_actualizacion || "Sin datos"),
                celda(c.alerta || "Sin alerta", c.alerta ? "state-lleno" : null),
                celda(c.conectividad, c.conectividad === "ONLINE" ? "state-disponible" : "state-neutral")
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
        const resumen = {
            puntos: new Set(contenedores.map(c => c.punto)).size,
            disponibles: contenedores.filter(c => c.estado === "Disponible").length,
            criticos: contenedores.filter(c => c.estado === "Casi lleno" || c.estado === "Lleno").length,
            alertas: contenedores.filter(c => c.alerta).length,
            online: contenedores.filter(c => c.conectividad === "ONLINE").length
        };
        for (const [clave, valor] of Object.entries(resumen)) {
            const elemento = document.getElementById(`resumen-${clave}`);
            if (elemento) elemento.textContent = String(valor);
        }
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

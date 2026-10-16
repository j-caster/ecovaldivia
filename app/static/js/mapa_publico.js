"use strict";

(() => {
    const INTERVALO_ACTUALIZACION_MS = 5000;
    // Mismo formato y zona que el render del servidor (filtro fecha_chile).
    const FORMATO_CHILE = new Intl.DateTimeFormat("es-CL", {
        timeZone: "America/Santiago", day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
    });

    function fechaChile(valor) {
        if (!valor) return null;
        const fecha = new Date(valor);
        if (Number.isNaN(fecha.getTime())) return null;
        const partes = {};
        for (const parte of FORMATO_CHILE.formatToParts(fecha)) {
            partes[parte.type] = parte.value;
        }
        return `${partes.day}-${partes.month}-${partes.year} ${partes.hour}:${partes.minute}:${partes.second}`;
    }

    const contenedor = document.getElementById("mapa-publico");
    const datos = document.getElementById("datos-mapa-publico");
    const aviso = document.getElementById("mapa-aviso");
    if (!contenedor || !datos) return;
    let puntos;
    try {
        puntos = JSON.parse(datos.textContent);
    } catch {
        aviso.textContent = "No se pudieron cargar las ubicaciones. Consulta las tarjetas.";
        return;
    }

    function parrafo(texto) {
        const p = document.createElement("p");
        p.textContent = texto;
        return p;
    }

    function popup(punto) {
        const contenido = document.createElement("div");
        contenido.className = "mapa-popup";
        const titulo = document.createElement("h3");
        titulo.className = "h6";
        titulo.textContent = punto.nombre;
        contenido.append(titulo, parrafo(punto.direccion),
            parrafo(`Materiales: ${punto.materiales.join(", ") || "Sin materiales registrados"}`));
        for (const c of punto.contenedores) {
            const porcentaje = Number.isFinite(c.porcentaje_llenado)
                ? `${c.porcentaje_llenado.toFixed(1)}%` : "Sin datos de llenado";
            contenido.append(parrafo(`${c.codigo}: ${c.estado || "Sin estado"} · ${porcentaje}`));
        }
        if (!punto.contenedores.length) contenido.append(parrafo("Sin contenedores activos registrados."));
        return contenido;
    }

    let mapa = null;
    const marcadores = new Map();
    if (window.L) {
        mapa = L.map(contenedor, {scrollWheelZoom: false});
        const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(mapa);
        tiles.on("tileerror", () => {
            aviso.textContent = "No se pudo cargar parte del mapa base. Las tarjetas siguen disponibles.";
        });
    } else {
        aviso.textContent = "No se pudo cargar el mapa. Consulta los puntos en las tarjetas.";
    }

    function actualizarMapa(nuevosPuntos, inicial = false) {
        if (!mapa) return;
        const ids = new Set();
        const coordenadas = [];
        let cambioGeometria = inicial;
        for (const punto of nuevosPuntos) {
            if (!Number.isFinite(punto.latitud) || !Number.isFinite(punto.longitud)
                || Math.abs(punto.latitud) > 90 || Math.abs(punto.longitud) > 180) continue;
            const id = String(punto.punto_id);
            ids.add(id);
            const posicion = [punto.latitud, punto.longitud];
            const existente = marcadores.get(id);
            if (existente) {
                existente.marcador.setPopupContent(popup(punto));
                if (existente.latitud !== punto.latitud || existente.longitud !== punto.longitud) {
                    existente.marcador.setLatLng(posicion);
                    existente.latitud = punto.latitud;
                    existente.longitud = punto.longitud;
                    cambioGeometria = true;
                }
            } else {
                const marcador = L.marker(posicion, {title: punto.nombre, alt: punto.nombre})
                    .addTo(mapa).bindPopup(popup(punto), {maxWidth: 300});
                marcadores.set(id, {marcador, latitud: punto.latitud, longitud: punto.longitud});
                cambioGeometria = true;
            }
            coordenadas.push(posicion);
        }
        for (const [id, existente] of marcadores) {
            if (!ids.has(id)) {
                mapa.removeLayer(existente.marcador);
                marcadores.delete(id);
                cambioGeometria = true;
            }
        }
        // Conservar el zoom y la posición elegidos mientras la geometría no cambie.
        if (!cambioGeometria) return;
        if (coordenadas.length > 1) {
            mapa.fitBounds(coordenadas, {padding: [24, 24], maxZoom: 15});
        } else if (coordenadas.length === 1) {
            mapa.setView(coordenadas[0], 15);
        } else {
            mapa.setView([-39.8142, -73.2459], 12);
            aviso.textContent = "No hay puntos con coordenadas válidas en este resultado. Se muestra Valdivia como referencia.";
        }
    }

    function actualizarTarjetas(nuevosPuntos) {
        const colores = {"Disponible": "state-disponible", "Medio": "state-medio",
            "Casi lleno": "state-casi", "Lleno": "state-lleno"};
        const porId = new Map(nuevosPuntos.map(punto => [String(punto.punto_id), punto]));
        for (const tarjeta of document.querySelectorAll("[data-punto-id]")) {
            const punto = porId.get(tarjeta.dataset.puntoId);
            tarjeta.parentElement.hidden = !punto;
            if (!punto) continue;
            const porCodigo = new Map(punto.contenedores.map(c => [c.codigo, c]));
            for (const bloque of tarjeta.querySelectorAll("[data-contenedor-codigo]")) {
                const c = porCodigo.get(bloque.dataset.contenedorCodigo);
                bloque.hidden = !c;
                if (!c) continue;
                bloque.querySelector('[data-campo="estado"]').textContent = c.estado || "Sin estado";
                bloque.querySelector('[data-campo="estado"]').className = `badge status-badge ${colores[c.estado] || "state-neutral"}`;
                bloque.querySelector('[data-campo="porcentaje"]').textContent = Number.isFinite(c.porcentaje_llenado)
                    ? `${c.porcentaje_llenado.toFixed(1)}%` : "Sin datos";
                const progreso = bloque.querySelector('[data-campo="progreso"]');
                if (progreso) {
                    if (c.porcentaje_llenado !== null) {
                        progreso.setAttribute("aria-valuenow", String(c.porcentaje_llenado));
                        progreso.removeAttribute("aria-valuetext");
                    } else {
                        progreso.removeAttribute("aria-valuenow");
                        progreso.setAttribute("aria-valuetext", "Sin datos");
                    }
                    progreso.firstElementChild.style.width = `${c.porcentaje_llenado ?? 0}%`;
                    progreso.firstElementChild.className = `progress-bar ${colores[c.estado] || "state-neutral"}`;
                }
                bloque.querySelector('[data-campo="fecha"]').textContent =
                    fechaChile(c.ultima_actualizacion) || "Sin actualización registrada";
            }
        }
    }

    actualizarMapa(puntos, true);
    const url = new URL(contenedor.dataset.endpoint, window.location.href);
    const parametros = new URLSearchParams(window.location.search);
    // Capturar el filtro aplicado; cambiar el select sin enviarlo no cambia la página.
    const material = parametros.has("material") ? parametros.get("material")
        : document.getElementById("material")?.value;
    if (material) url.searchParams.set("material", material);
    let timer = null;
    let detenido = false;

    async function actualizar() {
        const controlador = new AbortController();
        const timeout = setTimeout(() => controlador.abort(), INTERVALO_ACTUALIZACION_MS);
        try {
            const respuesta = await fetch(url, {
                cache: "no-store", signal: controlador.signal, headers: {"Accept": "application/json"}
            });
            if (!respuesta.ok) throw new Error("Respuesta pública no disponible.");
            const nuevos = await respuesta.json();
            if (!Array.isArray(nuevos.puntos)) throw new Error("Respuesta pública inválida.");
            if (detenido) return;
            actualizarTarjetas(nuevos.puntos);
            actualizarMapa(nuevos.puntos);
        } catch {
            console.debug("EcoValdivia: actualización pública no disponible; se reintentará.");
        } finally {
            clearTimeout(timeout);
            // Un solo ciclo; nunca programar la siguiente consulta antes de terminar.
            if (!detenido) timer = setTimeout(actualizar, INTERVALO_ACTUALIZACION_MS);
        }
    }
    timer = setTimeout(actualizar, INTERVALO_ACTUALIZACION_MS);
    window.addEventListener("pagehide", () => { detenido = true; clearTimeout(timer); });
})();

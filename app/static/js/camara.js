"use strict";

(() => {
    const contenedor = document.getElementById("contenedor-camara");
    const modal = document.getElementById("modal-camara");
    if (!contenedor || !modal) return;

    const errorTexto = document.getElementById("error-camara");
    const nombreTexto = document.getElementById("camara-nombre");
    const botonCerrar = document.getElementById("btn-cerrar-camara");

    function limpiar() {
        contenedor.innerHTML = "";
        if (errorTexto) errorTexto.textContent = "";
        if (nombreTexto) nombreTexto.textContent = "";
    }

    function abrirModal() {
        limpiar();
        modal.hidden = false;
    }

    function cerrarModal() {
        modal.hidden = true;
        limpiar();
    }

    if (botonCerrar) {
        botonCerrar.addEventListener("click", cerrarModal);
    }

    // Un clic sobre el fondo oscuro cierra el modal.
    modal.addEventListener("click", (evento) => {
        if (evento.target === modal) cerrarModal();
    });

    // Comprueba si go2rtc responde en el origen configurado. Si la conexión se
    // rechaza (servidor apagado o túnel caído), se muestra el mensaje de error.
    async function streamingDisponible(host) {
        const controlador = new AbortController();
        const temporizador = setTimeout(() => controlador.abort(), 5000);
        try {
            await fetch(`${host}/`, {
                mode: "no-cors",
                signal: controlador.signal,
            });
            return true;
        } catch {
            return false;
        } finally {
            clearTimeout(temporizador);
        }
    }

    async function abrirCamara(puntoId) {
        abrirModal();
        try {
            const respuesta = await fetch(`/api/camara/${puntoId}`);
            if (!respuesta.ok) {
                throw new Error("No se pudo consultar la cámara");
            }

            const datos = await respuesta.json();
            if (!datos.ok) {
                throw new Error("El punto no dispone de cámara");
            }

            if (nombreTexto && datos.nombre) {
                nombreTexto.textContent = datos.nombre;
            }

            const streamHost = (datos.stream_host || "http://localhost:1984").replace(/\/+$/, "");

            const disponible = await streamingDisponible(streamHost);
            if (!disponible) {
                if (errorTexto) {
                    errorTexto.textContent = "Servidor de cámara local desconectado";
                }
                return;
            }

            const iframe = document.createElement("iframe");
            const streamSrc = datos.stream_src || "las_animas";
            iframe.src = `${streamHost}/stream.html?src=${encodeURIComponent(streamSrc)}`;
            iframe.allow = "autoplay; fullscreen";
            iframe.title = "Transmisión en vivo del punto de reciclaje";
            contenedor.appendChild(iframe);
        } catch {
            if (errorTexto) {
                errorTexto.textContent = "Servidor de cámara local desconectado";
            }
        }
    }

    document.querySelectorAll(".btn-ver-camara").forEach((boton) => {
        boton.addEventListener("click", () => abrirCamara(boton.dataset.puntoId));
    });
})();

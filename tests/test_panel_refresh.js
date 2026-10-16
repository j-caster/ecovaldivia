// Prueba del fetch y renderizado reales con DOM mínimo, sin dependencias.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Nodo {
    constructor() { this.children = []; this.textContent = ""; this.style = {}; this.attributes = {}; }
    setAttribute(nombre, valor) { this.attributes[nombre] = valor; }
    append(...hijos) { this.children.push(...hijos); }
    replaceChildren(fragmento) { this.children = [...fragmento.children]; }
}

async function main() {
    const panel = {dataset: {endpoint: "/panel/datos", intervalo: "5000"}};
    const filas = new Nodo();
    const aviso = new Nodo();
    const alertaTexto = new Nodo();
    const alertaAviso = new Nodo();
    const disponibles = new Nodo();
    const temporizadores = [];
    const peticiones = [];
    let respuesta = {
        ok: true, status: 200, redirected: false,
        json: async () => ({fechas_locales: {"2026-10-08T12:00:00Z": "08-10-2026 09:00:00"}, contenedores: [{
            codigo: "DEMO-CENTRO-01", punto: "<img src=x onerror=alert(1)>",
            porcentaje: 95, estado: "Casi lleno", modo: "AUTO", compuerta: "CERRADA",
            ultima_actualizacion: "2026-10-08T12:00:00Z", alerta: null, conectividad: "ONLINE"
        }]})
    };
    const contexto = {
        document: {
            getElementById: id => ({"panel-operacional": panel, "panel-contenedores": filas, "panel-actualizacion": aviso,
                "panel-alertas-texto": alertaTexto, "panel-alertas-aviso": alertaAviso,
                "resumen-disponibles": disponibles})[id],
            createElement: () => new Nodo(), createDocumentFragment: () => new Nodo()
        },
        AbortController,
        setTimeout: (fn, ms) => { const t = {fn, ms}; temporizadores.push(t); return t; },
        clearTimeout: t => { const i = temporizadores.indexOf(t); if (i >= 0) temporizadores.splice(i, 1); },
        fetch: async (url, opciones) => { peticiones.push({url, opciones}); return respuesta; }
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../app/static/js/panel.js"), "utf8"), contexto);
    assert.equal(temporizadores[0].ms, 5000);
    await temporizadores.shift().fn();
    assert.equal(peticiones[0].url, "/panel/datos");
    assert.equal(peticiones[0].opciones.credentials, "same-origin");
    assert.equal(filas.children[0].children[1].textContent, "<img src=x onerror=alert(1)>");
    assert.equal(filas.children[0].children[3].children[0].textContent, "Casi lleno");
    assert.equal(filas.children[0].children[6].textContent, "08-10-2026 09:00:00");
    assert.match(aviso.textContent, /Fechas en hora local de Chile/);
    assert.equal(filas.children[0].className, "");
    assert.equal(alertaTexto.textContent, "0 contenedores con alerta activa");
    assert.equal(alertaAviso.className.includes("alert-summary-active"), false);
    assert.equal(disponibles.textContent, "0");
    assert.equal(temporizadores[0].ms, 5000);
    respuesta = {...respuesta, json: async () => ({contenedores: [
        ["Disponible", 20, "ONLINE"], ["Disponible", 49.9, "OFFLINE"],
        ["Medio", 50, "ONLINE"], ["Casi lleno", 90, "ONLINE"],
        ["Lleno", 100, "ONLINE"], ["Pendiente de lectura", null, "OFFLINE"]
    ].map(([estado, porcentaje, conectividad], i) => ({
        codigo: String(i), punto: "Punto", estado, porcentaje, conectividad,
        modo: null, compuerta: null, ultima_actualizacion: null, alerta: null
    }))})};
    await temporizadores.shift().fn();
    assert.equal(disponibles.textContent, "2");
    respuesta = {...respuesta, json: async () => ({contenedores: [{
        codigo: "DEMO-CENTRO-01", punto: "Punto", porcentaje: 96, estado: "Lleno",
        modo: "AUTO", compuerta: "CERRADA", ultima_actualizacion: null,
        alerta: "Requiere vaciado", conectividad: "OFFLINE"
    }]})};
    await temporizadores.shift().fn();
    assert.equal(filas.children[0].children[3].children[0].textContent, "Lleno");
    assert.equal(filas.children[0].children[7].children[0].textContent, "Requiere vaciado");
    assert.equal(filas.children[0].children[8].children[0].textContent, "OFFLINE");
    assert.equal(filas.children[0].children[6].textContent, "Sin datos");
    assert.equal(filas.children[0].className, "alert-active");
    assert.equal(alertaTexto.textContent, "1 contenedor con alerta activa");
    assert.equal(alertaAviso.className.includes("alert-summary-active"), true);
    assert.equal(disponibles.textContent, "0");
    respuesta = {ok: false, status: 500};
    const filasPrevias = filas.children;
    await temporizadores.shift().fn();
    assert.equal(filas.children, filasPrevias);
    assert.equal(alertaTexto.textContent, "1 contenedor con alerta activa");
    assert.match(aviso.textContent, /reintentará/);
    respuesta = {ok: true, status: 200, redirected: false, json: async () => ({contenedores: []})};
    await temporizadores.shift().fn();
    assert.equal(alertaTexto.textContent, "0 contenedores con alerta activa");
    assert.equal(alertaAviso.className.includes("alert-summary-active"), false);
    assert.equal(filas.children[0].children[0].textContent, "No hay contenedores activos.");
    respuesta = {ok: false, status: 403};
    await temporizadores.shift().fn();
    assert.match(aviso.textContent, /sesión terminó/);
    assert.equal(temporizadores.length, 0);
    console.log("Panel JS: polling, actualización, texto seguro, reintento y sesión vencida OK.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });

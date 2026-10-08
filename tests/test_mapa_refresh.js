// Comprobación del adaptador de actualización con DOM/Leaflet mínimos.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Nodo {
    constructor() { this.children = []; this.textContent = ""; }
    append(...nodos) { this.children.push(...nodos); }
}

async function main() {
    const inicial = {punto_id: 1, nombre: "Punto", direccion: "Dirección", latitud: -39.8,
        longitud: -73.2, materiales: ["Vidrio"], contenedores: [{codigo: "C1", estado: "Medio",
            porcentaje_llenado: 50, ultima_actualizacion: null}]};
    const campos = {estado: new Nodo(), porcentaje: new Nodo(), fecha: new Nodo()};
    const bloque = {dataset: {contenedorCodigo: "C1"}, hidden: false,
        querySelector: selector => campos[selector.match(/"(.*?)"/)[1]]};
    const tarjeta = {dataset: {puntoId: "1"}, parentElement: {hidden: false},
        querySelectorAll: () => [bloque]};
    const nodos = {
        "mapa-publico": {dataset: {endpoint: "/public/datos"}},
        "datos-mapa-publico": {textContent: JSON.stringify([inicial])},
        "mapa-aviso": new Nodo(), "material": {value: "3"}
    };
    const timers = [], solicitudes = [], marcadores = [], eventos = {};
    let mapasCreados = 0, centrados = 0, removidos = 0, movimientos = 0;
    const mapa = {setView: () => { centrados++; }, fitBounds: () => { centrados++; },
        removeLayer: () => { removidos++; }};
    const L = {
        map: () => { mapasCreados++; return mapa; },
        tileLayer: () => ({addTo() { return this; }, on() {}}),
        marker: () => {
            const marcador = {addTo() { return this; }, bindPopup(p) { this.popup = p; return this; },
                setPopupContent(p) { this.popup = p; }, setLatLng() { movimientos++; }};
            marcadores.push(marcador);
            return marcador;
        }
    };
    let nuevaRespuesta = {puntos: [{...inicial, materiales: ["<script>texto</script>"],
        contenedores: [{codigo: "C1", estado: "Lleno", porcentaje_llenado: 96,
            ultima_actualizacion: "2026-10-08T12:30:00Z"}]}]};
    let fallar = false;
    const contexto = {L, URL, URLSearchParams, AbortController,
        window: {L, location: {href: "http://localhost/?material=2", search: "?material=2"},
            addEventListener: (nombre, fn) => { eventos[nombre] = fn; }},
        document: {getElementById: id => nodos[id], createElement: () => new Nodo(),
            querySelectorAll: () => [tarjeta]},
        setTimeout: (fn, ms) => { const t = {fn, ms}; timers.push(t); return t; },
        clearTimeout: t => { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1); },
        console: {debug() {}},
        fetch: async url => { solicitudes.push(String(url)); if (fallar) throw new Error("temporal");
            return {ok: true, json: async () => nuevaRespuesta}; }
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../app/static/js/mapa_publico.js"), "utf8"), contexto);
    assert.equal(mapasCreados, 1);
    assert.equal(timers.length, 1);
    assert.equal(timers[0].ms, 5000);
    await timers.shift().fn();
    assert.equal(solicitudes[0], "http://localhost/public/datos?material=2");
    assert.equal(campos.estado.textContent, "Lleno");
    assert.equal(campos.porcentaje.textContent, "96.0%");
    assert.notEqual(campos.fecha.textContent, "Sin actualización registrada");
    assert.match(marcadores[0].popup.children[2].textContent, /<script>texto<\/script>/);
    assert.equal(marcadores.length, 1);
    assert.equal(movimientos, 0);
    assert.equal(centrados, 1);
    assert.equal(timers.length, 1);
    fallar = true;
    await timers.shift().fn();
    assert.equal(campos.porcentaje.textContent, "96.0%");
    assert.equal(removidos, 0);
    assert.equal(timers.length, 1);
    fallar = false;
    nuevaRespuesta.puntos[0].latitud = -39.9;
    await timers.shift().fn();
    assert.equal(movimientos, 1);
    assert.equal(marcadores.length, 1);
    nuevaRespuesta = {puntos: []};
    await timers.shift().fn();
    assert.equal(removidos, 1);
    assert.equal(tarjeta.parentElement.hidden, true);
    nuevaRespuesta = {puntos: [inicial]};
    await timers.shift().fn();
    assert.equal(marcadores.length, 2);
    assert.equal(tarjeta.parentElement.hidden, false);
    assert.equal(mapasCreados, 1);
    eventos.pagehide();
    assert.equal(timers.length, 0);
    console.log("Mapa público: filtro, tarjetas, popups, marcadores reutilizados y reintento OK.");
}

main().catch(error => { console.error(error); process.exitCode = 1; });

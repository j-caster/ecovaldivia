// Chrome DevTools permite comprobar el viewport exacto sin instalar dependencias.
const fs = require('node:fs');
const [port, url, width, screenshot] = process.argv.slice(2);
(async () => {
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
    await new Promise(resolve => socket.addEventListener('open', resolve, {once: true}));
    let id = 0;
    const pending = new Map();
    socket.addEventListener('message', event => {
        const message = JSON.parse(event.data);
        if (pending.has(message.id)) {
            const {resolve, reject} = pending.get(message.id);
            pending.delete(message.id);
            message.error ? reject(new Error(message.error.message)) : resolve(message.result);
        }
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
        pending.set(++id, {resolve, reject});
        socket.send(JSON.stringify({id, method, params}));
    });
    await send('Emulation.setDeviceMetricsOverride', {
        width: Number(width), height: 1000, deviceScaleFactor: 1, mobile: false
    });
    await send('Page.navigate', {url});
    let result;
    for (let attempt = 0; attempt < 100; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 100));
        result = await send('Runtime.evaluate', {
            expression: "document.body?.getAttribute('data-visual-result')", returnByValue: true
        });
        if (result.result.value) break;
    }
    if (!result.result.value) throw new Error('La comprobación visual no terminó.');
    if (screenshot) {
        await new Promise(resolve => setTimeout(resolve, 450));
        const capture = await send('Page.captureScreenshot', {format: 'png'});
        fs.writeFileSync(screenshot, Buffer.from(capture.data, 'base64'));
    }
    console.log(result.result.value);
    socket.close();
})().catch(error => {console.error(error); process.exit(1);});

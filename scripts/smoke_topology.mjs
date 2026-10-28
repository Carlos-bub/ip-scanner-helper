// Browser validation uses Node built-ins and an isolated headless Edge/Chrome.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {existsSync, readFileSync, writeFileSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const {layoutTopologyGroups, layoutTopologyMesh, layoutTopologyTree} = require('../src/ip_scanner_helper/resources/templates/topology-layout.js');
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
async function until(predicate, label, milliseconds = 10000) {
  const end = Date.now() + milliseconds;
  while (Date.now() < end) {if (await predicate()) return; await pause(40);}
  throw new Error(`Timeout: ${label}`);
}

// Unequal group heights must never make the next row overlap. Page sizes bound
// the number of cards; 4096 members do not require 4096 DOM nodes.
for (const width of [320, 600, 1000, 1440, 1920]) {
  const tree = layoutTopologyTree(Array.from({length: 25}, (_, id) => ({id,depth:Math.floor(id/5),switch:id%2===0})), width);
  for (const a of tree.cards) {
    assert(a.x >= 0 && a.x+a.width <= tree.width+.01 && a.y+a.height<=tree.height);
    for (const b of tree.cards) if (a!==b) assert(a.x+a.width<=b.x+.01||b.x+b.width<=a.x+.01||a.y+a.height<=b.y+.01||b.y+b.height<=a.y+.01);
  }
  const mesh = layoutTopologyMesh(Array.from({length: 16}, (_, id) => ({id})), width);
  for (const a of mesh.cards) {
    assert(a.x >= 0 && a.x + a.width <= mesh.width + .01 && a.y + a.height <= mesh.height);
    for (const b of mesh.cards) {
      if (a !== b) assert(a.x + a.width <= b.x + .01 || b.x + b.width <= a.x + .01 || a.y + a.height <= b.y + .01 || b.y + b.height <= a.y + .01);
    }
  }
  for (const sizes of [[], [0], [1, 12, 2, 7, 12, 1], [12, 1, 12, 0, 1, 12]]) {
    const groups = sizes.map((size, index) => ({id: String(index), context_ids: index % 2 ? ['source'] : [],
      visible_ids: Array.from({length: size}, (_, i) => String(i)), open: true}));
    const layout = layoutTopologyGroups(groups, width);
    for (const [i, a] of layout.groups.entries()) {
      assert(a.x >= 0 && a.y >= 0 && a.x + a.width <= layout.width + .01);
      for (const b of layout.groups.slice(i + 1)) {
        assert(a.x + a.width <= b.x + .01 || b.x + b.width <= a.x + .01 || a.y + a.height <= b.y + .01 || b.y + b.height <= a.y + .01);
      }
      for (const card of a.cards) {
        assert(card.width > 0 && card.x >= a.x && card.y >= a.y);
        assert(card.x + card.width <= a.x + a.width && card.y + card.height <= a.y + a.height);
      }
    }
  }
}

const browser = [process.env.MAP_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe'].find(candidate => candidate && existsSync(candidate));
assert(browser, 'Edge/Chrome não encontrado. Informe MAP_BROWSER para o executável local.');
const directory = mkdtempSync(path.join(tmpdir(), 'ish-map-smoke-'));
const child = spawn(browser, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${directory}`,
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-component-update',
  '--disable-sync', '--disable-extensions', '--metrics-recording-only', 'about:blank'], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
let stderr = '', client;
child.stderr.on('data', data => {stderr = (stderr + data).slice(-4000);});
const errors = [], requests = [], timings = [];
class Cdp {
  constructor(url) {
    this.socket = new WebSocket(url); this.nextId = 1; this.pending = new Map();
    this.ready = new Promise((resolve, reject) => {this.socket.addEventListener('open', resolve, {once: true}); this.socket.addEventListener('error', reject, {once: true});});
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (pending) {clearTimeout(pending.timer); this.pending.delete(message.id); message.error ? pending.reject(new Error(JSON.stringify(message.error))) : pending.resolve(message.result);}
      } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
      else if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request.url);
    });
  }
  async send(method, params = {}) {
    await this.ready;
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {this.pending.delete(id); reject(new Error(`CDP timeout: ${method}`));}, 10000);
      this.pending.set(id, {resolve, reject, timer}); this.socket.send(JSON.stringify({id, method, params}));
    });
  }
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result.value;
  }
}
try {
  const activePort = path.join(directory, 'DevToolsActivePort');
  await until(() => existsSync(activePort), 'iniciar navegador');
  const port = readFileSync(activePort, 'utf8').split('\n')[0];
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  client = new Cdp(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await client.send('Page.enable'); await client.send('Runtime.enable'); await client.send('Network.enable');
  await client.send('Emulation.setFocusEmulationEnabled', {enabled: true});
  const version = await client.send('Browser.getVersion');
  async function click(selector) {
    const point = await client.evaluate(`(() => {const box=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:box.x+box.width/2,y:box.y+box.height/2};})()`);
    await client.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
    await client.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
  }
  const cases = JSON.parse(readFileSync(process.argv[2], 'utf8'));
  for (const fixture of cases) {
    await client.send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
    const started = performance.now(), url = pathToFileURL(fixture.path).href;
    await client.send('Page.navigate', {url});
    await until(() => client.evaluate(`location.href === ${JSON.stringify(url)} && document.readyState === 'complete' && document.getElementById('summary')?.textContent.includes('dispositivos')`), 'carregar mapa');
    if (fixture.kind === 'l2-evidence') {
      const graph = await client.evaluate('JSON.parse(document.getElementById("graph-data").textContent)');
      assert.equal(graph.nodes.length, fixture.count, 'Relato sem IP não cria dispositivo artificial');
      assert.deepEqual(graph.nodes.map(node => node.ip), ['192.0.2.10', '192.0.2.20', '192.0.2.30']);
      const observer = graph.nodes.find(node => node.ip === '192.0.2.10');
      assert.equal(observer.category, 'unknown', 'Observador SNMP conserva a categoria inventariada');
      assert.equal(observer.tipo, 'Dispositivo não identificado');
      assert.equal(observer.neighbor_observer, true);
      const reports = graph.edges.filter(edge => edge.kind === 'reported_neighbor');
      assert.equal(reports.length, 2, 'Protocolos/portas paralelos preservam relatos distintos');
      assert.deepEqual(reports.map(edge => [edge.source, edge.port, edge.remote_port]),
        [['LLDP', 'Gi1/0/24', 'Gi1/0/48'], ['CDP', 'Gi1/0/25', 'Gi1/0/49']]);
      assert(reports.every(edge => edge.to === '192.0.2.20' && edge.neighbor_status === 'unilateral' && !edge.direct_link_confirmed));
      assert.equal(graph.edges.filter(edge => edge.kind === 'fdb_path').length, 1);
      assert.equal(graph.edges.length, 3, 'Vizinho sem endereço permanece somente nos dados do observador');

      async function checkEvidencePaths(selector) {
        const paths = await client.evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)}), node =>
          ({kind:node.dataset.kind,dash:node.getAttribute('stroke-dasharray'),stroke:node.getAttribute('stroke'),label:node.getAttribute('aria-label')}))`);
        const neighbors = paths.filter(item => item.kind === 'reported_neighbor'), fdb = paths.filter(item => item.kind === 'fdb_path');
        assert.equal(neighbors.length, 2, 'Ambos os relatos devem aparecer na visualização');
        assert.equal(fdb.length, 1, 'O caminho FDB deve aparecer separadamente');
        assert(neighbors.every(item => item.dash === '2 4'));
        assert.equal(fdb[0].dash, '5 5');
        assert.notEqual(neighbors[0].stroke, fdb[0].stroke, 'Relações LLDP/CDP e FDB têm estilos distintos');
        assert(neighbors.some(item => item.label.includes('LLDP') && item.label.includes('Gi1/0/24')));
        assert(neighbors.some(item => item.label.includes('CDP') && item.label.includes('Gi1/0/25')));
      }
      assert.equal(await client.evaluate('document.getElementById("view").value'), 'tree');
      assert.equal(await client.evaluate('document.getElementById("nextSwitch").disabled'), false, 'Observador genérico participa da navegação');
      await click('[data-node-id="192.0.2.10"]'); await pause(450);
      assert.equal(await client.evaluate('document.getElementById("detailTitle").textContent'), observer.nome);
      assert.equal(await client.evaluate('document.getElementById("switchPosition").textContent'), '1 / 1');
      assert.equal(await client.evaluate('document.querySelectorAll(".child-row").length'), 2, 'Dois protocolos não duplicam o mesmo dispositivo');
      await checkEvidencePaths('.tree-branch');
      await click('#evidenceTab');
      assert.equal(await client.evaluate('document.getElementById("evidencePanel").hidden'), false);
      assert.equal(await client.evaluate('document.querySelectorAll("#relations li").length'), 3);
      const evidence = await client.evaluate('document.getElementById("detailBody").textContent');
      assert(evidence.includes('SEM-IP </script><img') && evidence.includes('Gi1/0/26'), 'Relato sem IP conserva identidade e porta nos detalhes');
      assert(evidence.includes('Sem correspondência no inventário'));
      assert(evidence.includes('participação parcial ou não disponível'), 'VLANs incompletas devem informar a limitação');
      assert(evidence.includes('Bridge 7 · ifIndex 124') && evidence.includes('limite de entradas'));
      await click('#nextSwitch'); await pause(400);
      assert.equal(await client.evaluate('document.getElementById("detailTitle").textContent'), observer.nome, 'Navegação alcança o observador genérico');

      await click('#overview');
      await client.evaluate('document.getElementById("view").value="mesh";document.getElementById("view").dispatchEvent(new Event("change"))');
      await checkEvidencePaths('.fdb-path');
      assert.equal(await client.evaluate('document.querySelectorAll(".device").length'), 3, 'Malha usa somente dispositivos inventariados');
      await click('[data-node-id="192.0.2.10"]'); await click('#evidenceTab');
      assert.equal(await client.evaluate('document.querySelectorAll("#relations li").length'), 3);
      assert.equal(await client.evaluate('globalThis.unsafe === undefined && document.querySelectorAll("img").length === 0'), true, 'Nomes hostis permanecem texto');
      assert.equal(await client.evaluate('JSON.parse(document.getElementById("graph-data").textContent).nodes.find(node=>node.ip==="192.0.2.10").category'), 'unknown');
      await client.send('Emulation.setDeviceMetricsOverride', {width: 600, height: 900, deviceScaleFactor: 1, mobile: false});
      await pause(150);
      assert(await client.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Evidências L2 cabem na janela compacta');
      timings.push({kind: fixture.kind, count: fixture.count, validation_ms: Math.round(performance.now() - started)});
      continue;
    }
    if (fixture.kind === 'example-tree') {
      assert.equal(await client.evaluate('document.getElementById("view").value'),'tree');
      assert(await client.evaluate('document.querySelector(".topbar").getBoundingClientRect().height <= 60'));
      assert.equal(await client.evaluate(`document.querySelector('[data-node-id="192.0.2.40"]') === null`),true);
      await pause(150);
      const before = await client.evaluate('document.getElementById("scene").getAttribute("transform")');
      await click('[data-node-id="192.0.2.10"]'); await pause(500);
      assert.equal(await client.evaluate('document.getElementById("detailTitle").textContent'),'SW-DISTRIBUICAO');
      assert.equal(await client.evaluate('document.querySelectorAll(".child-row").length'),20);
      assert(await client.evaluate(`(() => {const bounds=document.getElementById('map').getBoundingClientRect();return [...document.querySelectorAll('.tree-card > rect')].every(node=>{const a=node.getBoundingClientRect();return a.left>=bounds.left-1&&a.right<=bounds.right+1&&a.top>=bounds.top-1&&a.bottom<=bounds.bottom+1;});})()`),'Ramo focado deve ficar enquadrado, sem cortar cartões');
      assert.notEqual(await client.evaluate('document.getElementById("scene").getAttribute("transform")'),before);
      assert.equal(await client.evaluate(`document.querySelector('[data-node-id="192.0.2.40"]') !== null`),true);
      const visited = new Set(['SW-DISTRIBUICAO']);
      for(let i=0;i<5;i++){await click('#nextSwitch');await pause(380);visited.add(await client.evaluate('document.getElementById("detailTitle").textContent'));}
      assert.equal(visited.size,6,'Navegação deve percorrer todos os switches sem voltar à visão geral');
      await click('#overview'); await pause(120);
      assert.equal(await client.evaluate('document.getElementById("details").hidden'),true);
      assert.equal(await client.evaluate(`document.querySelector('[data-node-id="192.0.2.40"]') === null`),true);
      if(process.argv.includes('--capture')){
        const image=await client.send('Page.captureScreenshot',{format:'png'});writeFileSync(path.join(root,'docs','topology-overview.png'),Buffer.from(image.data,'base64'));
      }
      await click('[data-node-id="192.0.2.10"]');await pause(500);
      if(process.argv.includes('--capture')){
        const image=await client.send('Page.captureScreenshot',{format:'png'});writeFileSync(path.join(root,'docs','topology-switch-focus.png'),Buffer.from(image.data,'base64'));
      }
      await client.evaluate(`document.getElementById('childSearch').value='PC-LAB-01-17';document.getElementById('childSearch').dispatchEvent(new Event('input'))`);
      assert.equal(await client.evaluate('document.querySelectorAll(".child-row").length'),1);
      await click('#overview');
      await client.evaluate(`document.getElementById('search').value='CAM-LAB-04-03';document.getElementById('search').dispatchEvent(new Event('input'))`);
      assert.equal(await client.evaluate(`document.querySelector('[data-node-id="192.0.2.102"]') !== null`),true);
      assert.equal(await client.evaluate(`document.querySelector('[data-node-id="192.0.2.10"]') !== null`),true,'Busca preserva os ancestrais declarados no exemplo');
      await client.send('Emulation.setDeviceMetricsOverride',{width:600,height:900,deviceScaleFactor:1,mobile:false});await pause(150);
      assert(await client.evaluate('document.documentElement.scrollWidth <= innerWidth'));
      timings.push({kind:fixture.kind,count:fixture.count,validation_ms:Math.round(performance.now()-started)});continue;
    }
    // The application opens in tree mode; also retain the category/group tests.
    await client.evaluate('document.getElementById("view").value="groups";document.getElementById("view").dispatchEvent(new Event("change"));document.getElementById("grouping").value="category";document.getElementById("grouping").dispatchEvent(new Event("change"))');
    assert.equal(await client.evaluate('document.querySelectorAll(".device").length'), 0, 'Grupos devem iniciar recolhidos');
    assert.equal(await client.evaluate('document.querySelectorAll(".fdb-path").length'), 0, 'Sem linhas iniciais');
    assert.equal(await client.evaluate('JSON.parse(document.getElementById("graph-data").textContent).nodes.length'), fixture.count);
    if (!fixture.count) {
      assert.equal(await client.evaluate('document.getElementById("empty").hidden'), false);
      timings.push({kind: fixture.kind, count: 0, validation_ms: Math.round(performance.now() - started)});
      continue;
    }
    await client.evaluate('document.querySelector(".group-toggle").dispatchEvent(new KeyboardEvent("keydown", {key:"Enter", bubbles:true}))');
    assert(await client.evaluate('document.querySelectorAll(".device").length > 0 && document.querySelectorAll(".device").length <= 12'));
    const last = String(fixture.count - 1).padStart(5, '0');
    if (!['paths', 'demo'].includes(fixture.kind)) {
      await client.evaluate(`document.getElementById('search').value='NODE-${last}';document.getElementById('search').dispatchEvent(new Event('input'))`);
      assert.equal(await client.evaluate('document.querySelectorAll(".device").length'), 1, 'Busca revela o último dispositivo');
      await client.evaluate('document.querySelector(".device").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))');
      assert.equal(await client.evaluate('document.getElementById("details").hidden'), false);
      await client.evaluate('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))');
      assert.equal(await client.evaluate('document.getElementById("details").hidden'), true);
      await client.evaluate('document.getElementById("clear").click()');
    }
    await client.evaluate('document.getElementById("expandAll").click()');
    assert(await client.evaluate('document.querySelectorAll(".device").length <= 144'), 'Renderização deve ser paginada');
    // Check the actual DOM geometry in addition to pure layout arithmetic.
    assert(await client.evaluate(`(() => {const boxes=[...document.querySelectorAll('.cluster > rect')].map(node=>node.getBBox());return boxes.every((a,i)=>boxes.slice(i+1).every(b=>a.x+a.width<=b.x+.1||b.x+b.width<=a.x+.1||a.y+a.height<=b.y+.1||b.y+b.height<=a.y+.1));})()`));
    if (fixture.kind === 'large-group') {
      await client.evaluate(`document.querySelector('[data-page-group][data-delta="1"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))`);
      assert.equal(await client.evaluate('document.querySelector(".device").dataset.nodeId'), '10.0.0.13');
    }
    if (fixture.kind === 'many-switches') {
      await client.evaluate('document.getElementById("grouping").value="switch";document.getElementById("grouping").dispatchEvent(new Event("change"))');
      assert.equal(await client.evaluate('document.querySelectorAll(".cluster").length'), 12);
      await client.evaluate('document.getElementById("nextGroups").click()');
      assert.equal(await client.evaluate('document.getElementById("groupPageLabel").textContent'), '13–24 de 4096 grupos');
    }
    if (fixture.kind === 'paths') {
      await client.evaluate('document.getElementById("grouping").value="switch";document.getElementById("grouping").dispatchEvent(new Event("change"));document.getElementById("expandAll").click()');
      await client.evaluate(`document.querySelector('[data-node-id="10.0.0.10"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))`);
      assert.equal(await client.evaluate('document.querySelectorAll("#relations li").length'), 3);
      assert(await client.evaluate('document.querySelectorAll(".fdb-path").length >= 2'));
      assert.equal(await client.evaluate('globalThis.unsafe === undefined && document.querySelectorAll("img").length === 0'), true);
      await client.evaluate('document.getElementById("category").value="printers";document.getElementById("category").dispatchEvent(new Event("change"))');
      assert(await client.evaluate(`document.querySelector('[data-focus^="context:"]') !== null`), 'Filtro mantém observador como contexto');
      await client.evaluate('document.getElementById("closeDetails").click();document.getElementById("collapseAll").click()');
    }
    // The forest uses every FDB observer as an independent expansion point;
    // the mesh draws only recorded relationships, never a gateway hierarchy.
    if (['paths', 'demo'].includes(fixture.kind)) {
      await client.evaluate('document.getElementById("clear").click();document.getElementById("view").value="tree";document.getElementById("view").dispatchEvent(new Event("change"));document.getElementById("expandAll").click()');
      assert(await client.evaluate('document.querySelectorAll(".tree-branch").length >= 3'));
      assert.equal(await client.evaluate('document.getElementById("grouping").disabled'), true);
      if (fixture.kind === 'paths') {
        await client.send('Emulation.setDeviceMetricsOverride', {width: 600, height: 900, deviceScaleFactor: 1, mobile: false});
        await pause(150);
        await client.evaluate(`for(let i=0;i<5;i++) document.getElementById('zoomIn').click(); [...document.querySelectorAll('.device')].at(-1).focus();`);
        const bounds = await client.evaluate(`(() => {const a=document.activeElement.getBoundingClientRect(),b=document.getElementById('map').getBoundingClientRect();return {a:a.toJSON(),b:b.toJSON(),focus:document.activeElement.getAttribute('data-focus'),transform:document.getElementById('scene').getAttribute('transform')};})()`);
        assert(bounds.a.top >= bounds.b.top && bounds.a.bottom <= bounds.b.bottom && bounds.a.left >= bounds.b.left && bounds.a.right <= bounds.b.right, 'O foco por teclado deve permanecer visível após zoom: ' + JSON.stringify(bounds));
        await client.send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
      }
      await pause(150);
      if (process.argv.includes('--capture') && fixture.kind === 'demo') {
        const image = await client.send('Page.captureScreenshot', {format: 'png'});
        writeFileSync(path.join(root, 'docs', 'map-tree.png'), Buffer.from(image.data, 'base64'));
      }
      await client.evaluate('document.getElementById("view").value="mesh";document.getElementById("view").dispatchEvent(new Event("change"))');
      assert(await client.evaluate('document.querySelectorAll(".fdb-path").length >= 2'));
      assert(await client.evaluate('document.querySelectorAll(".device").length <= 16'));
      const target = fixture.kind === 'demo' ? '192.0.2.11' : '10.0.0.10';
      await client.evaluate(`document.querySelector('[data-node-id="${target}"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))`);
      assert.equal(await client.evaluate('document.getElementById("details").hidden'), false);
      await pause(150);
      if (process.argv.includes('--capture') && fixture.kind === 'demo') {
        const image = await client.send('Page.captureScreenshot', {format: 'png'});
        writeFileSync(path.join(root, 'docs', 'map-mesh.png'), Buffer.from(image.data, 'base64'));
      }
    } else if (fixture.count === 4096) {
      await client.evaluate('document.getElementById("view").value="mesh";document.getElementById("view").dispatchEvent(new Event("change"))');
      assert(await client.evaluate('document.querySelectorAll(".device").length <= 16'));
      await client.evaluate('document.getElementById("nextGroups").click()');
      assert.equal(await client.evaluate('document.getElementById("groupPageLabel").textContent'), '13–24 de 4096 dispositivos');
    }
    if (process.argv.includes('--capture') && fixture.count === 100) {
      await client.evaluate('document.getElementById("collapseAll").click()');
      const image = await client.send('Page.captureScreenshot', {format: 'png'});
      writeFileSync(path.join(root, 'docs', 'demo-map.png'), Buffer.from(image.data, 'base64'));
    }
    await client.send('Emulation.setDeviceMetricsOverride', {width: 600, height: 900, deviceScaleFactor: 1, mobile: false});
    await pause(150);
    assert(await client.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Janela compacta sem transbordamento horizontal');
    timings.push({kind: fixture.kind, count: fixture.count, validation_ms: Math.round(performance.now() - started)});
  }
  assert.deepEqual(errors, [], 'Erros JavaScript no navegador');
  assert(requests.every(url => url.startsWith('file:') || url.startsWith('data:')), 'O mapa tentou acessar a rede');
  writeFileSync(path.join(root, 'build', 'topology-smoke', 'report.json'), JSON.stringify({browser: version.product, cases: timings, errors, requests: requests.length}, null, 2));
  console.log(`Mapa OK: ${version.product}; grupos, árvore e malha; ${timings.length} cenários até ${Math.max(...timings.map(item=>item.count))} registros; exemplo com 129 equipamentos, foco animado, painel e navegação entre seis switches; relatos LLDP/CDP distintos da FDB, observador genérico, vizinho sem IP e VLAN parcial; busca, teclado, contexto, segurança e layout compacto; sem requisições externas da página.`);
} catch (error) {
  console.error(stderr); console.error(error); throw error;
} finally {
  try {if (client) await client.send('Browser.close');} catch {}
  client?.socket.close();
  if (child.exitCode === null) {
    await Promise.race([new Promise(resolve => child.once('exit', resolve)), pause(1500)]);
    if (child.exitCode === null) child.kill();
  }
  const resolved = path.resolve(directory);
  assert(path.dirname(resolved) === path.resolve(tmpdir()) && path.basename(resolved).startsWith('ish-map-smoke-'));
  try {
    await until(() => {try {rmSync(resolved, {recursive: true, force: true});return true;} catch {return false;}}, 'liberar perfil temporário', 6000);
  } catch {console.warn('O Windows ainda está liberando o perfil temporário do teste: ' + resolved);}
}

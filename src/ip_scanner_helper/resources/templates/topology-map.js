'use strict';

(() => {
  const graph = JSON.parse(document.getElementById('graph-data').textContent);
  const byId = new Map(graph.nodes.map(node => [node.id, node]));
  const svg = document.getElementById('map'), scene = document.getElementById('scene');
  const search = document.getElementById('search'), category = document.getElementById('category');
  const grouping = document.getElementById('grouping'), panel = document.getElementById('details');
  const view = document.getElementById('view');
  const links = graph.example ? graph.tree_links : graph.edges;
  const outgoing = new Map(), fdbSources = new Set();
  for (const link of links) {if (!outgoing.has(link.from)) outgoing.set(link.from, []); outgoing.get(link.from).push(link); if (link.kind === 'fdb_path') fdbSources.add(link.from);}
  const virtualNodes = new Map();
  for (const group of graph.groupings.switch) {
    if (group.observer_ip && !byId.has(group.observer_ip)) virtualNodes.set(group.observer_ip, {
      id: group.observer_ip, ip: group.observer_ip, nome: 'Observador fora do inventário', tipo: 'Referência FDB',
      icon: 'network', color: '#727b88', state: 'unknown', detail: 'Referência de uma tabela FDB. Equipamento não inventariado.'});
  }
  // Observers get navigation controls without changing their inventory category.
  const switchIds = [...graph.nodes.filter(node => foldType(node.tipo).includes('switch') || fdbSources.has(node.id) || node.neighbor_observer).map(node => node.id), ...virtualNodes.keys()];
  const switchSet = new Set(switchIds), expandedSwitches = new Set();
  let activeSwitch = null, childPage = 0, animation = 0;
  function foldType(value) {return String(value).toLocaleLowerCase();}
  const snapshotNode = id => byId.get(id) || virtualNodes.get(id);
  const principalIds = new Set([...switchIds, ...graph.nodes.filter(node => node.category === 'servers').map(node => node.id), graph.gateway]);
  const otherInfrastructure = graph.nodes.filter(node => node.category === 'infrastructure' && !principalIds.has(node.id)).map(node => node.id);
  for (const id of otherInfrastructure) principalIds.add(id);
  const mappedTargets = new Set(links.filter(edge => switchSet.has(edge.from)).map(edge => edge.to));
  const unmappedIds = graph.nodes.filter(node => !principalIds.has(node.id) && !mappedTargets.has(node.id)).map(node => node.id);
  virtualNodes.set('__unmapped__', {id: '__unmapped__', ip: '', nome: 'Sem associação registrada', tipo: 'Agrupamento lógico',
    icon: 'device', color: '#727b88', state: 'unknown', detail: 'Dispositivos sem caminho registrado para um observador. Este grupo não representa um equipamento.'});
  const gatewayId = graph.gateway || '__gateway__';
  if (!byId.has(gatewayId)) virtualNodes.set(gatewayId, {id: gatewayId, ip: graph.gateway || 'Não informado',
    nome: 'Gateway da interface', tipo: 'Referência da interface', icon: 'router', color: '#316c5a', state: 'unknown',
    detail: 'Referência da interface. Não estabelece presença nem ligação física com os switches.'});
  const expanded = new Set(), pages = new Map(), ns = 'http://www.w3.org/2000/svg';
  const pageSize = 12, groupsPageSize = 12;
  let selected = null, groupsPage = 0, scale = 1, offset = {x: 0, y: 0}, drag = null;
  let layout = {width: 1000, height: 500}, anchors = new Map();
  const fold = value => String(value).normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
  const icons = {
    router: 'M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20 M2 12h20 M12 2c-5 5-5 15 0 20c5-5 5-15 0-20',
    wifi: 'M2 8c6-6 14-6 20 0 M5 12c4-4 10-4 14 0 M8 16c2-2 6-2 8 0 M12 20h.01',
    network: 'M3 5h18v5H3z M6 8h1m3 0h1m3 0h1 M12 10v5 M4 19h16 M4 16v5m8-5v5m8-5v5',
    computer: 'M3 4h18v13H3z M8 21h8 M12 17v4',
    server: 'M4 3h16v8H4z M4 13h16v8H4z M7 7h1m3 0h6 M7 17h1m3 0h6',
    printer: 'M6 9V3h12v6 M6 17H3V9h18v8h-3 M6 14h12v7H6z M17 12h1',
    camera: 'M3 6h13v12H3z M16 10l5-3v10l-5-3 M6 9h3',
    phone: 'M7 3h10v18H7z M10 6h4v5h-4z M10 15h1m2 0h1m-4 3h1m2 0h1',
    device: 'M5 3h14v18H5z M9 7h6 M9 11h6 M11 17h2'
  };
  function element(tag, attrs = {}, text) {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function text(x, y, value, attrs = {}) {
    return element('text', {x, y, fill: '#243342', 'font-size': 13, ...attrs}, value);
  }
  function clippedText(x, y, value, width, attrs = {}) {
    const viewport = element('svg', {x, y:y-17, width, height:23, overflow:'hidden', 'aria-hidden':'true'});
    viewport.append(text(0,17,value,attrs)); return viewport;
  }
  function icon(name, x, y, color, size = 22) {
    const group = element('g', {transform: `translate(${x} ${y}) scale(${size / 24})`, 'aria-hidden': 'true'});
    group.append(element('path', {d: icons[name] || icons.device, fill: 'none', stroke: color,
      'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}));
    return group;
  }
  function shorten(value, available, pixels = 7) {
    const count = Math.max(3, Math.floor(available / pixels));
    return value.length > count ? value.slice(0, count - 1) + '…' : value;
  }
  function button(key, label, callback, attrs = {}) {
    const node = element('g', {tabindex: 0, role: 'button', 'aria-label': label, 'data-focus': key, ...attrs});
    node.addEventListener('click', event => {event.stopPropagation(); callback();});
    node.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); callback();}
    });
    return node;
  }
  function restoreFocus(key) {
    if (!key) return;
    const item = [...scene.querySelectorAll('[data-focus]')].find(node => node.dataset.focus === key);
    if (item) item.focus({preventScroll: true});
  }
  function transform() {scene.setAttribute('transform', `translate(${offset.x} ${offset.y}) scale(${scale})`);}
  function fit() {
    animation++;
    scale = Math.min(1.2, svg.clientWidth / layout.width, svg.clientHeight / layout.height);
    scale = Math.max(.2, scale);
    offset = {x: (svg.clientWidth - layout.width * scale) / 2, y: 12};
    transform();
  }
  function addAnchor(id, point) {
    if (!anchors.has(id)) anchors.set(id, []);
    anchors.get(id).push(point);
  }
  function matchingIds() {
    const words = fold(search.value.trim()).split(/\s+/).filter(Boolean);
    return new Set(graph.nodes.filter(node => (!category.value || node.category === category.value)
      && words.every(word => fold(`${node.nome} ${node.ip} ${node.tipo} ${node.detail}`).includes(word))).map(node => node.id));
  }
  function childrenOf(id) {
    if (id === '__unmapped__') return unmappedIds;
    return [...new Set((outgoing.get(id) || []).filter(edge => byId.has(edge.to) && !switchSet.has(edge.to) && edge.to !== graph.gateway).map(edge => edge.to))];
  }
  function eligibleSwitches(matches = matchingIds()) {
    const filtered = search.value.trim() || category.value;
    return switchIds.filter(id => !filtered || matches.has(id) || childrenOf(id).some(child => matches.has(child)));
  }
  function updateNavigation() {
    const ids = eligibleSwitches(), index = ids.indexOf(activeSwitch);
    document.getElementById('nextSwitch').disabled = !ids.length;
    document.getElementById('previousSwitch').disabled = !ids.length;
    document.getElementById('switchPosition').textContent = index >= 0 ? `${index + 1} / ${ids.length}` : `${ids.length} switches / observadores`;
  }
  function focusSwitch(id) {
    const anchor = anchors.get(id)?.[0];
    if (!anchor) return;
    const ticket = ++animation, start = performance.now(), initial = {scale, ...offset};
    const targetScale = Math.min(1.6, Math.max(1.15, scale));
    const target = {x: svg.clientWidth / 2 - anchor.x * targetScale, y: svg.clientHeight * .32 - anchor.y * targetScale};
    const duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 320;
    function frame(now) {
      if (ticket !== animation) return;
      const progress = duration ? Math.min(1, (now - start) / duration) : 1, ease = 1 - (1 - progress) ** 3;
      scale = initial.scale + (targetScale - initial.scale) * ease;
      offset = {x: initial.x + (target.x - initial.x) * ease, y: initial.y + (target.y - initial.y) * ease}; transform();
      if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function renderChildren() {
    const all = childrenOf(activeSwitch || ''), term = fold(document.getElementById('childSearch').value.trim());
    const filtered = all.filter(id => {const node = byId.get(id); return fold(`${node.nome} ${node.ip} ${node.tipo}`).includes(term);});
    childPage = Math.min(childPage, Math.max(0, Math.ceil(filtered.length / 24) - 1));
    const list = document.getElementById('childrenList'); list.replaceChildren();
    for (const id of filtered.slice(childPage * 24, (childPage + 1) * 24)) {
      const node = byId.get(id), row = document.createElement('button'); row.className = 'child-row'; row.dataset.childId = id;
      const name = document.createElement('strong'); name.textContent = node.nome;
      const detail = document.createElement('span'); detail.textContent = `${node.ip} · ${node.tipo}`;
      const status = document.createElement('i'); status.className = 'status-dot ' + (node.state || 'observed');
      row.append(status, name, detail); row.addEventListener('click', () => showDetails(id)); list.append(row);
    }
    if (!filtered.length) {const empty = document.createElement('p'); empty.textContent = 'Nenhum dispositivo nesta busca.'; list.append(empty);}
    const counts = new Map();
    for (const id of all) {const node = byId.get(id); counts.set(node.tipo, (counts.get(node.tipo) || 0) + 1);}
    document.getElementById('childCounts').textContent = [...counts].map(([kind, count]) => `${kind}: ${count}`).join(' · ');
    document.getElementById('childrenPageLabel').textContent = filtered.length ? `${childPage * 24 + 1}–${Math.min(filtered.length, (childPage + 1) * 24)} de ${filtered.length}` : '0 dispositivos';
    document.getElementById('previousChildren').disabled = childPage === 0;
    document.getElementById('nextChildren').disabled = (childPage + 1) * 24 >= filtered.length;
  }
  function visibleGroups(matches) {
    const size = pageSize;
    return graph.groupings[grouping.value].map(group => {
      const members = group.member_ids.filter(id => matches.has(id));
      const count = Math.ceil(members.length / size);
      const page = Math.min(pages.get(group.id) || 0, Math.max(0, count - 1));
      return {...group, matching_ids: members, page, pageCount: count, pageSize: size,
        open: expanded.has(group.id) || !!search.value.trim(),
        visible_ids: members.slice(page * size, (page + 1) * size)};
    }).filter(group => group.matching_ids.length);
  }
  function showDetails(id, focusKey) {
    const node = snapshotNode(id);
    if (!node) return;
    selected = id; panel.hidden = false;
    document.getElementById('detailTitle').textContent = node.nome;
    document.getElementById('detailSubtitle').textContent = node.ip + ' · ' + node.tipo;
    document.getElementById('detailBody').textContent = node.detail;
    const list = document.getElementById('relations'); list.replaceChildren();
    const paths = links.filter(edge => edge.to === id || edge.from === id);
    document.getElementById('relationCount').textContent = `${paths.length} relações ${graph.example ? 'do exemplo' : 'registradas'}`;
    for (const edge of paths) {
      const row = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = edge.kind === 'reported_neighbor' ? edge.label : `${edge.from} → ${edge.to} · ${edge.port}`;
      const detail = document.createElement('p');
      detail.textContent = `${edge.source} · ${edge.observed_at}. ${graph.example ? 'Relação fictícia.' : 'Vínculo direto não confirmado.'}`;
      row.append(title, detail); list.append(row);
    }
    if (!paths.length) {
      const row = document.createElement('li'); row.textContent = 'Nenhum caminho ou vizinho associado ao inventário. Relatos sem correspondência aparecem nos dados do equipamento.'; list.append(row);
    }
    const isSwitch = switchSet.has(id) || id === '__unmapped__';
    document.getElementById('detailTabs').hidden = !isSwitch;
    document.getElementById('switchPanel').hidden = !isSwitch;
    document.getElementById('evidencePanel').hidden = isSwitch;
    document.getElementById('backToSwitch').hidden = isSwitch || !activeSwitch;
    if (isSwitch) {
      activeSwitch = id; childPage = 0; document.getElementById('childSearch').value = ''; expandedSwitches.add(id);
      renderChildren();
      document.getElementById('detailSubtitle').textContent = `${node.ip} · ${childrenOf(id).length} dispositivos ${graph.example ? 'no exemplo' : 'observados'}`;
      const eligible = [...graph.nodes.filter(item => item.category === 'servers').map(item => item.id), ...eligibleSwitches()];
      const index = eligible.indexOf(id); if (index >= 0) groupsPage = Math.floor(index / 12);
    }
    render(false, focusKey); updateNavigation();
    if (isSwitch && view.value === 'tree') focusSwitch(id);
  }
  function drawCard(groupElement, group, card) {
    const node = byId.get(card.id), key = `node:${group.id}:${node.id}`;
    const item = button(key, `${node.nome}, ${node.ip}, ${node.tipo}`, () => showDetails(node.id, key),
      {class: 'device', 'data-node-id': node.id});
    item.append(element('rect', {x: card.x, y: card.y, width: card.width, height: card.height, rx: 6,
      fill: selected === node.id ? '#edf5f1' : '#fff', stroke: selected === node.id ? '#316c5a' : '#dce3e8'}));
    item.append(icon(node.icon, card.x + 10, card.y + 16, node.color, 20));
    item.append(clippedText(card.x + 39, card.y + 22, shorten(node.nome, card.width - 49, 6.8), card.width-49, {'font-weight': 600, 'font-size': 12}));
    item.append(text(card.x + 39, card.y + 40, node.ip + (node.is_gateway ? ' · GW' : ''), {'font-size': 11, fill: '#697888'}));
    item.append(element('title', {}, `${node.nome}\n${node.ip}\n${node.tipo}\nConfiança da categoria: ${node.confianca}`));
    const stateColors = {online: '#3b8a66', offline: '#a65d61', observed: '#3b8a66', partial: '#b48a47', unknown: '#8a97a4'};
    item.append(element('circle', {cx: card.x + card.width - 10, cy: card.y + 10, r: 3.5, fill: stateColors[node.state] || '#8a97a4'}));
    groupElement.append(item); addAnchor(node.id, {x: card.x + card.width / 2, y: card.y + card.height / 2,
      top: card.y, right: card.x + card.width, group: group.id});
  }
  function drawGroup(placement) {
    const {group, x, y, width, height} = placement;
    const container = element('g', {class: 'cluster', 'data-group-id': group.id});
    container.append(element('rect', {x, y, width, height, rx: 10, fill: '#f8fafb', stroke: '#dce3e8'}));
    const key = `group:${group.id}`;
    const toggle = button(key, `${group.open ? 'Recolher' : 'Expandir'} ${group.title}, ${group.matching_ids.length} dispositivos`, () => {
      if (search.value.trim()) {document.getElementById('status').textContent = 'Limpe a busca para recolher os resultados.'; return;}
      if (expanded.has(group.id)) expanded.delete(group.id); else expanded.add(group.id);
      render(false, key);
    }, {'aria-expanded': group.open, class: 'group-toggle'});
    toggle.append(element('rect', {x: x + 1, y: y + 1, width: width - 2, height: group.open ? 84 : height - 2, rx: 10, fill: '#fff'}));
    toggle.append(icon(group.icon, x + 18, y + 19, group.color, 24));
    toggle.append(clippedText(x + 54, y + 32, shorten(group.title, width - 104), width-104, {'font-size': 15, 'font-weight': 600}));
    toggle.append(text(x + width - 25, y + 33, group.open ? '−' : '+', {'font-size': 23, 'text-anchor': 'middle', fill: '#677786'}));
    toggle.append(text(x + 18, y + 59, `${group.matching_ids.length} dispositivos`, {'font-size': 12, fill: '#486459'}));
    toggle.append(text(x + 18, y + 82, shorten(group.subtitle, width - 36, 6), {'font-size': 11, fill: '#798592'}));
    toggle.append(element('title', {}, group.title + '\n' + group.subtitle)); container.append(toggle);
    if (group.open) {
      for (const id of group.context_ids) {
        const node = byId.get(id), contextKey = `context:${group.id}:${id}`;
        const context = button(contextKey, `Observador ${node.nome}, ${id}`, () => showDetails(id, contextKey));
        context.append(text(x + 18, y + 105, shorten(`Observador: ${node.nome} · ${id}`, width - 36, 6), {'font-size': 11, fill: '#356a78'}));
        container.append(context); addAnchor(id, {x: x + width / 2, y: y + 100, group: group.id});
      }
      for (const card of placement.cards) drawCard(container, group, card);
      const from = group.page * group.pageSize + 1, to = Math.min((group.page + 1) * group.pageSize, group.matching_ids.length);
      container.append(text(x + 18, y + height - 20, `${from}–${to} de ${group.matching_ids.length}`, {'font-size': 11, fill: '#798592'}));
      for (const [delta, label, dx] of [[-1, 'Anterior', 142], [1, 'Próxima', 76]]) {
        if (group.page + delta < 0 || group.page + delta >= group.pageCount) continue;
        const pageKey = `page:${group.id}:${delta}`;
        const control = button(pageKey, `${label} página de ${group.title}`, () => {
          pages.set(group.id, group.page + delta); render(false, key); // Stable keyboard focus after replacing the page.
        }, {'data-page-group': group.id, 'data-delta': delta});
        control.append(element('rect', {x: x + width - dx - 4, y: y + height - 38, width: 68, height: 29, rx: 4, fill: '#fff', stroke: '#dce3e8'}));
        control.append(text(x + width - dx + 29, y + height - 19, label, {'text-anchor': 'middle', 'font-size': 11})); container.append(control);
      }
    }
    scene.append(container);
  }
  function drawPaths() {
    if ((!selected && view.value !== 'mesh') || view.value === 'tree' || !document.getElementById('showPaths').checked) return;
    const layer = element('g', {class: 'paths'});
    const paths = links.filter(item => view.value === 'mesh' || item.from === selected || item.to === selected);
    let drawn = 0;
    for (const edge of paths) {
      const sources = anchors.get(edge.from) || [], targets = anchors.get(edge.to) || [];
      if (!sources.length || !targets.length) continue;
      if (drawn++ >= 200) break;
      const a = sources[0], b = targets.find(point => point.group === a.group) || targets[0];
      const mid = (a.y + b.y) / 2;
      let route = `M${a.x} ${a.y} C${a.x} ${mid},${b.x} ${mid},${b.x} ${b.y}`;
      if (view.value === 'mesh') {
        if (a.top === b.top) {
          const bend = 34 + (drawn % 3) * 12;
          route = `M${a.x} ${a.top} C${a.x} ${a.top - bend},${b.x} ${b.top - bend},${b.x} ${b.top}`;
        } else {
          const channel = Math.max(a.right, b.right) + 15;
          route = `M${a.x} ${a.top} V${a.top - 20} H${channel} V${b.top - 20} H${b.x} V${b.top}`;
        }
      }
      const path = element('path', {d: route,
        class: 'fdb-path', stroke: edge.kind === 'reported_neighbor' ? '#516d9a' : '#557d80', 'stroke-width': 2, 'stroke-dasharray': edge.kind === 'reported_neighbor' ? '2 4' : '5 5', fill: 'none',
        opacity: selected && edge.from !== selected && edge.to !== selected ? .2 : 1,
        tabindex: 0, role: 'button', 'aria-label': edge.label, 'data-kind': edge.kind});
      path.append(element('title', {}, `${edge.label}\n${edge.source} · ${edge.observed_at}`));
      const announce = () => {document.getElementById('status').textContent = edge.label + '. ' + edge.source + ' · ' + edge.observed_at;};
      path.addEventListener('click', announce);
      path.addEventListener('keydown', event => {if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); announce();}});
      layer.append(path);
    }
    if (view.value === 'mesh') scene.prepend(layer); else scene.append(layer);
  }
  function renderMesh(matches, reset, focusKey) {
    const matched = graph.nodes.filter(node => matches.has(node.id));
    const count = Math.ceil(matched.length / pageSize);
    groupsPage = Math.min(groupsPage, Math.max(0, count - 1));
    const nodes = matched.slice(groupsPage * pageSize, (groupsPage + 1) * pageSize);
    const shown = new Set(nodes.map(node => node.id));
    let contexts = 0;
    for (const edge of links) {
      if (shown.has(edge.to) && !shown.has(edge.from) && byId.has(edge.from) && contexts < 4) {
        nodes.unshift(byId.get(edge.from)); shown.add(edge.from); contexts++;
      }
    }
    layout = layoutTopologyMesh(nodes, svg.clientWidth);
    const layer = element('g', {class: 'mesh-nodes'});
    for (const card of layout.cards) drawCard(layer, {id: 'mesh'}, card);
    scene.append(layer); drawPaths();
    document.getElementById('summary').textContent = `${matches.size} de ${graph.nodes.length} dispositivos · ${nodes.length} visíveis na malha`;
    document.getElementById('empty').hidden = nodes.length > 0;
    document.getElementById('groupPages').hidden = count <= 1;
    document.getElementById('groupPageLabel').textContent = `${groupsPage * pageSize + 1}–${Math.min(matched.length, (groupsPage + 1) * pageSize)} de ${matched.length} dispositivos`;
    document.getElementById('previousGroups').disabled = groupsPage === 0;
    document.getElementById('nextGroups').disabled = groupsPage + 1 >= count;
    document.getElementById('status').textContent = `${graph.example ? 'Malha do exemplo fictício' : 'Malha de caminhos e vizinhos'} · ${contexts} observadores de contexto. Até 12 resultados e 200 caminhos por página; evidências completas nos detalhes.`;
    if (reset) fit(); else transform(); restoreFocus(focusKey);
  }
  function renderHierarchy(matches, reset, focusKey) {
    const filtered = search.value.trim() || category.value;
    const servers = graph.nodes.filter(node => node.category === 'servers' && node.id !== gatewayId).map(node => node.id);
    const relevant = new Set(eligibleSwitches(matches));
    if (graph.example && filtered) {
      const pending = [...relevant];
      for (let i = 0; i < pending.length; i++) for (const edge of links.filter(item => item.to === pending[i])) {
        if (switchSet.has(edge.from) && !relevant.has(edge.from)) {relevant.add(edge.from);pending.push(edge.from);}
      }
    }
    const principals = [...new Set([...servers, ...otherInfrastructure, ...switchIds.filter(id => relevant.has(id))])].filter(id => id !== gatewayId);
    groupsPage = Math.min(groupsPage, Math.max(0, Math.ceil(principals.length / 12) - 1));
    const focused = activeSwitch && !panel.hidden && (switchSet.has(activeSwitch) || activeSwitch === '__unmapped__');
    const page = focused ? (activeSwitch === '__unmapped__' ? [] : [activeSwitch]) : principals.slice(groupsPage * 12, (groupsPage + 1) * 12);
    const depth = new Map([[gatewayId, 0]]);
    if (graph.example) {
      const pending = [gatewayId];
      for (let i = 0; i < pending.length; i++) for (const edge of outgoing.get(pending[i]) || []) {
        if (!depth.has(edge.to)) {depth.set(edge.to, depth.get(edge.from) + 1); pending.push(edge.to);}
      }
    }
    const items = focused ? [] : [{id: gatewayId, depth: 0, context: !byId.has(gatewayId)}];
    for (const id of page) items.push({id, depth: focused ? 0 : graph.example ? depth.get(id) || 2 : servers.includes(id) ? 1 : 2, switch: switchSet.has(id)});
    const lastLevel = focused ? 0 : Math.max(2, ...items.map(item => item.depth));
    const present = new Set(items.map(item => item.id));
    for (const id of page.filter(item => switchSet.has(item))) {
      const children = childrenOf(id).filter(child => !filtered || matches.has(child));
      if (search.value.trim() && children.length) expandedSwitches.add(id);
      if (!expandedSwitches.has(id)) continue;
      for (const child of children.slice(0, 12)) if (!present.has(child)) {
        present.add(child); items.push({id: child, depth: lastLevel + 1});
      }
    }
    const unmapped = unmappedIds.filter(id => !filtered || matches.has(id));
    if (unmapped.length && (!focused || activeSwitch === '__unmapped__')) {
      items.push({id: '__unmapped__', depth: lastLevel + 1, switch: true, grouping: true});
      if (expandedSwitches.has('__unmapped__') || search.value.trim()) for (const id of unmapped.slice(0, 12)) items.push({id, depth: lastLevel + 2});
    }
    layout = layoutTopologyTree(items, svg.clientWidth, {maxColumns: focused ? 4 : 6});
    for (const card of layout.cards) {
      const node = snapshotNode(card.id), key = `tree:${card.id}`;
      const control = button(key, `${node.nome}, ${node.ip}${card.switch ? ', expandir dispositivos' : ''}`, () => showDetails(card.id, key),
        {class: byId.has(card.id) ? 'device tree-card' : 'context-node tree-card', 'data-node-id': card.id});
      const selectedCard = selected === card.id;
      control.append(element('rect', {x: card.x, y: card.y, width: card.width, height: card.height, rx: 7,
        fill: selectedCard ? '#edf5f1' : card.id === gatewayId ? '#f4f8f6' : '#fff', stroke: selectedCard ? '#316c5a' : '#d5dfe4'}));
      control.append(icon(node.icon, card.x + 12, card.y + 15, node.color, 22));
      control.append(clippedText(card.x + 42, card.y + 23, shorten(node.nome, card.width - 57, 6.7), card.width-57, {'font-size': 12, 'font-weight': 600}));
      control.append(text(card.x + 42, card.y + 42, node.ip || 'Grupo lógico', {'font-size': 11, fill: '#6b7989'}));
      if (byId.has(card.id)) control.append(element('circle', {cx: card.x + card.width - 10, cy: card.y + 10, r: 3.5,
        fill: ({online:'#3b8a66',offline:'#a65d61',partial:'#b48a47',observed:'#3b8a66'})[node.state] || '#8a97a4'}));
      if (card.switch) {
        const count = card.grouping ? unmappedIds.length : childrenOf(card.id).length;
        control.append(text(card.x + 12, card.y + 65, `${count} dispositivos · ${expandedSwitches.has(card.id) ? 'recolher −' : 'expandir +'}`, {'font-size': 11, fill: '#486b5d'}));
      }
      control.append(element('title', {}, `${node.nome}\n${node.ip}\n${node.tipo}\n${graph.example ? 'Estado fictício: ' + node.state : 'Dados do inventário; vínculos físicos não confirmados'}`));
      scene.append(control); addAnchor(card.id, {x:card.x+card.width/2,y:card.y+card.height/2,top:card.y,bottom:card.y+card.height,right:card.x+card.width,group:'tree'});
      if (card.switch && expandedSwitches.has(card.id)) {
        const collapse = button(`collapse:${card.id}`, `Recolher ramo de ${node.nome}`, () => {expandedSwitches.delete(card.id); render(false, key);}, {'data-collapse-id': card.id});
        collapse.append(element('rect', {x:card.x+card.width-27,y:card.y+card.height-25,width:24,height:22,rx:4,fill:'#f4f8f6'}));
        collapse.append(text(card.x+card.width-15,card.y+card.height-9,'−',{'text-anchor':'middle','font-size':16,fill:'#316c5a'})); scene.append(collapse);
      }
    }
    if (document.getElementById('showPaths').checked) {
      const layer = element('g', {class:'tree-paths'});
      for (const edge of links) {
        const a = anchors.get(edge.from)?.[0], b = anchors.get(edge.to)?.[0]; if (!a || !b) continue;
        const mid = (a.bottom + b.top) / 2;
        let route = a.top === b.top ? `M${a.x} ${a.top} C${a.x} ${a.top-32},${b.x} ${b.top-32},${b.x} ${b.top}`
          : `M${a.x} ${a.bottom} C${a.x} ${mid},${b.x} ${mid},${b.x} ${b.top}`;
        if (focused && edge.from === activeSwitch) {
          const targetCard = layout.cards.find(card => card.id === edge.to), channel = targetCard.x - 12;
          const firstRow = Math.min(...layout.cards.filter(card => card.id !== activeSwitch).map(card => card.y));
          const bus = firstRow - 32;
          route = `M${a.x} ${a.bottom} V${bus} H${channel} V${b.top-14} H${b.x} V${b.top}`;
        }
        const path = element('path', {d:route, class:'tree-branch',fill:'none',stroke:edge.kind === 'reported_neighbor'?'#516d9a':'#829e99','stroke-width':1.5,
          'stroke-dasharray':graph.example?'':edge.kind === 'reported_neighbor'?'2 4':'5 5','data-kind':edge.kind,'aria-label':edge.label});
        path.append(element('title',{},edge.label));layer.append(path);
      }
      scene.prepend(layer);
    }
    document.getElementById('summary').textContent = `${matches.size} dispositivos`;
    document.getElementById('empty').hidden = graph.nodes.length > 0;
    document.getElementById('groupPages').hidden = principals.length <= 12;
    document.getElementById('groupPageLabel').textContent = `${groupsPage*12+1}–${Math.min(principals.length,(groupsPage+1)*12)} de ${principals.length} principais`;
    document.getElementById('previousGroups').disabled = groupsPage === 0;
    document.getElementById('nextGroups').disabled = (groupsPage + 1) * 12 >= principals.length;
    document.getElementById('status').textContent = graph.example ? 'Exemplo JSON · hierarquia e estados fictícios. Selecione um switch para explorar.'
      : 'Posições lógicas · verde: FDB; azul: relato LLDP/CDP. Linhas não certificam cabos. Gateway é referência. Sem resposta não significa offline.';
    updateNavigation(); if (reset) fit(); else transform(); restoreFocus(focusKey);
  }
  function render(reset = false, focusKey = null) {
    animation++;
    scene.replaceChildren(); anchors = new Map();
    svg.setAttribute('viewBox', `0 0 ${svg.clientWidth} ${svg.clientHeight}`);
    if (view.value === 'mesh') {renderMesh(matchingIds(), reset, focusKey); return;}
    if (view.value === 'tree') {renderHierarchy(matchingIds(), reset, focusKey); return;}
    const matches = matchingIds(), groups = visibleGroups(matches);
    groupsPage = Math.min(groupsPage, Math.max(0, Math.ceil(groups.length / groupsPageSize) - 1));
    const visible = groups.slice(groupsPage * groupsPageSize, (groupsPage + 1) * groupsPageSize);
    layout = layoutTopologyGroups(visible, svg.clientWidth);
    for (const placement of layout.groups) drawGroup(placement);
    drawPaths();
    const active = !!search.value.trim() || !!category.value;
    document.getElementById('summary').textContent = `${matches.size} de ${graph.nodes.length} dispositivos · ${groups.length} grupos`;
    document.getElementById('empty').hidden = groups.length > 0;
    document.getElementById('groupPages').hidden = groups.length <= groupsPageSize;
    document.getElementById('groupPageLabel').textContent = `${groupsPage * groupsPageSize + 1}–${Math.min(groups.length, (groupsPage + 1) * groupsPageSize)} de ${groups.length} grupos`;
    document.getElementById('previousGroups').disabled = groupsPage === 0;
    document.getElementById('nextGroups').disabled = (groupsPage + 1) * groupsPageSize >= groups.length;
    document.getElementById('status').textContent = active ? 'Resultados filtrados; observadores FDB são mantidos como contexto nos grupos abertos.' : 'Grupos lógicos não representam cabos. Selecione um equipamento para consultar as evidências.';
    if (reset) fit(); else transform();
    restoreFocus(focusKey);
  }
  function filterChanged() {
    groupsPage = 0; pages.clear();
    if (selected && !matchingIds().has(selected)) {selected = null; panel.hidden = true;}
    render(true);
  }
  for (const group of graph.groupings.category) {
    const option = document.createElement('option'); option.value = group.id.slice('category:'.length); option.textContent = group.title; category.append(option);
  }
  search.addEventListener('input', filterChanged); category.addEventListener('change', filterChanged);
  grouping.addEventListener('change', () => {groupsPage = 0; pages.clear(); render(true);});
  view.addEventListener('change', () => {
    groupsPage = 0; pages.clear(); grouping.disabled = view.value !== 'groups';
    if (view.value === 'tree') grouping.value = 'switch';
    grouping.closest('.field').hidden = view.value !== 'groups';
    document.getElementById('switchNavigation').hidden = view.value !== 'tree';
    document.getElementById('expandAll').hidden = view.value === 'mesh';
    document.getElementById('collapseAll').hidden = view.value === 'mesh'; render(true);
  });
  document.getElementById('clear').addEventListener('click', () => {search.value = ''; category.value = ''; filterChanged(); search.focus();});
  document.getElementById('expandAll').addEventListener('click', () => {
    if (view.value === 'tree') {for (const id of eligibleSwitches()) expandedSwitches.add(id); expandedSwitches.add('__unmapped__');}
    else for (const group of graph.groupings[grouping.value]) expanded.add(group.id); render(true);
  });
  document.getElementById('collapseAll').addEventListener('click', () => {expanded.clear(); expandedSwitches.clear(); search.value = ''; render(true);});
  document.getElementById('fit').addEventListener('click', fit);
  document.getElementById('showPaths').addEventListener('change', () => render());
  document.getElementById('previousGroups').addEventListener('click', () => {groupsPage--; render(true);});
  document.getElementById('nextGroups').addEventListener('click', () => {groupsPage++; render(true);});
  document.getElementById('closeDetails').addEventListener('click', () => {selected = null; panel.hidden = true; render(true); svg.focus();});
  function navigateSwitch(delta) {
    const ids = eligibleSwitches(); if (!ids.length) return;
    const current = ids.indexOf(activeSwitch), index = current < 0 ? 0 : (current + delta + ids.length) % ids.length;
    showDetails(ids[index]);
  }
  document.getElementById('nextSwitch').addEventListener('click', () => navigateSwitch(1));
  document.getElementById('previousSwitch').addEventListener('click', () => navigateSwitch(-1));
  document.getElementById('overview').addEventListener('click', () => {
    activeSwitch = selected = null; expandedSwitches.clear(); panel.hidden = true; search.value = ''; category.value = '';
    view.value = 'tree'; view.dispatchEvent(new Event('change'));
  });
  document.getElementById('childSearch').addEventListener('input', () => {childPage = 0; renderChildren();});
  document.getElementById('previousChildren').addEventListener('click', () => {childPage--; renderChildren();});
  document.getElementById('nextChildren').addEventListener('click', () => {childPage++; renderChildren();});
  document.getElementById('devicesTab').addEventListener('click', () => {document.getElementById('switchPanel').hidden = false; document.getElementById('evidencePanel').hidden = true;});
  document.getElementById('evidenceTab').addEventListener('click', () => {document.getElementById('switchPanel').hidden = true; document.getElementById('evidencePanel').hidden = false;});
  document.getElementById('backToSwitch').addEventListener('click', () => {if (activeSwitch) showDetails(activeSwitch);});
  function zoom(factor) {
    animation++;
    const previous = scale; scale = Math.min(3, Math.max(.2, scale * factor));
    const center = {x: svg.clientWidth / 2, y: svg.clientHeight / 2};
    offset = {x: center.x - (center.x - offset.x) * scale / previous, y: center.y - (center.y - offset.y) * scale / previous}; transform();
  }
  document.getElementById('zoomIn').addEventListener('click', () => zoom(1.2));
  document.getElementById('zoomOut').addEventListener('click', () => zoom(1 / 1.2));
  svg.addEventListener('wheel', event => {event.preventDefault(); zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1);}, {passive: false});
  svg.addEventListener('pointerdown', event => {
    if (event.target.closest('[role="button"]')) return;
    animation++;
    drag = {x: event.clientX, y: event.clientY, ox: offset.x, oy: offset.y}; svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener('pointermove', event => {if (drag) {offset = {x: drag.ox + event.clientX - drag.x, y: drag.oy + event.clientY - drag.y}; transform();}});
  svg.addEventListener('pointerup', () => {drag = null;}); svg.addEventListener('pointercancel', () => {drag = null;});
  svg.addEventListener('focus', event => {
    if (event.target === svg || !event.target.getBBox) return;
    const box = (event.target.querySelector?.('rect') || event.target).getBBox(), padding = 12;
    const left = box.x * scale + offset.x, top = box.y * scale + offset.y;
    const right = (box.x + box.width) * scale + offset.x, bottom = (box.y + box.height) * scale + offset.y;
    if (left < padding) offset.x += padding - left;
    else if (right > svg.clientWidth - padding) offset.x -= right - svg.clientWidth + padding;
    if (top < padding) offset.y += padding - top;
    else if (bottom > svg.clientHeight - padding) offset.y -= bottom - svg.clientHeight + padding;
    transform();
  }, true);
  svg.addEventListener('keydown', event => {
    if (event.target !== svg) return;
    const moves = {ArrowLeft: [50, 0], ArrowRight: [-50, 0], ArrowUp: [0, 50], ArrowDown: [0, -50]};
    if (moves[event.key]) {event.preventDefault(); const [x, y] = moves[event.key]; offset.x += x; offset.y += y; transform();}
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {event.preventDefault(); search.focus(); search.select();}
    if (event.key === 'Escape') {selected = null; panel.hidden = true; render(true); search.focus();}
  });
  document.addEventListener('pointerdown', event => {if (!event.target.closest('.filters')) document.querySelector('.filters').open = false;});
  let resizeTimer;
  new ResizeObserver(() => {clearTimeout(resizeTimer); resizeTimer = setTimeout(() => {render(true);if(view.value==='tree' && selected) focusSwitch(selected);}, 80);}).observe(svg);
  document.getElementById('graphKind').textContent = graph.example ? 'Exemplo fictício' : 'Inventário observado';
  view.dispatchEvent(new Event('change'));
})();

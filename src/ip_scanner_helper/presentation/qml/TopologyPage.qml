import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../resources/templates/topology-layout.js" as Geometry

Item {
    id: page
    signal inspectRequested(string ip)
    property var graph: ({nodes: [], edges: [], groupings: {category: [], switch: []}})
    property var geometry: ({cards: [], width: 960, height: 300})
    property var expanded: ({})
    property var selected: ({})
    property real zoom: 1
    property real panX: 0
    property real panY: 0
    property int revision: -1
    readonly property int cardCount: geometry.cards.length

    function refresh(fit) {
        graph = scanner.topologySnapshot();
        revision = scanner.state.inventoryRevision;
        if (selected.id) selected = graph.nodes.find(function(node) { return node.id === selected.id; }) || ({});
        arrange(fit);
    }
    function arrange(fit) {
        let cards = [], query = search.text.trim().toLowerCase(), nodes = graph.nodes || [];
        function matches(node) { return !query || (node.ip + " " + node.nome + " " + node.tipo).toLowerCase().indexOf(query) >= 0; }
        function card(node, depth) {
            return {id: node.id, ip: node.ip, title: node.nome, subtitle: node.ip + " · " + node.tipo,
                    depth: depth, group: false, color: node.color, state: node.state, icon: node.icon};
        }
        if (grouping.currentIndex === 2) {
            nodes.filter(matches).forEach(function(node) { cards.push(card(node, node.is_gateway ? 0 : node.category === "infrastructure" ? 1 : 2)); });
        } else {
            let byId = {}, anchors = {};
            nodes.forEach(function(node) {
                byId[node.id] = node;
                if (node.is_gateway || node.category === "infrastructure" || node.neighbor_observer) {
                    anchors[node.id] = true;
                    cards.push(card(node, node.is_gateway ? 0 : 1));
                }
            });
            let groups = graph.groupings[grouping.currentIndex === 1 ? "switch" : "category"] || [];
            groups.forEach(function(group) {
                let ids = group.member_ids.filter(function(ip) { return byId[ip] && !anchors[ip] && matches(byId[ip]); });
                if (!ids.length) return;
                let open = !!expanded[group.id] || !!query;
                cards.push({id: group.id, title: group.title, subtitle: ids.length + (ids.length === 1 ? " equipamento · " : " equipamentos · ") + (open ? "Recolher" : "Expandir"),
                            depth: 2, group: true, color: group.color, open: open});
                if (open) ids.forEach(function(ip) { cards.push(card(byId[ip], 3)); });
            });
        }
        geometry = Geometry.layoutTopologyTree(cards, Math.max(720, viewport.width - 24));
        if (fit) fitAll();
        else viewport.requestPaint();
    }
    function fitAll() {
        if (viewport.width <= 0 || viewport.height <= 0) return;
        zoom = Math.max(0.001, Math.min(1.3, Math.min((viewport.width - 40) / geometry.width, (viewport.height - 40) / geometry.height)));
        panX = (viewport.width - geometry.width * zoom) / 2;
        panY = (viewport.height - geometry.height * zoom) / 2;
        viewport.requestPaint();
    }
    function zoomAt(factor, x, y) {
        let next = Math.max(0.001, Math.min(3, zoom * factor)), ratio = next / zoom;
        panX = x - (x - panX) * ratio; panY = y - (y - panY) * ratio;
        zoom = next; viewport.requestPaint();
    }
    function pick(x, y) {
        let wx = (x - panX) / zoom, wy = (y - panY) / zoom;
        for (let i = geometry.cards.length - 1; i >= 0; --i) {
            let card = geometry.cards[i];
            if (wx < card.x || wx > card.x + card.width || wy < card.y || wy > card.y + card.height) continue;
            if (card.group) {
                let next = Object.assign({}, expanded); next[card.id] = !card.open; expanded = next; arrange(false);
            } else {
                selected = graph.nodes.find(function(node) { return node.id === card.id; }) || ({});
                viewport.requestPaint();
            }
            return;
        }
        selected = ({}); viewport.requestPaint();
    }
    function detailsText() {
        let labels = {nome:"Nome", ip:"IP", mac:"MAC", tipo:"Categoria", fabricante:"Fabricante",
                      latencia:"Latência", origem:"Origem do nome", confianca:"Confiança",
                      evidencia_categoria:"Evidência da categoria", status:"Estado", visto_em:"Observado em"};
        return String(selected.detail || "").split("\n").map(function(line) {
            let separator = line.indexOf(":");
            let key = separator > 0 ? line.slice(0, separator) : "";
            return labels[key] ? labels[key] + line.slice(separator) : line;
        }).join("\n");
    }
    Timer { id: refreshTimer; interval: 300; onTriggered: { if (page.visible && page.revision !== scanner.state.inventoryRevision) page.refresh(false); } }
    Connections { target: scanner; function onStateChanged() { if (page.visible && !refreshTimer.running && page.revision !== scanner.state.inventoryRevision) refreshTimer.start(); } }
    Connections { target: Theme; function onDarkChanged() { viewport.requestPaint(); } }

    ColumnLayout {
        anchors.fill: parent; spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Text { textFormat: Text.PlainText; text: "Topologia"; color: Theme.ink; font.pixelSize: 22; font.weight: Font.DemiBold }
            Item { Layout.fillWidth: true }
            Text { textFormat: Text.PlainText; text: page.graph.nodes.length + " equipamentos"; color: Theme.muted; font.pixelSize: 12 }
            AppButton { objectName: "topologyExternal"; text: "Abrir mapa detalhado"; enabled: page.graph.nodes.length > 0; onClicked: scanner.openMap() }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            AppCombo { id: grouping; objectName: "topologyGrouping"; model: ["Por categoria", "Por switch", "Malha"]; Layout.preferredWidth: 150; onActivated: page.arrange(true) }
            AppField { id: search; objectName: "topologySearch"; placeholderText: "Buscar IP, nome ou categoria"; Layout.fillWidth: true; onTextEdited: page.arrange(true) }
            AppButton { objectName: "topologyRefresh"; text: "Atualizar"; onClicked: page.refresh(false) }
            AppButton { objectName: "topologyZoomOut"; text: "−"; implicitWidth: 40; hint: "Reduzir"; onClicked: page.zoomAt(0.8, viewport.width / 2, viewport.height / 2) }
            AppButton { objectName: "topologyZoomIn"; text: "+"; implicitWidth: 40; hint: "Ampliar"; onClicked: page.zoomAt(1.25, viewport.width / 2, viewport.height / 2) }
            AppButton { objectName: "topologyFit"; text: "Enquadrar"; onClicked: page.fitAll() }
        }
        Text { textFormat: Text.PlainText; text: "Arraste para mover · Role para ampliar · Clique nos grupos para expandir"; color: Theme.muted; font.pixelSize: 12 }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.minimumWidth: 320
                color: Theme.background; radius: 8; border.color: Theme.border; clip: true
                Canvas {
                    id: viewport; objectName: "topologyCanvas"
                    anchors.fill: parent; activeFocusOnTab: true
                    onWidthChanged: { if (page.visible) Qt.callLater(function() { page.arrange(true); }); }
                    onHeightChanged: { if (page.visible) Qt.callLater(page.fitAll); }
                    Accessible.role: Accessible.Graphic
                    Accessible.name: "Mapa de relações observadas. Use os controles para ampliar ou enquadrar."
                    function rounded(ctx, x, y, w, h) {
                        ctx.beginPath(); ctx.moveTo(x + 7, y); ctx.lineTo(x + w - 7, y); ctx.quadraticCurveTo(x + w, y, x + w, y + 7);
                        ctx.lineTo(x + w, y + h - 7); ctx.quadraticCurveTo(x + w, y + h, x + w - 7, y + h);
                        ctx.lineTo(x + 7, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - 7);
                        ctx.lineTo(x, y + 7); ctx.quadraticCurveTo(x, y, x + 7, y); ctx.closePath();
                    }
                    function shorten(ctx, value, width) {
                        let text = String(value || "");
                        while (text.length > 1 && ctx.measureText(text).width > width) text = text.slice(0, -2) + "…";
                        return text;
                    }
                    onPaint: {
                        let ctx = getContext("2d"); ctx.reset(); ctx.clearRect(0, 0, width, height);
                        ctx.translate(page.panX, page.panY); ctx.scale(page.zoom, page.zoom);
                        let cards = page.geometry.cards, byId = {};
                        cards.forEach(function(card) { if (!card.group && !byId[card.id]) byId[card.id] = card; });
                        page.graph.edges.forEach(function(edge) {
                            let a = byId[edge.from], b = byId[edge.to];
                            if (!a || !b) return;
                            ctx.strokeStyle = edge.kind === "reported_neighbor" ? "#4c8aab" : Theme.accent;
                            ctx.lineWidth = 1.4;
                            if (typeof ctx.setLineDash === "function") ctx.setLineDash(edge.kind === "reported_neighbor" ? [3, 4] : [8, 5]);
                            let ax = a.x + a.width / 2, ay = a.y + a.height, bx = b.x + b.width / 2, by = b.y;
                            ctx.beginPath(); ctx.moveTo(ax, ay); ctx.bezierCurveTo(ax, ay + 35, bx, by - 35, bx, by); ctx.stroke();
                        });
                        if (typeof ctx.setLineDash === "function") ctx.setLineDash([]);
                        for (let i = 0; i < cards.length; ++i) {
                            let card = cards[i];
                            if ((card.x + card.width) * page.zoom + page.panX < 0 || card.x * page.zoom + page.panX > width ||
                                (card.y + card.height) * page.zoom + page.panY < 0 || card.y * page.zoom + page.panY > height) continue;
                            rounded(ctx, card.x, card.y, card.width, card.height);
                            ctx.fillStyle = page.selected.id === card.id ? Theme.selection : Theme.surface; ctx.fill();
                            ctx.strokeStyle = page.selected.id === card.id ? Theme.accent : Theme.border; ctx.lineWidth = 1; ctx.stroke();
                            ctx.fillStyle = card.state === "partial" ? Theme.warning : card.color;
                            ctx.fillRect(card.x + 12, card.y + 14, 4, 30);
                            if (page.zoom < 0.15) continue;
                            ctx.fillStyle = Theme.ink; ctx.font = "600 13px Segoe UI";
                            ctx.fillText(shorten(ctx, (card.group ? (card.open ? "− " : "+ ") : "") + card.title, card.width - 35), card.x + 24, card.y + 25);
                            ctx.fillStyle = Theme.muted; ctx.font = "11px Segoe UI";
                            ctx.fillText(shorten(ctx, card.subtitle, card.width - 35), card.x + 24, card.y + 44);
                        }
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) { page.zoomAt(1.25, width / 2, height / 2); event.accepted = true; }
                        else if (event.key === Qt.Key_Minus) { page.zoomAt(0.8, width / 2, height / 2); event.accepted = true; }
                        else if (event.key === Qt.Key_0) { page.fitAll(); event.accepted = true; }
                        else if (event.key === Qt.Key_Return && page.selected.id) { page.inspectRequested(page.selected.ip); event.accepted = true; }
                    }
                    MouseArea {
                        anchors.fill: parent
                        property real startX: 0
                        property real startY: 0
                        property real baseX: 0
                        property real baseY: 0
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                        onPressed: function(mouse) { viewport.forceActiveFocus(); startX = mouse.x; startY = mouse.y; baseX = page.panX; baseY = page.panY; }
                        onPositionChanged: function(mouse) { if (pressed) { page.panX = baseX + mouse.x - startX; page.panY = baseY + mouse.y - startY; viewport.requestPaint(); } }
                        onReleased: function(mouse) { if (Math.abs(mouse.x - startX) + Math.abs(mouse.y - startY) < 6) page.pick(mouse.x, mouse.y); }
                        onWheel: function(wheel) { page.zoomAt(wheel.angleDelta.y > 0 ? 1.15 : 1 / 1.15, wheel.x, wheel.y); wheel.accepted = true; }
                    }
                }
                ColumnLayout {
                    anchors.centerIn: parent; width: Math.min(400, parent.width - 40); spacing: 10
                    visible: page.graph.nodes.length === 0
                    Text { textFormat: Text.PlainText; text: "Nenhum equipamento nesta visualização"; font.pixelSize: 17; font.weight: Font.DemiBold; color: Theme.ink; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                    Text { textFormat: Text.PlainText; text: "Faça uma coleta no Inventário ou abra uma sessão no Histórico."; color: Theme.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
                }
            }
            ColumnLayout {
                visible: !!page.selected.id; Layout.preferredWidth: page.width < 1000 ? 250 : 300
                Layout.minimumWidth: page.width < 1000 ? 250 : 300
                Layout.maximumWidth: page.width < 1000 ? 250 : 300
                Layout.fillHeight: true; spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; text: "Equipamento"; color: Theme.ink; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    AppButton { objectName: "topologyCloseDetails"; text: "Fechar"; onClicked: { page.selected = ({}); viewport.requestPaint(); } }
                }
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth
                    TextArea { text: page.detailsText(); textFormat: TextEdit.PlainText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.ink; font.pixelSize: 12; background: null }
                }
                AppButton { objectName: "topologyInspect"; text: "Ver no inventário"; Layout.fillWidth: true; onClicked: page.inspectRequested(page.selected.ip) }
            }
        }
        Text { text: "Verde: caminho FDB · Azul: relato LLDP/CDP · Grupos são lógicos. Relações observadas não comprovam cabeamento direto."; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}

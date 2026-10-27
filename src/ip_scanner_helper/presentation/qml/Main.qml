import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models

ApplicationWindow {
    id: root
    objectName: "scannerWindow"
    width: 1440; height: 900
    minimumWidth: 960; minimumHeight: 640
    visible: true
    title: "IP Scanner Helper"
    color: Theme.background
    font.family: Theme.font
    font.pixelSize: 14
    property string hoveredIp: ""
    property int detailTab: 0
    property string switchMethod: "snmp"
    property real savedScroll: 0
    property var state: scanner.state
    function syncSettings() {
        modeBox.currentIndex = scanner.state.mode === "Rápido" ? 0 : 1;
        workers.text = String(scanner.state.workers);
        targetTimeout.text = String(scanner.state.targetTimeout);
    }
    function rememberScanDefaults() {
        scanner.setScanDefaults(modeBox.currentText, Number(workers.text), Number(targetTimeout.text));
    }
    Component.onCompleted: syncSettings()
    Connections { target: scanner; function onSettingsChanged() { root.syncSettings(); } function onColumnsChanged() { table.clearColumnWidths(); table.forceLayout(); } }

    Shortcut { sequence: "Ctrl+F"; onActivated: searchField.forceActiveFocus() }
    Shortcut { sequence: "Escape"; onActivated: { searchField.clear(); categoryBox.currentIndex = 0; scanner.category(categoryBox.currentText); qualityBox.currentIndex = 0; scanner.quality("Todos"); } }

    Rectangle {
        id: appbar
        height: 68
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        color: "white"
        Rectangle { height: 1; color: Theme.border; anchors.bottom: parent.bottom; width: parent.width }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24
            spacing: 12
            Image { source: "../assets/app.png"; sourceSize.width: 32; sourceSize.height: 32; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
            Text { text: "IP Scanner Helper"; font.pixelSize: 18; font.weight: Font.DemiBold; color: Theme.ink }
            Rectangle { width: 1; height: 18; color: Theme.border; Layout.leftMargin: 8; Layout.rightMargin: 8 }
            Text { text: root.state.demo ? "Demonstração" : "Inventário IPv4"; font.pixelSize: 12; color: Theme.muted }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "preferencesButton"; text: "Preferências"; onClicked: { preferencesDialog.requestedTab = 0; preferencesDialog.open(); } }
            AppButton { text: "Mapa da rede"; enabled: root.state.deviceCount > 0; onClicked: scanner.openMap() }
            AppButton { id: exportButton; text: "Exportar"; enabled: root.state.deviceCount > 0 && !root.state.scanning; onClicked: exportMenu.popup() }
        }
    }
    Menu {
        id: exportMenu
        MenuItem { text: "Inventário em CSV"; onTriggered: scanner.export("csv") }
        MenuItem { text: "Inventário em JSON"; onTriggered: scanner.export("json") }
        MenuItem { text: "Mapa HTML offline"; onTriggered: scanner.export("html") }
        MenuSeparator {}
        MenuItem { objectName: "exportDrawio"; text: "Diagrama Draw.io (.drawio / .xml)"; onTriggered: scanner.export("drawio") }
        MenuItem { objectName: "exportDot"; text: "Diagrama Graphviz (.dot)"; onTriggered: scanner.export("dot") }
    }

    ColumnLayout {
        anchors.top: appbar.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: footer.top
        anchors.margins: 22
        spacing: 16
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: config.implicitHeight + 28
            color: "white"; radius: 8; border.color: Theme.border
            ColumnLayout {
                id: config
                anchors.fill: parent; anchors.margins: 14
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true; spacing: 14
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.minimumWidth: 220; spacing: 7
                        Text { text: "Faixa de IPs"; color: Theme.muted; font.pixelSize: 12 }
                        AppField { id: targetField; objectName: "targetField"; Layout.fillWidth: true; text: root.state.target; placeholderText: "192.168.1.0/24"; enabled: !root.state.scanning; onTextEdited: scanner.setTarget(text); onAccepted: scanButton.clicked() }
                    }
                    ColumnLayout {
                        visible: root.width > 1120; Layout.fillWidth: true; Layout.preferredWidth: 320; spacing: 7
                        Text { text: "Interface de rede"; color: Theme.muted; font.pixelSize: 12 }
                        AppCombo { Layout.fillWidth: true; model: root.state.interfaceLabels; currentIndex: root.state.interfaceIndex; displayText: currentIndex >= 0 ? currentText : "Informar faixa manualmente"; enabled: !root.state.demo && !root.state.scanning; onActivated: scanner.selectInterface(currentIndex) }
                    }
                    ColumnLayout {
                        spacing: 7
                        Text { text: "Consulta"; color: Theme.muted; font.pixelSize: 12 }
                        AppCombo { id: modeBox; objectName: "modeBox"; Layout.preferredWidth: 128; model: ["Rápido", "Completo"]; currentIndex: 1; enabled: !root.state.scanning; onActivated: { scanner.setMode(currentText); root.rememberScanDefaults(); } }
                    }
                    AppButton { objectName: "optionsButton"; text: "Opções"; Layout.alignment: Qt.AlignBottom; hint: "Comunidade SNMP, consultas simultâneas e limite por IP"; onClicked: advanced.visible = !advanced.visible }
                    AppButton {
                        id: scanButton
                        objectName: "scanButton"
                        Layout.preferredWidth: 160; Layout.preferredHeight: 38; Layout.alignment: Qt.AlignBottom
                        text: root.state.stopping ? "Encerrando…" : root.state.scanning ? "Parar varredura" : "Iniciar varredura"
                        variant: root.state.scanning ? "danger" : "primary"
                        enabled: !root.state.demo && !root.state.stopping
                        onClicked: { if (enabled) { if (root.state.scanning) scanner.stopScan(); else scanner.startScan(community.text, Number(workers.text), Number(targetTimeout.text)); } }
                    }
                }
                RowLayout {
                    visible: advanced.visible && root.width <= 1120
                    Layout.fillWidth: true
                    Text { text: "Interface de rede"; color: Theme.muted; font.pixelSize: 12 }
                    AppCombo { Layout.fillWidth: true; model: root.state.interfaceLabels; currentIndex: root.state.interfaceIndex; displayText: currentIndex >= 0 ? currentText : "Informar faixa manualmente"; enabled: !root.state.demo && !root.state.scanning; onActivated: scanner.selectInterface(currentIndex) }
                }
                RowLayout {
                    id: advanced; objectName: "advancedOptions"; visible: false; spacing: 12; Layout.fillWidth: true
                    Text { text: "Comunidade SNMP"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { id: community; text: "public"; echoMode: TextInput.Password; Layout.preferredWidth: 160; enabled: !root.state.scanning && root.state.credentialId.length === 0 }
                    Text { text: "Consultas simultâneas"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { id: workers; objectName: "workersField"; text: "32"; Layout.preferredWidth: 64; validator: IntValidator { bottom: 1; top: 128 } enabled: !root.state.scanning; onEditingFinished: root.rememberScanDefaults() }
                    AppButton { text: "Atualizar interfaces"; variant: "quiet"; enabled: !root.state.demo && !root.state.scanning && !root.state.interfacesBusy; onClicked: scanner.refreshInterfaces() }
                    Item { Layout.fillWidth: true }
                }
                RowLayout {
                    visible: advanced.visible; Layout.fillWidth: true; spacing: 12
                    Text { text: "Credencial SNMP"; color: Theme.muted; font.pixelSize: 12 }
                    AppCombo { objectName: "credentialCombo"; Layout.fillWidth: true; model: root.state.credentialLabels; currentIndex: root.state.credentialIndex; enabled: !root.state.scanning && !root.state.demo; onActivated: scanner.selectCredential(root.state.credentialIds[currentIndex]) }
                    AppButton { text: "Gerenciar cofre"; onClicked: { preferencesDialog.requestedTab = 3; preferencesDialog.open(); } }
                }
                RowLayout {
                    visible: advanced.visible; Layout.fillWidth: true; spacing: 12
                    Text { text: "Limite por IP (s)"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { id: targetTimeout; objectName: "targetTimeoutField"; text: "20"; Layout.preferredWidth: 64; validator: DoubleValidator { bottom: 0.01; top: 300; decimals: 2; locale: "C" } enabled: !root.state.scanning; onEditingFinished: root.rememberScanDefaults() }
                    Text { text: "Ao atingir o limite, os dados encontrados são preservados."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
                Text { visible: advanced.visible; text: "Próxima coleta · " + root.state.portProfile + " · " + root.state.portCount + " portas TCP · " + (root.state.probeRateLimit > 0 ? root.state.probeRateLimit + " sondas/s" : "Sem limite de sondas/s") + ". Ajuste em Preferências."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                RowLayout {
                    visible: advanced.visible; Layout.fillWidth: true; spacing: 12
                    Text { text: "Ambiente (opcional)"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { objectName: "environmentField"; text: root.state.environmentName; Layout.preferredWidth: 220; maximumLength: 120; placeholderText: "Ex.: Escritório · matriz"; enabled: !root.state.scanning; onTextEdited: scanner.setEnvironmentName(text) }
                    Text { text: "Use um nome exclusivo para cada rede. Sem nome, a coleta fica isolada."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
                Text {
                    visible: advanced.visible && root.state.networkContext.target_count > 0
                    text: "Resultados desta coleta: " + (root.state.networkContext.environment_label || "ambiente não informado") + " · " + (root.state.networkContext.target_expression || "")
                    color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap; textFormat: Text.PlainText
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
            Rectangle {
                id: inventoryPanel
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "white"; radius: 8; border.color: Theme.border; clip: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 1; spacing: 0
                    RowLayout {
                        Layout.fillWidth: true; Layout.margins: 16; spacing: 12
                        Text { text: "Endereços IP"; color: Theme.ink; font.pixelSize: 21; font.weight: Font.DemiBold }
                        Text { visible: inventoryPanel.width > 760; text: root.state.visibleCount + " de " + root.state.deviceCount; color: Theme.muted; font.pixelSize: 12 }
                        Item { Layout.fillWidth: true }
                        AppField { id: searchField; objectName: "searchField"; Layout.preferredWidth: Math.max(180, Math.min(300, inventoryPanel.width * .28)); placeholderText: "Buscar IP, nome ou serviço"; onTextChanged: scanner.search(text) }
                        AppButton { text: "Colunas"; onClicked: columnsPopup.open() }
                        AppButton { objectName: "detailsButton"; text: root.state.detailsOpen ? "Fechar" : "Detalhes"; enabled: root.state.selectedIp.length > 0; onClicked: root.state.detailsOpen ? scanner.closeDetails() : scanner.openDetails() }
                    }
                    RowLayout {
                        Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.bottomMargin: 14; spacing: 10
                        AppCombo { id: categoryBox; objectName: "categoryCombo"; Layout.preferredWidth: 190; model: root.state.categories; onActivated: scanner.category(currentText) }
                        AppCombo { id: qualityBox; Layout.preferredWidth: root.state.detailsOpen ? 160 : 200; model: ["Todos", "Sem nome", "Sem MAC", "Categoria não identificada"]; onActivated: scanner.quality(currentText) }
                        AppButton { text: "Limpar"; variant: "quiet"; onClicked: { searchField.clear(); categoryBox.currentIndex = 0; scanner.category(categoryBox.currentText); qualityBox.currentIndex = 0; scanner.quality("Todos"); } }
                        Item { Layout.fillWidth: true }
                        Text { visible: !root.state.detailsOpen && inventoryPanel.width > 1000; text: root.state.metrics.sem_nome + " sem nome   ·   " + root.state.metrics.sem_mac + " sem MAC"; color: Theme.muted; font.pixelSize: 12 }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    HorizontalHeaderView {
                        id: header
                        objectName: "tableHeader"
                        Layout.fillWidth: true; implicitHeight: 43
                        syncView: table
                        clip: true
                        resizableColumns: false
                        delegate: Rectangle {
                            required property int column
                            required property var display
                            implicitWidth: scanner.columnWidth(column); implicitHeight: 43
                            color: "#f8f9fb"
                            Text { anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 14; verticalAlignment: Text.AlignVCenter; text: { let state = scanner.state; return scanner.columnTitle(column); } color: "#667381"; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight }
                            Rectangle { width: 1; height: 14; color: Theme.border; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter }
                            TapHandler { onTapped: scanner.sortColumn(column) }
                            MouseArea {
                                anchors.right: parent.right; width: 10; height: parent.height
                                cursorShape: Qt.SizeHorCursor
                                property real startX: 0
                                property real startWidth: 0
                                onPressed: function(mouse) { startX = mapToItem(root.contentItem, mouse.x, 0).x; startWidth = parent.width; }
                                onPositionChanged: function(mouse) {
                                    if (pressed) { let size = Math.max(60, Math.min(1200, startWidth + mapToItem(root.contentItem, mouse.x, 0).x - startX)); table.setColumnWidth(column, size); scanner.resizeColumn(column, size); }
                                }
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    TableView {
                        id: table
                        objectName: "inventoryTable"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        model: inventoryModel
                        rowSpacing: 0; columnSpacing: 0
                        reuseItems: true
                        activeFocusOnTab: true
                        boundsBehavior: Flickable.StopAtBounds
                        columnWidthProvider: function(column) {
                            let explicit = explicitColumnWidth(column);
                            if (explicit >= 0) return explicit;
                            let natural = scanner.columnWidth(column);
                            if (column === columns - 1) {
                                let used = 0;
                                for (let i = 0; i < column; i++) {
                                    let w = explicitColumnWidth(i);
                                    used += w >= 0 ? w : scanner.columnWidth(i);
                                }
                                return Math.max(natural, width - used);
                            }
                            return natural;
                        }
                        onWidthChanged: forceLayout()
                        rowHeightProvider: function(row) { return 46; }
                        resizableColumns: false
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
                        Keys.onReturnPressed: scanner.openDetails()
                        Keys.onEnterPressed: scanner.openDetails()
                        Keys.onDownPressed: { let row = scanner.moveSelection(1); if (row >= 0) positionViewAtRow(row, TableView.Contain); }
                        Keys.onUpPressed: { let row = scanner.moveSelection(-1); if (row >= 0) positionViewAtRow(row, TableView.Contain); }
                        delegate: Rectangle {
                            id: cell
                            required property int row
                            required property int column
                            required property string display
                            required property string rowIp
                            required property string columnKey
                            implicitWidth: scanner.columnWidth(column); implicitHeight: 46
                            color: root.state.selectedIp === rowIp ? Theme.selection : root.hoveredIp === rowIp ? "#f2f6f8" : row % 2 ? "#fbfcfd" : "white"
                            Rectangle { height: 1; width: parent.width; anchors.bottom: parent.bottom; color: "#f0f3f6" }
                            Rectangle { visible: column === 0 && root.state.selectedIp === rowIp; anchors.left: parent.left; height: parent.height; width: 3; color: Theme.accent }
                            Text { anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 14; text: cell.display; textFormat: Text.PlainText; color: cell.columnKey === "ip" ? "#243f51" : cell.columnKey === "origem" ? Theme.muted : Theme.ink; font.family: cell.columnKey === "ip" || cell.columnKey === "mac" ? "Consolas" : Theme.font; font.pixelSize: 13; font.weight: cell.columnKey === "ip" ? Font.Medium : Font.Normal; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                            HoverHandler { id: cellHover; onHoveredChanged: root.hoveredIp = hovered ? cell.rowIp : "" }
                            ToolTip.visible: cellHover.hovered && cell.display.length > 24
                            ToolTip.text: cell.display
                            ToolTip.delay: 800
                            TapHandler {
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onTapped: function(point, button) { scanner.selectRow(cell.row); table.forceActiveFocus(); if (button === Qt.RightButton) rowMenu.popup(); }
                                onDoubleTapped: { scanner.selectRow(cell.row); scanner.openDetails(); }
                            }
                        }
                        Text {
                            parent: table
                            objectName: "inventoryEmptyState"
                            anchors.centerIn: parent; visible: root.state.visibleCount === 0
                            text: root.state.deviceCount ? "Nenhum resultado para estes filtros." : root.state.scanning ? "Aguardando respostas da rede…" : "Informe uma faixa de IPs para iniciar."
                            font.pixelSize: 15; color: "#84909b"
                        }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    RowLayout {
                        Layout.fillWidth: true; Layout.margins: 14
                        Text { text: root.state.deviceCount + " dispositivos"; color: Theme.muted; font.pixelSize: 12 }
                        Item { Layout.fillWidth: true }
                        Text { text: "Duplo clique ou Enter para abrir os detalhes"; color: "#8c97a2"; font.pixelSize: 12 }
                    }
                }
            }

            Rectangle {
                objectName: "detailPanel"
                visible: root.state.detailsOpen
                Layout.preferredWidth: root.width > 1200 ? 350 : 310
                Layout.fillHeight: true
                radius: 8; color: "white"; border.color: Theme.border
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 18; spacing: 14
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Equipamento"; color: Theme.muted; font.pixelSize: 12 }
                        Item { Layout.fillWidth: true }
                        AppButton { text: "Fechar"; variant: "quiet"; implicitHeight: 28; onClicked: scanner.closeDetails() }
                    }
                    Text { text: root.state.selected.nome || ""; font.pixelSize: 21; font.weight: Font.DemiBold; color: Theme.ink; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
                    Text { text: root.state.selected.identitySource || ""; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { visible: root.state.selected.coleta_completa === false; text: root.state.selected.status || ""; color: Theme.accent; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 0
                        Repeater {
                            model: ["Identidade", "Serviços", "Evidências"]
                            delegate: AppButton {
                                required property int index
                                required property string modelData
                                text: modelData; variant: "quiet"; Layout.fillWidth: true; implicitWidth: 70
                                onClicked: root.detailTab = index
                                Rectangle { visible: root.detailTab === index; height: 2; width: parent.width; anchors.bottom: parent.bottom; color: Theme.accent }
                            }
                        }
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width; spacing: 12
                            Repeater {
                                model: root.detailTab === 0 ? [{k:"ip",l:"Endereço IP"},{k:"tipo",l:"Categoria"},{k:"confianca",l:"Confiança da categoria"},{k:"mac",l:"Endereço MAC"},{k:"fabricante",l:"Fabricante"},{k:"origem_mac",l:"Origem do MAC"}]
                                    : root.detailTab === 1 ? [{k:"portas",l:"Serviços TCP"},{k:"latencia",l:"Latência ICMP"},{k:"web_title",l:"Título da página"},{k:"ssl_cn",l:"Certificado"}]
                                    : [{k:"origem",l:"Origem do nome"},{k:"identityNote",l:"Sobre a identificação"},{k:"evidencia_categoria",l:"Evidência da categoria"},{k:"evidenciasTexto",l:"Respostas recebidas"},{k:"dns_ptr",l:"DNS reverso"},{k:"netbios_name",l:"NetBIOS"},{k:"snmp_descr",l:"Descrição SNMP"}]
                                delegate: InfoField { required property var modelData; Layout.fillWidth: true; label: modelData.l; value: String(root.state.selected[modelData.k] || "Não disponível"); mono: modelData.k === "ip" || modelData.k === "mac" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        AppButton { text: "Copiar IP"; Layout.fillWidth: true; onClicked: scanner.copy("ip") }
                        AppButton { text: "Abrir HTTPS"; Layout.fillWidth: true; enabled: !root.state.demo; onClicked: scanner.action("https") }
                    }
                    AppButton { text: "Mapear portas do switch"; Layout.fillWidth: true; enabled: !root.state.demo && root.state.selectedIp.length > 0 && !root.state.scanning; onClicked: { scanner.mapSwitch(community.text); switchDialog.open(); } }
                }
            }
        }
    }
    Rectangle {
        id: footer
        anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right
        height: 34; color: Theme.background
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24; spacing: 16
            Rectangle { width: 6; height: 6; radius: 3; color: root.state.scanning ? Theme.accent : "#a8b4bf" }
            Text { text: root.state.status; color: Theme.muted; font.pixelSize: 12 }
            ProgressBar { visible: root.state.total > 0; value: root.state.progress; Layout.preferredWidth: 140; Layout.preferredHeight: 3; background: Rectangle { color: "#e1e6e9"; radius: 2 } contentItem: Item { Rectangle { width: parent.width * root.state.progress; height: parent.height; radius: 2; color: Theme.accent } } }
            Text { visible: root.state.total > 0; text: root.state.completed + "/" + root.state.total; color: Theme.muted; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "incompleteButton"; visible: root.state.limitedCount > 0; text: root.state.limitedCount + " incompletas"; variant: "quiet"; implicitHeight: 26; onClicked: { messageTitle.text = "Coletas incompletas"; messageBody.text = root.state.limitedTargetsText; messageDialog.open(); } }
            Text { visible: !root.state.demo; text: root.state.elapsed; color: Theme.muted; font.pixelSize: 12; font.family: "Consolas" }
            AppButton { text: root.state.errorCount + " erros"; variant: "quiet"; implicitHeight: 26; enabled: root.state.errorCount > 0; onClicked: { messageTitle.text = "Erros da varredura"; messageBody.text = root.state.errorsText; messageDialog.open(); } }
        }
    }

    Popup {
        id: columnsPopup
        objectName: "columnsPopup"
        x: Math.max(20, root.width - width - 24); y: appbar.height + 132
        width: 270; padding: 12
        background: Rectangle { color: "white"; radius: 8; border.color: Theme.border }
        contentItem: Column {
            spacing: 2
            Repeater {
                model: root.state.columnOptions
                delegate: CheckBox { required property var modelData; width: parent.width; text: modelData.label; checked: modelData.checked; enabled: !modelData.mandatory; font.pixelSize: 13; onToggled: scanner.setColumn(modelData.key, checked) }
            }
        }
    }
    PreferencesDialog { id: preferencesDialog; anchors.centerIn: parent; width: Math.min(820, root.width - 60); height: Math.min(680, root.height - 60) }
    Menu {
        id: rowMenu
        MenuItem { text: "Detalhes"; onTriggered: scanner.openDetails() }
        MenuSeparator {}
        MenuItem { text: "Copiar IP"; onTriggered: scanner.copy("ip") }
        MenuItem { text: "Copiar MAC"; onTriggered: scanner.copy("mac") }
        MenuItem { text: "Copiar nome"; onTriggered: scanner.copy("nome") }
        MenuSeparator {}
        MenuItem { text: "Abrir HTTP"; enabled: !root.state.demo; onTriggered: scanner.action("http") }
        MenuItem { text: "Abrir HTTPS"; enabled: !root.state.demo; onTriggered: scanner.action("https") }
        MenuItem { text: "Ping contínuo"; enabled: !root.state.demo; onTriggered: scanner.action("ping") }
        MenuItem { text: "Conexão RDP"; enabled: !root.state.demo; onTriggered: scanner.action("rdp") }
        MenuItem { text: "Conexão SSH"; enabled: !root.state.demo; onTriggered: scanner.action("ssh") }
        MenuItem { text: "Mapear portas"; enabled: !root.state.demo && !root.state.scanning; onTriggered: { scanner.mapSwitch(community.text); switchDialog.open(); } }
    }

    Dialog {
        id: messageDialog
        objectName: "messageDialog"
        anchors.centerIn: parent
        width: Math.min(600, root.width - 80); height: Math.min(400, root.height - 80)
        modal: true; standardButtons: Dialog.Ok
        background: Rectangle { color: "white"; radius: 10; border.color: Theme.border }
        ColumnLayout {
            anchors.fill: parent; spacing: 16
            Text { id: messageTitle; font.pixelSize: 20; font.weight: Font.DemiBold; color: Theme.ink }
            ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth; TextArea { id: messageBody; readOnly: true; wrapMode: TextEdit.Wrap; color: Theme.muted; font.pixelSize: 14; background: null; textFormat: TextEdit.PlainText } }
        }
    }
    Connections { target: scanner; function onNotice(title, message) { messageTitle.text = title; messageBody.text = message; messageDialog.open(); } }
    Connections { target: inventoryModel; function onModelAboutToBeReset() { root.savedScroll = table.contentY; } function onModelReset() { Qt.callLater(function() { table.contentY = Math.min(root.savedScroll, Math.max(0, table.contentHeight - table.height)); }); } }

    Dialog {
        id: switchDialog
        objectName: "switchDialog"
        anchors.centerIn: parent
        width: Math.min(1100, root.width - 60); height: Math.min(680, root.height - 60)
        modal: true; padding: 20
        background: Rectangle { radius: 10; color: "white"; border.color: Theme.border }
        ColumnLayout {
            anchors.fill: parent; spacing: 12
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout { spacing: 4; Text { text: "Portas e endereços aprendidos"; font.pixelSize: 21; font.weight: Font.DemiBold; color: Theme.ink } Text { text: root.state.switchTitle + "  ·  " + root.state.switchIp; color: Theme.muted; font.pixelSize: 13 } }
                Item { Layout.fillWidth: true }
                AppButton { text: "Fechar"; onClicked: switchDialog.close() }
            }
            RowLayout {
                AppButton { text: "SNMP"; variant: root.switchMethod === "snmp" ? "primary" : "normal"; onClicked: root.switchMethod = "snmp" }
                AppButton { text: "Colar tabela MAC"; variant: root.switchMethod === "text" ? "primary" : "normal"; onClicked: root.switchMethod = "text" }
                AppButton { text: "Telnet"; variant: root.switchMethod === "telnet" ? "primary" : "normal"; onClicked: root.switchMethod = "telnet" }
                Item { Layout.fillWidth: true }
                AppButton { text: "Consultar SNMP"; enabled: !root.state.switchBusy; onClicked: scanner.mapSwitch(community.text) }
            }
            RowLayout {
                visible: root.switchMethod === "text"; Layout.fillWidth: true
                ScrollView { Layout.fillWidth: true; Layout.preferredHeight: 100; TextArea { id: macInput; placeholderText: "Cole a saída da tabela MAC do switch"; font.family: "Consolas"; font.pixelSize: 12; wrapMode: TextEdit.Wrap } }
                AppButton { text: "Importar"; enabled: !root.state.switchBusy; onClicked: scanner.importMacTable(macInput.text) }
            }
            RowLayout {
                visible: root.switchMethod === "telnet"; Layout.fillWidth: true
                AppField { id: telnetUser; text: "admin"; placeholderText: "Usuário"; Layout.preferredWidth: 140 }
                AppField { id: telnetPassword; echoMode: TextInput.Password; placeholderText: "Senha"; Layout.preferredWidth: 150 }
                AppField { id: telnetPort; text: "23"; Layout.preferredWidth: 60; validator: IntValidator { bottom: 1; top: 65535 } }
                AppButton { text: "Coletar"; enabled: !root.state.switchBusy; onClicked: { scanner.collectTelnet(telnetUser.text, telnetPassword.text, Number(telnetPort.text)); telnetPassword.clear(); } }
                Text { text: "Telnet transmite credenciais sem criptografia."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Text { text: root.state.switchStatus; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Rectangle {
                Layout.fillWidth: true; height: 36; color: "#f7f9fa"
                RowLayout { anchors.fill: parent; anchors.margins: 10; Text { text: "Interface"; Layout.preferredWidth: 130; font.pixelSize: 12 } Text { text: "Estado"; Layout.preferredWidth: 105; font.pixelSize: 12 } Text { text: "MAC"; Layout.preferredWidth: 165; font.pixelSize: 12 } Text { text: "Equipamento / IP"; Layout.fillWidth: true; font.pixelSize: 12 } }
            }
            ListView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: root.state.switchRows
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: ListView.view.width; height: 44; color: index % 2 ? "#fafbfd" : "white"
                    RowLayout { anchors.fill: parent; anchors.margins: 10; Text { text: modelData.port; Layout.preferredWidth: 130; elide: Text.ElideRight; font.pixelSize: 13 } Text { text: modelData.status; Layout.preferredWidth: 105; elide: Text.ElideRight; font.pixelSize: 12 } Text { text: modelData.mac; Layout.preferredWidth: 165; font.family: "Consolas"; font.pixelSize: 12 } Text { text: modelData.host + " · " + modelData.ip; Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: 13 } }
                }
            }
        }
    }
}

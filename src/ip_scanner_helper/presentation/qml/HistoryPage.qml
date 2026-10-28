import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: dialog
    signal opened()
    signal closed()
    property bool heatmap: false
    function open() { opened(); }
    function close() { closed(); }
    objectName: "historyDialog"
    property var history
    readonly property var snapshot: history ? history.state : ({enabled: false, busy: false, status: "Histórico indisponível.", sessions: [], selectedId: "", selectedTitle: "", sessionDetails: "", compareIds: [], compareLabels: [], diffRows: [], addressRows: [], view: "sessions", canLoad: false, canReserve: false, canRestore: false})
    onOpened: { if (history) history.refresh(); }

    function tagsText(value) {
        return Array.isArray(value) ? value.join(", ") : (value || "");
    }
    function kindLabel(value) {
        const names = {new: "Novo endereço", name: "Nome alterado", mac: "MAC alterado", services: "Serviços alterados", no_response: "Sem resposta", inconclusive: "Inconclusivo", unchanged: "Sem alteração"};
        return names[value] || value || "Alteração";
    }

    ColumnLayout {
        anchors.fill: parent;
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Text { textFormat: Text.PlainText; text: "IPAM e histórico"; font.pixelSize: 21; font.weight: Font.DemiBold; color: Theme.ink; Layout.fillWidth: true }
            AppButton { objectName: "historyBackup"; text: "Backup"; enabled: dialog.snapshot.enabled && !dialog.snapshot.busy; onClicked: dialog.history.backup() }
            AppButton { objectName: "historyRestore"; text: "Restaurar"; enabled: dialog.snapshot.canRestore && !dialog.snapshot.busy; onClicked: dialog.history.restore() }
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            text: "Consulte coletas anteriores e acompanhe alterações no mesmo ambiente."
            font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            AppButton { objectName: "historyRefresh"; text: "Atualizar"; enabled: dialog.snapshot.enabled && !dialog.snapshot.busy; onClicked: dialog.history.refresh() }
            AppButton { objectName: "historyLoad"; text: "Abrir inventário"; variant: "primary"; enabled: dialog.snapshot.canLoad && !dialog.snapshot.busy; onClicked: { dialog.history.loadSelected(); dialog.close(); } }
            AppButton { objectName: "historyAddresses"; text: "Endereços da faixa"; enabled: dialog.snapshot.selectedId.length > 0 && !dialog.snapshot.busy; onClicked: dialog.history.showAddresses() }
            Item { Layout.fillWidth: true }
            BusyIndicator { running: dialog.snapshot.busy; visible: running; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18
            ColumnLayout {
                Layout.preferredWidth: dialog.width < 1000 ? 220 : 260
                Layout.fillHeight: true; spacing: 8
                Text { textFormat: Text.PlainText; text: "COLETAS"; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1; color: Theme.muted }
                ListView {
                    id: sessions
                    objectName: "historySessions"
                    Layout.fillWidth: true; Layout.fillHeight: true
                    model: dialog.snapshot.sessions
                    clip: true; spacing: 5
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ItemDelegate {
                        required property var modelData
                        objectName: "historySession:" + modelData.id
                        width: sessions.width
                        height: 88
                        padding: 10
                        enabled: !dialog.snapshot.busy
                        background: Rectangle { color: modelData.id === dialog.snapshot.selectedId ? Theme.selection : parent.hovered ? Theme.hover : Theme.surface; radius: 6 }
                        contentItem: ColumnLayout {
                            spacing: 4
                            Text { text: modelData.title || "Coleta"; textFormat: Text.PlainText; color: Theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: modelData.subtitle || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: modelData.status || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                        onClicked: dialog.history.selectSession(modelData.id)
                    }
                    Text {
                        visible: sessions.count === 0
                        width: parent.width; y: 20
                        text: dialog.snapshot.busy ? "Carregando coletas…" : "As varreduras serão salvas aqui."
                        textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
                    }
                }
            }
            Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.border }
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
                Text { text: dialog.snapshot.selectedTitle || "Selecione uma coleta"; textFormat: Text.PlainText; color: Theme.ink; font.pixelSize: 15; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    AppCombo {
                        id: comparisonBox
                        objectName: "historyBaseline"
                        Layout.fillWidth: true
                        model: dialog.snapshot.compareLabels
                        displayText: count > 0 ? currentText : "Sem coleta compatível para comparar"
                        enabled: count > 0 && !dialog.snapshot.busy
                        contentItem: Text {
                            text: comparisonBox.displayText; textFormat: Text.PlainText
                            font: comparisonBox.font; color: comparisonBox.enabled ? Theme.ink : Theme.muted
                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                        }
                        delegate: ItemDelegate {
                            required property var modelData
                            required property int index
                            width: comparisonBox.width - 8
                            highlighted: comparisonBox.highlightedIndex === index
                            background: Rectangle { color: parent.highlighted ? Theme.selection : Theme.surface; radius: 4 }
                            contentItem: Text { text: modelData; textFormat: Text.PlainText; color: Theme.ink; font: comparisonBox.font; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                        }
                    }
                    AppButton {
                        objectName: "historyCompare"; text: "Comparar"
                        enabled: dialog.snapshot.selectedId.length > 0 && comparisonBox.currentIndex >= 0 && comparisonBox.currentIndex < dialog.snapshot.compareIds.length && !dialog.snapshot.busy
                        onClicked: dialog.history.compareSelected(dialog.snapshot.compareIds[comparisonBox.currentIndex])
                    }
                }
                StackLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    currentIndex: dialog.snapshot.view === "diff" ? 1 : dialog.snapshot.view === "addresses" ? 2 : 0
                    ScrollView {
                        id: summary
                        contentWidth: availableWidth; clip: true
                        Text {
                            width: summary.availableWidth
                            text: dialog.snapshot.sessionDetails || "Escolha uma coleta à esquerda para consultar a cobertura e recuperar o inventário."
                            textFormat: Text.PlainText; wrapMode: Text.Wrap
                            color: Theme.ink; font.pixelSize: 13; lineHeight: 1.35
                            padding: 4
                        }
                    }
                    ColumnLayout {
                        spacing: 8
                        Text { text: "A comparação mostra evidências das duas coletas. Ausência de resposta não confirma queda."; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        ListView {
                            id: differences
                            objectName: "historyRows"
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; spacing: 8
                            model: dialog.snapshot.diffRows
                            ScrollBar.vertical: ScrollBar {}
                            delegate: Rectangle {
                                required property var modelData
                                width: differences.width
                                implicitHeight: differenceText.implicitHeight + 20
                                color: Theme.subtle; radius: 6
                                ColumnLayout {
                                    id: differenceText
                                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10
                                    spacing: 5
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.ip || ""; textFormat: Text.PlainText; font.family: "Consolas"; font.pixelSize: 13; font.weight: Font.DemiBold; color: Theme.ink }
                                        Item { Layout.fillWidth: true }
                                        Text { text: dialog.kindLabel(modelData.kind); textFormat: Text.PlainText; font.pixelSize: 11; color: Theme.accent }
                                    }
                                    Text { text: modelData.detail || ""; textFormat: Text.PlainText; font.pixelSize: 12; color: Theme.ink; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Text { visible: text.length > 0; text: modelData.before ? "Antes · " + modelData.before : ""; textFormat: Text.PlainText; font.pixelSize: 11; color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                    Text { visible: text.length > 0; text: modelData.after ? "Depois · " + modelData.after : ""; textFormat: Text.PlainText; font.pixelSize: 11; color: Theme.muted; Layout.fillWidth: true; wrapMode: Text.Wrap }
                                }
                            }
                            Text { visible: differences.count === 0; width: parent.width; y: 16; text: "Nenhuma alteração nos campos comparados."; textFormat: Text.PlainText; font.pixelSize: 12; color: Theme.muted; wrapMode: Text.Wrap }
                        }
                    }
                    ColumnLayout {
                        spacing: 9
                        Text { text: "Estados desta coleta. Um endereço sem observação não está confirmado como livre."; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        RowLayout {
                            Layout.fillWidth: true
                            AppButton { objectName: "historyListMode"; text: "Lista"; variant: !dialog.heatmap ? "primary" : "quiet"; onClicked: dialog.heatmap = false }
                            AppButton { objectName: "historyHeatmapMode"; text: "Mapa de endereços"; variant: dialog.heatmap ? "primary" : "quiet"; onClicked: dialog.heatmap = true }
                            Item { Layout.fillWidth: true }
                        }
                        GridView {
                            id: heatmapGrid; objectName: "historyHeatmap"
                            visible: dialog.heatmap
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; cellWidth: 100; cellHeight: 64
                            model: dialog.heatmap ? dialog.snapshot.addressRows : []
                            ScrollBar.vertical: ScrollBar {}
                            delegate: ItemDelegate {
                                required property var modelData
                                objectName: "historyAddressTile:" + modelData.ip
                                width: heatmapGrid.cellWidth - 6; height: heatmapGrid.cellHeight - 6; padding: 8
                                background: Rectangle {
                                    color: parent.hovered ? Theme.hover : Theme.subtle; radius: 5; border.color: Theme.border
                                    Rectangle { width: 4; height: parent.height - 14; x: 0; y: 7; radius: 2; color: modelData.stateCode === "observed" ? Theme.accent : modelData.stateCode === "reserved" ? Theme.warning : modelData.stateCode === "partial" ? "#6096b0" : Theme.disabledInk }
                                }
                                contentItem: Column {
                                    spacing: 4
                                    Text { text: (modelData.ip || "").split(".").slice(2).join("."); textFormat: Text.PlainText; color: Theme.ink; font.family: "Consolas"; font.pixelSize: 13 }
                                    Text { text: modelData.state || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 9; width: parent.width; elide: Text.ElideRight }
                                }
                                ToolTip.visible: hovered
                                ToolTip.text: modelData.ip + " · " + modelData.state
                                Accessible.name: modelData.ip + " " + modelData.state
                                onClicked: { reservationIp.text = modelData.ip || ""; reservationLabel.text = modelData.label || ""; reservationTags.text = dialog.tagsText(modelData.tags); }
                            }
                        }
                        ListView {
                            id: addresses
                            objectName: "historyAddressRows"
                            visible: !dialog.heatmap
                            Layout.fillWidth: true; Layout.fillHeight: true
                            clip: true; spacing: 4
                            model: dialog.snapshot.addressRows
                            ScrollBar.vertical: ScrollBar {}
                            delegate: ItemDelegate {
                                required property var modelData
                                width: addresses.width; height: 61; padding: 8
                                background: Rectangle { color: parent.hovered ? Theme.selection : Theme.subtle; radius: 5 }
                                contentItem: ColumnLayout {
                                    spacing: 3
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: modelData.ip || ""; textFormat: Text.PlainText; font.family: "Consolas"; color: Theme.ink; font.pixelSize: 13 }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.state || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11 }
                                    }
                                    Text { text: [modelData.label || "", dialog.tagsText(modelData.tags)].filter(function(part) { return part.length > 0; }).join(" · "); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                                }
                                onClicked: { reservationIp.text = modelData.ip || ""; reservationLabel.text = modelData.label || ""; reservationTags.text = dialog.tagsText(modelData.tags); }
                            }
                        }
                        ColumnLayout {
                            visible: dialog.snapshot.canReserve
                            Layout.fillWidth: true; spacing: 6
                            Text { textFormat: Text.PlainText; text: "Reserva manual · não altera DHCP ou equipamentos"; color: Theme.muted; font.pixelSize: 11 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                AppField { id: reservationIp; objectName: "historyReservationIp"; Layout.preferredWidth: 134; maximumLength: 15; placeholderText: "Endereço IPv4" }
                                AppField { id: reservationLabel; objectName: "historyReservationLabel"; Layout.fillWidth: true; maximumLength: 120; placeholderText: "Descrição" }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                AppField { id: reservationTags; objectName: "historyReservationTags"; Layout.fillWidth: true; maximumLength: 256; placeholderText: "Tags, separadas por vírgula" }
                                AppButton { objectName: "historyReservationSave"; text: "Reservar"; enabled: reservationIp.text.length > 0 && !dialog.snapshot.busy; onClicked: dialog.history.saveReservation(reservationIp.text, reservationLabel.text, reservationTags.text) }
                                AppButton { objectName: "historyReservationDelete"; text: "Remover"; enabled: reservationIp.text.length > 0 && !dialog.snapshot.busy; onClicked: dialog.history.deleteReservation(reservationIp.text) }
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            Text { objectName: "historyStatus"; text: dialog.snapshot.status || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
            AppButton { objectName: "historyClose"; text: "Fechar"; onClicked: dialog.close() }
        }
    }
}

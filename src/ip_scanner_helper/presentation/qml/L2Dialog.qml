import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "l2Dialog"
    required property var state
    signal collectRequested()
    signal cancelRequested()
    property string page: "neighbors"
    anchors.centerIn: parent
    width: Math.min(1100, parent.width - 48)
    height: Math.min(720, parent.height - 48)
    modal: true
    padding: 20
    onClosed: { if (state.l2Busy) cancelRequested(); }
    background: Rectangle { color: Theme.surface; radius: 10; border.color: Theme.border }
    ColumnLayout {
        anchors.fill: parent
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 4
                Text { textFormat: Text.PlainText; text: "Vizinhança e VLANs"; font.pixelSize: 21; font.weight: Font.DemiBold; color: Theme.ink }
                Text { textFormat: Text.PlainText; text: dialog.state.switchTitle + " · " + dialog.state.switchIp; font.pixelSize: 13; color: Theme.muted }
            }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "refreshL2"; text: "Consultar"; enabled: !dialog.state.l2Busy; onClicked: dialog.collectRequested() }
            AppButton { objectName: "cancelL2"; text: "Interromper"; visible: dialog.state.l2Busy; onClicked: dialog.cancelRequested() }
            AppButton { text: "Fechar"; onClicked: dialog.close() }
        }
        RowLayout {
            AppButton { text: "Vizinhos"; variant: dialog.page === "neighbors" ? "primary" : "normal"; onClicked: dialog.page = "neighbors" }
            AppButton { text: "VLANs por porta"; variant: dialog.page === "vlans" ? "primary" : "normal"; onClicked: dialog.page = "vlans" }
            AppButton { text: "Cobertura da consulta"; variant: dialog.page === "coverage" ? "primary" : "normal"; onClicked: dialog.page = "coverage" }
            Item { Layout.fillWidth: true }
        }
        Text { textFormat: Text.PlainText; text: dialog.state.l2Status; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
        Rectangle {
            Layout.fillWidth: true
            height: 34
            color: Theme.subtle
            Text { textFormat: Text.PlainText; anchors.fill: parent; anchors.margins: 10; font.pixelSize: 12; color: Theme.muted
                text: dialog.page === "neighbors" ? "Protocolo · Porta local → Equipamento / Porta remota"
                    : dialog.page === "vlans" ? "Porta / índice da bridge · PVID · Saída tagged / untagged"
                    : "MIB consultada · Entradas, requisições e limites" }
        }
        ListView {
            objectName: "l2Results"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: dialog.page === "neighbors" ? dialog.state.l2Neighbors : dialog.page === "vlans" ? dialog.state.l2Vlans : dialog.state.l2Coverage
            ScrollBar.vertical: ScrollBar {}
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: ListView.view.width
                height: row.implicitHeight + 22
                color: index % 2 ? Theme.subtle : Theme.surface
                ColumnLayout {
                    id: row
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    spacing: 5
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 13; color: Theme.ink
                        text: dialog.page === "neighbors" ? modelData.protocol + " · " + modelData.localPort + " → " + modelData.remoteName + " · " + modelData.remotePort
                            : dialog.page === "vlans" ? modelData.port + " · Bridge " + modelData.bridgePort + " · ifIndex " + modelData.ifIndex + " · PVID " + modelData.pvid
                            : modelData.table
                    }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true; wrapMode: Text.Wrap; font.pixelSize: 12; color: Theme.muted
                        text: dialog.page === "neighbors" ? modelData.address + " · " + modelData.status
                            : dialog.page === "vlans" ? "Tagged: " + modelData.tagged + "     Untagged: " + modelData.untagged
                            : modelData.text
                    }
                }
            }
            Text { textFormat: Text.PlainText; anchors.centerIn: parent; visible: parent.count === 0; text: dialog.state.l2Busy ? "Consulta em andamento…" : "Nenhuma entrada disponível nesta consulta."; color: Theme.muted; font.pixelSize: 13 }
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 11
            text: "Relatos LLDP/CDP são direcionais e não certificam cabeamento. Janela de correlação: 5 minutos; TTL não disponível. Índices LLDP, bridge e ifIndex são distintos. VLANs mostram evidências de configuração, sem presumir modo acesso/trunk."
        }
    }
}

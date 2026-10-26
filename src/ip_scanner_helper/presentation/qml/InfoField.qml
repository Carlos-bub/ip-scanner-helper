import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property string label: ""
    property string value: ""
    property bool mono: false
    spacing: 6
    Text { text: label; color: Theme.muted; font.family: Theme.font; font.pixelSize: 12; Layout.fillWidth: true }
    Text { text: value || "Não disponível"; color: Theme.ink; font.family: mono ? "Consolas" : Theme.font; font.pixelSize: 14; wrapMode: Text.Wrap; Layout.fillWidth: true; textFormat: Text.PlainText }
    Item { implicitHeight: 8 }
}

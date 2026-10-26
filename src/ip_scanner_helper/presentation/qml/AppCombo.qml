import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.ComboBox {
    id: control
    implicitHeight: 38
    font.family: Theme.font
    font.pixelSize: 13
    leftPadding: 12
    rightPadding: 28
    background: Rectangle {
        radius: 6
        color: control.enabled ? "white" : "#f5f6f8"
        border.color: control.activeFocus ? Theme.accent : Theme.border
        border.width: control.activeFocus ? 2 : 1
    }
    contentItem: Text {
        text: control.displayText
        font: control.font
        color: control.enabled ? Theme.ink : Theme.muted
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Canvas {
        x: control.width - width - 12
        y: (control.height - height) / 2
        width: 10; height: 6
        onPaint: { let c = getContext("2d"); c.strokeStyle = "#7b8792"; c.lineWidth = 1.5; c.beginPath(); c.moveTo(1, 1); c.lineTo(5, 5); c.lineTo(9, 1); c.stroke(); }
    }
    popup.padding: 4
    popup.background: Rectangle { color: "white"; radius: 7; border.color: Theme.border }
    delegate: Basic.ItemDelegate {
        width: control.width - 8
        text: modelData
        font: control.font
        highlighted: control.highlightedIndex === index
        background: Rectangle { color: parent.highlighted ? "#edf3f0" : "white"; radius: 4 }
        contentItem: Text { text: parent.text; color: Theme.ink; font: control.font; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
    }
}

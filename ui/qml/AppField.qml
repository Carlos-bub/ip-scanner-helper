import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.TextField {
    id: control
    implicitHeight: 38
    leftPadding: 12
    rightPadding: 12
    font.family: Theme.font
    font.pixelSize: 14
    color: Theme.ink
    placeholderTextColor: "#95a0aa"
    selectionColor: "#d9e9e1"
    selectedTextColor: Theme.ink
    selectByMouse: true
    background: Rectangle {
        radius: 6
        color: control.enabled ? "#ffffff" : "#f5f6f8"
        border.color: control.activeFocus ? Theme.accent : Theme.border
        border.width: control.activeFocus ? 2 : 1
    }
}

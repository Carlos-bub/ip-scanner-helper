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
    placeholderTextColor: Theme.disabledInk
    selectionColor: Theme.selection
    selectedTextColor: Theme.ink
    selectByMouse: true
    background: Rectangle {
        radius: 6
        color: control.enabled ? Theme.surface : Theme.disabled
        border.color: control.activeFocus ? Theme.accent : Theme.border
        border.width: control.activeFocus ? 2 : 1
    }
}

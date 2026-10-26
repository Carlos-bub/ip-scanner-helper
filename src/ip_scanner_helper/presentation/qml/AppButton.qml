import QtQuick
import QtQuick.Controls.Basic as Basic

Basic.Button {
    id: control
    property string variant: "normal"
    property string hint: ""
    implicitHeight: 36
    implicitWidth: Math.max(72, label.implicitWidth + 28)
    hoverEnabled: true
    font.family: Theme.font
    font.pixelSize: 13
    font.weight: Font.Medium
    background: Rectangle {
        radius: 6
        color: !control.enabled ? "#f0f2f4" : control.variant === "primary" ? (control.down ? "#204b3e" : control.hovered ? "#285e4d" : Theme.accent)
                    : control.variant === "danger" ? "#ab3535" : control.down ? "#edf0f3" : control.hovered ? "#f7f9fa" : "#ffffff"
        border.width: control.activeFocus ? 2 : control.variant === "quiet" || control.variant === "primary" ? 0 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.border
    }
    contentItem: Text {
        id: label
        text: control.text
        font: control.font
        color: !control.enabled ? "#a0a9b2" : control.variant === "primary" || control.variant === "danger" ? "white" : Theme.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    Basic.ToolTip.visible: hovered && hint.length > 0
    Basic.ToolTip.text: hint
    Basic.ToolTip.delay: 600
}

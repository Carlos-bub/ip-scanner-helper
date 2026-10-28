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
        color: !control.enabled ? Theme.disabled : control.variant === "primary" ? (control.down ? Theme.accentDown : control.hovered ? Theme.accentHover : Theme.accent)
                    : control.variant === "danger" ? Theme.dangerFill : control.down ? Theme.hover : control.hovered ? Theme.subtle : Theme.surface
        border.width: control.activeFocus ? 2 : control.variant === "quiet" || control.variant === "primary" ? 0 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.border
    }
    contentItem: Text { textFormat: Text.PlainText;
        id: label
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.disabledInk : control.variant === "danger" ? "white" : control.variant === "primary" ? Theme.accentInk : Theme.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    Basic.ToolTip.visible: hovered && hint.length > 0
    Basic.ToolTip.text: hint
    Basic.ToolTip.delay: 600
}

pragma Singleton
import QtQuick
QtObject {
    property string mode: "light"
    readonly property bool dark: mode === "dark" || (mode === "system" && Application.styleHints.colorScheme === Qt.Dark)
    readonly property color background: dark ? "#12151a" : "#f4f6f8"
    readonly property color surface: dark ? "#1b2027" : "#ffffff"
    readonly property color subtle: dark ? "#222932" : "#f7f9fa"
    readonly property color hover: dark ? "#2a333d" : "#f0f3f6"
    readonly property color ink: dark ? "#e3e9ee" : "#19252d"
    readonly property color muted: dark ? "#a4b0bd" : "#657582"
    readonly property color border: dark ? "#343e49" : "#e3e8ed"
    readonly property color accent: dark ? "#79c7ad" : "#306958"
    readonly property color accentHover: dark ? "#91d5bf" : "#285e4d"
    readonly property color accentDown: dark ? "#5eaa92" : "#204b3e"
    readonly property color accentInk: dark ? "#10261e" : "#ffffff"
    readonly property color selection: dark ? "#263e37" : "#eaf2ef"
    readonly property color danger: dark ? "#f09893" : "#b33a36"
    readonly property color dangerFill: dark ? "#963c3c" : "#ab3535"
    readonly property color disabled: dark ? "#252c34" : "#f0f2f4"
    readonly property color disabledInk: dark ? "#77838e" : "#8c97a2"
    readonly property color warning: dark ? "#dfbf78" : "#8b6b2e"
    readonly property string font: "Segoe UI"
}

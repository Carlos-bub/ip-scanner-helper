import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "preferencesDialog"
    modal: true
    padding: 24
    closePolicy: Popup.CloseOnEscape
    property bool showError: false
    onOpened: {
        let draft = scanner.preferencesDraft();
        mode.currentIndex = draft.mode === "Rápido" ? 0 : 1;
        workers.text = String(draft.workers);
        timeout.text = String(draft.target_timeout);
        showError = false;
    }
    background: Rectangle { color: "white"; radius: 10; border.color: Theme.border }
    contentItem: ColumnLayout {
        spacing: 18
        Text { text: "Preferências"; font.pixelSize: 22; font.weight: Font.DemiBold; color: Theme.ink }
        Text { text: "Defina os valores para a próxima varredura. A coleta em andamento mantém suas configurações."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 13 }
        ColumnLayout {
            spacing: 7; Layout.fillWidth: true
            Text { text: "Modo de consulta"; color: Theme.muted; font.pixelSize: 12 }
            AppCombo { id: mode; objectName: "preferenceMode"; Layout.fillWidth: true; model: ["Rápido", "Completo"] }
        }
        RowLayout {
            spacing: 20; Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true; spacing: 7
                Text { text: "Consultas simultâneas · 1 a 128"; color: Theme.muted; font.pixelSize: 12 }
                AppField { id: workers; objectName: "preferenceWorkers"; Layout.fillWidth: true; validator: IntValidator { bottom: 1; top: 128 } }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 7
                Text { text: "Limite por IP · até 300 s"; color: Theme.muted; font.pixelSize: 12 }
                AppField { id: timeout; objectName: "preferenceTimeout"; Layout.fillWidth: true; validator: DoubleValidator { bottom: 0.01; top: 300; decimals: 2; locale: "C" } }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        Text { text: "Janela, colunas, ordenação e última faixa são lembradas automaticamente. Credenciais e resultados não são salvos nas preferências."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
        Text { visible: dialog.showError; text: scanner.state.preferencesError; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#b33a36"; font.pixelSize: 12; textFormat: Text.PlainText }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Item { Layout.fillWidth: true }
            AppButton { objectName: "preferencesCancel"; text: "Cancelar"; onClicked: dialog.close() }
            AppButton {
                objectName: "preferencesSave"; text: "Salvar preferências"; variant: "primary"
                onClicked: {
                    if (scanner.applyPreferences({mode: mode.currentText, workers: Number(workers.text), target_timeout: Number(timeout.text)})) dialog.close();
                    else dialog.showError = true;
                }
            }
        }
    }
}

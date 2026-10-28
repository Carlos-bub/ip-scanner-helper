import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: pane
    contentWidth: availableWidth
    clip: true
    property string credentialId: ""
    property bool confirmingDelete: false
    property var entries: scanner.state.credentials
    function clearSecret() { secret.clear(); confirmingDelete = false; }
    function newCredential() {
        credentialId = ""; list.currentIndex = -1;
        nameField.clear(); environment.clear(); clearSecret();
    }
    function selectEntry(index) {
        if (index < 0 || index >= entries.length) return;
        credentialId = entries[index].id;
        nameField.text = entries[index].name;
        environment.text = entries[index].environment;
        clearSecret();
    }
    Component.onCompleted: newCredential()
    ColumnLayout {
        width: pane.availableWidth; spacing: 12
        Text { textFormat: Text.PlainText;
            text: scanner.state.vaultEnabled ? "O cofre é salvo pelos botões desta aba, independentemente das outras preferências. O segredo nunca é exibido ao editar." : "O cofre pessoal fica indisponível na demonstração e na autoverificação."
            Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            AppCombo {
                id: list; objectName: "vaultCredentialList"; Layout.fillWidth: true
                model: pane.entries.map(function(entry) { return entry.name + (entry.environment ? " · " + entry.environment : ""); })
                displayText: currentIndex >= 0 ? currentText : "Selecione para editar ou crie uma credencial"
                enabled: scanner.state.vaultReady
                onActivated: pane.selectEntry(currentIndex)
            }
            AppButton { objectName: "vaultNew"; text: "Nova"; enabled: scanner.state.vaultReady && pane.entries.length < 32; onClicked: pane.newCredential() }
            AppButton { objectName: "vaultRefresh"; text: "Atualizar"; enabled: scanner.state.vaultEnabled; onClicked: { scanner.refreshCredentials(); pane.newCredential(); } }
        }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 6
            Text { textFormat: Text.PlainText; text: "Nome da credencial"; color: Theme.muted; font.pixelSize: 12 }
            AppField { id: nameField; objectName: "vaultName"; Layout.fillWidth: true; maximumLength: 64; placeholderText: "Ex.: Monitoramento da matriz"; enabled: scanner.state.vaultReady }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 18
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Text { textFormat: Text.PlainText; text: "Comunidade SNMP"; color: Theme.muted; font.pixelSize: 12 }
                AppField { id: secret; objectName: "vaultCommunity"; Layout.fillWidth: true; echoMode: TextInput.Password; maximumLength: 255; enabled: scanner.state.vaultReady; placeholderText: pane.credentialId ? "Vazio mantém a comunidade existente" : "Informe a comunidade" }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Text { textFormat: Text.PlainText; text: "Ambiente vinculado (opcional)"; color: Theme.muted; font.pixelSize: 12 }
                AppField { id: environment; objectName: "vaultEnvironment"; Layout.fillWidth: true; maximumLength: 120; placeholderText: "Ex.: Matriz"; enabled: scanner.state.vaultReady }
            }
        }
        Text { textFormat: Text.PlainText; text: "Ao usar uma credencial vinculada, o ambiente é preenchido para a próxima coleta. Depois de reabrir o aplicativo, confirme o ambiente ou selecione a credencial novamente."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            AppButton {
                objectName: "vaultSave"; text: "Salvar credencial"; variant: "primary"; enabled: scanner.state.vaultReady
                onClicked: {
                    let identifier = scanner.saveCredential(pane.credentialId, nameField.text, secret.text, environment.text);
                    if (identifier) {
                        let index = pane.entries.findIndex(function(entry) { return entry.id === identifier; });
                        list.currentIndex = index; pane.selectEntry(index);
                    }
                }
            }
            AppButton { objectName: "vaultUse"; text: "Usar na próxima coleta"; enabled: pane.credentialId.length > 0 && scanner.state.vaultReady; onClicked: scanner.selectCredential(pane.credentialId) }
            AppButton { objectName: "vaultDelete"; text: "Excluir"; enabled: pane.credentialId.length > 0 && scanner.state.vaultReady; onClicked: pane.confirmingDelete = true }
        }
        RowLayout {
            visible: pane.confirmingDelete; Layout.fillWidth: true; spacing: 8
            Text { textFormat: Text.PlainText; text: "Excluir esta credencial do cofre?"; color: Theme.ink; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
            AppButton { objectName: "vaultDeleteCancel"; text: "Cancelar"; onClicked: pane.confirmingDelete = false }
            AppButton { objectName: "vaultDeleteConfirm"; text: "Confirmar exclusão"; variant: "danger"; onClicked: { if (scanner.deleteCredential(pane.credentialId)) pane.newCredential(); } }
        }
        Text { visible: scanner.state.vaultError.length > 0; text: scanner.state.vaultError; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.danger; font.pixelSize: 12 }
        Text { visible: scanner.state.vaultError.length === 0; text: scanner.state.vaultStatus; textFormat: Text.PlainText; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.accent; font.pixelSize: 12 }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
        Text { textFormat: Text.PlainText; text: "Proteção vinculada ao usuário do Windows. Uma cópia do cofre pode não abrir em outra conta ou máquina. SNMP v1/v2c continua transmitindo a comunidade sem criptografia na rede."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
    }
}

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
    property int currentTab: 0
    property int requestedTab: 0
    property var profiles: []
    property var times: []
    property int editingIndex: -1
    property bool builtin: true
    property var timeLabels: ({icmp: "ICMP", tcp: "TCP · conexão", tcp_batch: "TCP · lote por IP", snmp: "SNMP", dns_ptr: "DNS reverso", netbios: "NetBIOS", pjl: "Impressão PJL", onvif: "ONVIF", http: "HTTP", sip: "SIP", rdp: "RDP", ssh: "SSH", ftp: "FTP", tls: "TLS", ssdp: "SSDP"})
    function setTime(key, value) {
        showError = false;
        for (let i = 0; i < times.length; ++i) {
            if (times[i].key === key) { times[i].value = value; return; }
        }
    }
    function storeEditor() {
        if (editingIndex >= 0 && editingIndex < profiles.length && !profiles[editingIndex].builtin) {
            profiles[editingIndex].name = profileName.text;
            profiles[editingIndex].ports_text = portsEditor.text;
        }
    }
    function loadProfile(index) {
        editingIndex = index;
        if (index < 0 || index >= profiles.length) return;
        builtin = profiles[index].builtin;
        profileName.text = profiles[index].name;
        portsEditor.text = profiles[index].ports_text;
    }
    function newProfile(duplicate) {
        storeEditor();
        let source = profiles[Math.max(0, editingIndex)];
        let entry = {id: "custom-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10),
                     name: duplicate ? source.name + " cópia" : "Meu perfil", builtin: false,
                     ports_text: duplicate ? source.ports_text : "8088 Minha aplicação"};
        profiles = profiles.concat([entry]);
        profileCombo.currentIndex = profiles.length - 1;
        loadProfile(profileCombo.currentIndex);
    }
    onOpened: {
        let draft = scanner.preferencesDraft();
        mode.currentIndex = draft.mode === "Rápido" ? 0 : 1;
        workers.text = String(draft.workers);
        timeout.text = String(draft.target_timeout);
        probeRate.text = String(draft.probe_rate_limit);
        profiles = JSON.parse(JSON.stringify(draft.profile_catalog));
        times = JSON.parse(JSON.stringify(draft.timeout_catalog));
        let selected = profiles.findIndex(function(profile) { return profile.id === draft.port_profile_id; });
        profileCombo.currentIndex = Math.max(0, selected);
        loadProfile(profileCombo.currentIndex);
        currentTab = requestedTab;
        showError = false;
    }
    onClosed: vaultPane.clearSecret()
    background: Rectangle { color: "white"; radius: 10; border.color: Theme.border }
    contentItem: ColumnLayout {
        spacing: 16
        Text { text: "Preferências"; font.pixelSize: 22; font.weight: Font.DemiBold; color: Theme.ink }
        Text { text: "As alterações valem para a próxima varredura. A coleta em andamento mantém suas configurações."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 13 }
        RowLayout {
            Layout.fillWidth: true; spacing: 6
            Repeater {
                model: ["Coleta", "Perfis TCP", "Tempos", "Cofre SNMP"]
                delegate: AppButton {
                    required property int index
                    required property string modelData
                    objectName: "preferencesTab" + index
                    text: modelData; variant: "quiet"; Layout.fillWidth: true
                    onClicked: dialog.currentTab = index
                    Rectangle { visible: dialog.currentTab === index; anchors.bottom: parent.bottom; width: parent.width; height: 2; color: Theme.accent }
                }
            }
        }
        StackLayout {
            currentIndex: dialog.currentTab
            Layout.fillWidth: true; Layout.fillHeight: true
            ScrollView {
                id: generalScroll
                contentWidth: availableWidth; clip: true
                ColumnLayout {
                    width: generalScroll.availableWidth; spacing: 18
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
                    Text { text: "O perfil TCP define quais portas serão consultadas. O modo Completo acrescenta identificação especializada nos serviços conhecidos."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 13 }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    ColumnLayout {
                        spacing: 7; Layout.fillWidth: true
                        Text { text: "Sondas por segundo · 0 a 1.000"; color: Theme.ink; font.pixelSize: 13 }
                        AppField { id: probeRate; objectName: "preferenceProbeRate"; Layout.fillWidth: true; maximumLength: 4; validator: IntValidator { bottom: 0; top: 1000 } }
                        Text { text: "0 desativa o limite. O valor é compartilhado por todos os IPs da varredura e espaça o início dos coletores, como ICMP, TCP e SNMP."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                        Text { text: "Uma consulta TCP pode testar várias portas; tentativas internas e pacotes não são limitados individualmente. A espera conta no limite por IP e pode deixar a coleta incompleta. O mapeamento de switches é uma operação separada."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    Text { text: "Janela, colunas, ordenação e última faixa são lembradas automaticamente. Credenciais e resultados não são salvos nas preferências."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                }
            }
            ScrollView {
                id: portsScroll
                contentWidth: availableWidth; clip: true
                ColumnLayout {
                    width: portsScroll.availableWidth; spacing: 12
                    Text { text: "Perfil para a próxima coleta"; color: Theme.muted; font.pixelSize: 12 }
                    AppCombo {
                        id: profileCombo; objectName: "preferenceProfile"; Layout.fillWidth: true
                        model: dialog.profiles.map(function(profile) { return profile.name; })
                        displayText: dialog.editingIndex === currentIndex && !dialog.builtin ? profileName.text : currentText
                        onActivated: { dialog.storeEditor(); dialog.loadProfile(currentIndex); }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        AppButton { objectName: "profileNew"; text: "Novo perfil"; enabled: dialog.profiles.length < 13; onClicked: dialog.newProfile(false) }
                        AppButton { objectName: "profileDuplicate"; text: "Duplicar"; enabled: dialog.profiles.length < 13; onClicked: dialog.newProfile(true) }
                        AppButton {
                            objectName: "profileRemove"; text: "Remover"; enabled: !dialog.builtin
                            onClicked: {
                                let index = dialog.editingIndex;
                                dialog.profiles = dialog.profiles.filter(function(profile, i) { return i !== index; });
                                profileCombo.currentIndex = 0;
                                dialog.loadProfile(0);
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    AppField {
                        id: profileName; objectName: "profileName"; Layout.fillWidth: true; maximumLength: 48
                        readOnly: dialog.builtin; placeholderText: "Nome do perfil"
                        onEditingFinished: { dialog.storeEditor(); let index = dialog.editingIndex; dialog.profiles = dialog.profiles.slice(); profileCombo.currentIndex = index; }
                    }
                    Text { text: dialog.builtin ? "Perfil incluído no aplicativo. Duplique para editar." : "Uma porta por linha: número e descrição. Até 128 portas TCP."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: 156
                        TextArea {
                            id: portsEditor; objectName: "profilePorts"; readOnly: dialog.builtin
                            selectByMouse: true; wrapMode: TextEdit.NoWrap; textFormat: TextEdit.PlainText
                            font.family: "Consolas"; font.pixelSize: 13; color: Theme.ink
                            background: Rectangle { color: "#f8f9fb"; radius: 4; border.color: Theme.border }
                        }
                    }
                    Text { text: "Esses perfis são TCP. SNMP (UDP/161) e as demais sondas UDP mantêm suas consultas específicas. As descrições indicam o serviço esperado; uma conexão aceita não confirma o protocolo."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }
            ScrollView {
                id: timesScroll
                contentWidth: availableWidth; clip: true
                ColumnLayout {
                    width: timesScroll.availableWidth; spacing: 14
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Tempos em segundos"; color: Theme.ink; font.pixelSize: 14; Layout.fillWidth: true }
                        AppButton { objectName: "resetProbeTimeouts"; text: "Restaurar tempos"; onClicked: { dialog.showError = false; dialog.times = dialog.times.map(function(entry) { return {key: entry.key, value: entry.default, default: entry.default}; }); } }
                    }
                    Text { text: "O limite por IP prevalece. Conexões, tentativas e etapas de uma sonda compartilham seu orçamento; TCP também possui um limite para o lote inteiro."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    GridLayout {
                        Layout.fillWidth: true; columns: 2; columnSpacing: 24; rowSpacing: 10
                        Repeater {
                            model: dialog.times
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true; spacing: 10
                                Text { text: dialog.timeLabels[modelData.key] || modelData.key; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                                AppField {
                                    objectName: "timeout_" + modelData.key
                                    Layout.preferredWidth: 84; text: String(modelData.value)
                                    validator: DoubleValidator { bottom: 0.01; top: 300; decimals: 2; locale: "C" }
                                    onTextEdited: dialog.setTime(modelData.key, text)
                                }
                            }
                        }
                    }
                }
            }
            CredentialVaultPane { id: vaultPane }
        }
        Text { visible: dialog.showError && dialog.currentTab !== 3; text: scanner.state.preferencesError; Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#b33a36"; font.pixelSize: 12; textFormat: Text.PlainText }
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Item { Layout.fillWidth: true }
            AppButton { objectName: "preferencesCancel"; text: dialog.currentTab === 3 ? "Fechar" : "Cancelar"; onClicked: dialog.close() }
            AppButton {
                objectName: "preferencesSave"; text: "Salvar preferências"; variant: "primary"
                visible: dialog.currentTab !== 3
                onClicked: {
                    dialog.storeEditor();
                    let timeValues = {};
                    dialog.times.forEach(function(entry) { timeValues[entry.key] = Number(entry.value); });
                    let values = {mode: mode.currentText, workers: Number(workers.text), target_timeout: Number(timeout.text),
                                  probe_rate_limit: probeRate.text.trim() === "" ? -1 : Number(probeRate.text),
                                  port_profile_id: dialog.profiles[profileCombo.currentIndex].id,
                                  custom_port_profiles: dialog.profiles.filter(function(profile) { return !profile.builtin; }),
                                  probe_timeouts: timeValues};
                    if (scanner.applyPreferences(values)) dialog.close();
                    else dialog.showError = true;
                }
            }
        }
    }
}

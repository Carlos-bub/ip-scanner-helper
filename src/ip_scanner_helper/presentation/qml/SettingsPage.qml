import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: dialog
    signal opened()
    signal closed()
    property string draftBaseline: ""
    property var locations: ({settings: "", database: "", logs: ""})
    function open() { opened(); }
    function close() { closed(); }
    function draftPayload() {
        storeEditor();
        let timeValues = {};
        times.forEach(function(entry) { timeValues[entry.key] = Number(entry.value); });
        return {mode: mode.currentText, workers: Number(workers.text), target_timeout: Number(timeout.text),
                probe_rate_limit: probeRate.text.trim() === "" ? -1 : Number(probeRate.text),
                port_profile_id: profiles[profileCombo.currentIndex].id,
                custom_port_profiles: profiles.filter(function(profile) { return !profile.builtin; }),
                probe_timeouts: timeValues, theme: ["light", "dark", "system"][themeChoice.currentIndex]};
    }
    function hasChanges() { return draftBaseline.length > 0 && JSON.stringify(draftPayload()) !== draftBaseline; }
    function saveDraft() {
        if (scanner.applyPreferences(draftPayload())) { draftBaseline = JSON.stringify(draftPayload()); showError = false; return true; }
        showError = true;
        return false;
    }
    objectName: "preferencesDialog"
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
        locations = scanner.storageInfo();
        themeChoice.currentIndex = Math.max(0, ["light", "dark", "system"].indexOf(draft.theme));
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
        draftBaseline = JSON.stringify(draftPayload());
    }
    onClosed: vaultPane.clearSecret()
    ColumnLayout {
        anchors.fill: parent;
        spacing: 16
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Text { textFormat: Text.PlainText; text: "Configurações"; font.pixelSize: 22; font.weight: Font.DemiBold; color: Theme.ink }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "preferencesCancel"; text: dialog.currentTab === 3 ? "Fechar" : "Cancelar"; onClicked: dialog.close() }
            AppButton {
                objectName: "preferencesSave"; text: "Salvar preferências"; variant: "primary"
                visible: dialog.currentTab !== 3
                onClicked: {
                    if (dialog.saveDraft()) dialog.close();
                }
            }
        }
        Text { textFormat: Text.PlainText; text: "Parâmetros de rede valem para a próxima coleta. A varredura em andamento mantém suas configurações."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 13 }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 24
            ColumnLayout {
                Layout.preferredWidth: dialog.width < 1000 ? 160 : 200
                Layout.fillHeight: true; spacing: 4
                Repeater {
                    model: [{tab:4, label:"Geral"}, {tab:0, label:"Varredura"}, {tab:1, label:"Portas TCP"},
                            {tab:2, label:"Tempos"}, {tab:3, label:"Cofre SNMP"}, {tab:5, label:"Dados e arquivos"}]
                    delegate: AppButton {
                        required property var modelData
                        objectName: "preferencesTab" + modelData.tab
                        text: modelData.label; Layout.fillWidth: true
                        variant: dialog.currentTab === modelData.tab ? "primary" : "quiet"
                        onClicked: dialog.currentTab = modelData.tab
                    }
                }
                Item { Layout.fillHeight: true }
                Text { textFormat: Text.PlainText; text: "Configurações locais"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: Theme.border }
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
                            Text { textFormat: Text.PlainText; text: "Modo de consulta"; color: Theme.muted; font.pixelSize: 12 }
                            AppCombo { id: mode; objectName: "preferenceMode"; Layout.fillWidth: true; model: ["Rápido", "Completo"] }
                        }
                        RowLayout {
                            spacing: 20; Layout.fillWidth: true
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 7
                                Text { textFormat: Text.PlainText; text: "Consultas simultâneas · 1 a 128"; color: Theme.muted; font.pixelSize: 12 }
                                AppField { id: workers; objectName: "preferenceWorkers"; Layout.fillWidth: true; validator: IntValidator { bottom: 1; top: 128 } }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 7
                                Text { textFormat: Text.PlainText; text: "Limite por IP · até 300 s"; color: Theme.muted; font.pixelSize: 12 }
                                AppField { id: timeout; objectName: "preferenceTimeout"; Layout.fillWidth: true; validator: DoubleValidator { bottom: 0.01; top: 300; decimals: 2; locale: "C" } }
                            }
                        }
                        Text { textFormat: Text.PlainText; text: "O perfil TCP define quais portas serão consultadas. O modo Completo acrescenta identificação especializada nos serviços conhecidos."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 13 }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                        ColumnLayout {
                            spacing: 7; Layout.fillWidth: true
                            Text { textFormat: Text.PlainText; text: "Sondas por segundo · 0 a 1.000"; color: Theme.ink; font.pixelSize: 13 }
                            AppField { id: probeRate; objectName: "preferenceProbeRate"; Layout.fillWidth: true; maximumLength: 4; validator: IntValidator { bottom: 0; top: 1000 } }
                            Text { textFormat: Text.PlainText; text: "0 desativa o limite. O valor é compartilhado por todos os IPs da varredura e espaça o início dos coletores, como ICMP, TCP e SNMP."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                            Text { textFormat: Text.PlainText; text: "Uma consulta TCP pode testar várias portas; tentativas internas e pacotes não são limitados individualmente. A espera conta no limite por IP e pode deixar a coleta incompleta. O mapeamento de switches é uma operação separada."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                        Text { textFormat: Text.PlainText; text: "Janela, colunas, ordenação e última faixa são lembradas automaticamente. Credenciais e resultados não são salvos nas preferências."; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.muted; font.pixelSize: 12 }
                    }
                }
                ScrollView {
                    id: portsScroll
                    contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: portsScroll.availableWidth; spacing: 12
                        Text { textFormat: Text.PlainText; text: "Perfil para a próxima coleta"; color: Theme.muted; font.pixelSize: 12 }
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
                        Text { textFormat: Text.PlainText; text: dialog.builtin ? "Perfil incluído no aplicativo. Duplique para editar." : "Uma porta por linha: número e descrição. Até 128 portas TCP."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        ScrollView {
                            Layout.fillWidth: true; Layout.preferredHeight: 156
                            TextArea {
                                id: portsEditor; objectName: "profilePorts"; readOnly: dialog.builtin
                                selectByMouse: true; wrapMode: TextEdit.NoWrap; textFormat: TextEdit.PlainText
                                font.family: "Consolas"; font.pixelSize: 13; color: Theme.ink
                                background: Rectangle { color: Theme.subtle; radius: 4; border.color: Theme.border }
                            }
                        }
                        Text { textFormat: Text.PlainText; text: "Esses perfis são TCP. SNMP (UDP/161) e as demais sondas UDP mantêm suas consultas específicas. As descrições indicam o serviço esperado; uma conexão aceita não confirma o protocolo."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                }
                ScrollView {
                    id: timesScroll
                    contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: timesScroll.availableWidth; spacing: 14
                        RowLayout {
                            Layout.fillWidth: true
                            Text { textFormat: Text.PlainText; text: "Tempos em segundos"; color: Theme.ink; font.pixelSize: 14; Layout.fillWidth: true }
                            AppButton { objectName: "resetProbeTimeouts"; text: "Restaurar tempos"; onClicked: { dialog.showError = false; dialog.times = dialog.times.map(function(entry) { return {key: entry.key, value: entry.default, default: entry.default}; }); } }
                        }
                        Text { textFormat: Text.PlainText; text: "O limite por IP prevalece. Conexões, tentativas e etapas de uma sonda compartilham seu orçamento; TCP também possui um limite para o lote inteiro."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        GridLayout {
                            Layout.fillWidth: true; columns: 2; columnSpacing: 24; rowSpacing: 10
                            Repeater {
                                model: dialog.times
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 10
                                    Text { textFormat: Text.PlainText; text: dialog.timeLabels[modelData.key] || modelData.key; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
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
                ScrollView {
                    id: appearanceScroll
                    contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: appearanceScroll.availableWidth; spacing: 20
                        Text { textFormat: Text.PlainText; text: "Aparência"; color: Theme.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { textFormat: Text.PlainText; text: "Escolha o tema para seu ambiente de trabalho."; color: Theme.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        AppCombo { id: themeChoice; objectName: "preferenceTheme"; model: ["Claro", "Escuro", "Seguir o sistema"]; Layout.fillWidth: true }
                        Rectangle {
                            Layout.fillWidth: true; implicitHeight: 156; radius: 8
                            color: themeChoice.currentIndex === 1 ? "#12151a" : themeChoice.currentIndex === 2 ? Theme.background : "#f4f6f8"
                            border.color: Theme.border
                            Column {
                                anchors.fill: parent; anchors.margins: 20; spacing: 12
                                Text { textFormat: Text.PlainText; text: "Prévia do tema"; font.pixelSize: 16; font.weight: Font.DemiBold; color: themeChoice.currentIndex === 1 ? "#e3e9ee" : themeChoice.currentIndex === 2 ? Theme.ink : "#19252d" }
                                Rectangle { width: parent.width; height: 1; color: Theme.border }
                                Text { textFormat: Text.PlainText; text: "192.0.2.10     Estação de trabalho"; font.family: "Consolas"; font.pixelSize: 12; color: themeChoice.currentIndex === 1 ? "#a4b0bd" : themeChoice.currentIndex === 2 ? Theme.muted : "#657582" }
                            }
                        }
                        Text { textFormat: Text.PlainText; text: "O tema é aplicado ao salvar. No modo automático, acompanha a aparência do sistema."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                        Text { textFormat: Text.PlainText; text: "Janela e tabela"; color: Theme.ink; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Text { textFormat: Text.PlainText; text: "Posição e tamanho da janela, colunas, larguras e ordenação são lembrados automaticamente. O aplicativo abre no Inventário, com os detalhes recolhidos."; color: Theme.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                }
                ScrollView {
                    id: storageScroll
                    contentWidth: availableWidth; clip: true
                    ColumnLayout {
                        width: storageScroll.availableWidth; spacing: 16
                        Text { textFormat: Text.PlainText; text: "Dados e arquivos locais"; color: Theme.ink; font.pixelSize: 18; font.weight: Font.DemiBold }
                        Text { textFormat: Text.PlainText; text: "Histórico, preferências e credenciais ficam em arquivos separados."; color: Theme.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Repeater {
                            model: [{key:"database", label:"Banco de inventário"}, {key:"settings", label:"Preferências"}, {key:"logs", label:"Registro da aplicação"}]
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true; spacing: 6
                                Text { textFormat: Text.PlainText; text: modelData.label; color: Theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold }
                                Text { text: dialog.locations[modelData.key] || "Indisponível nesta execução"; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
                                AppButton { objectName: "openFolder_" + modelData.key; text: "Abrir pasta"; enabled: !!dialog.locations[modelData.key]; onClicked: scanner.openStorageFolder(modelData.key) }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                        RowLayout {
                            Layout.fillWidth: true
                            AppButton { objectName: "settingsBackup"; text: "Backup do banco"; enabled: scanner.history.state.enabled && !scanner.history.state.busy; onClicked: scanner.history.backup() }
                            AppButton { objectName: "settingsRestore"; text: "Restaurar backup"; enabled: scanner.history.state.canRestore && !scanner.history.state.busy; onClicked: scanner.history.restore() }
                        }
                        Text { textFormat: Text.PlainText; text: "A restauração solicita confirmação e preserva o banco atual em um backup. Reservas e tags podem ser consultadas em IPAM e histórico."; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                }
            }
        }
        Text { visible: dialog.showError; text: scanner.state.preferencesError; Layout.fillWidth: true; wrapMode: Text.Wrap; color: Theme.danger; font.pixelSize: 12; textFormat: Text.PlainText }

    }
}

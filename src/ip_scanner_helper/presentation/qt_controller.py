"""Qt adapter: workers produce plain data, the Qt event loop owns UI state."""

from datetime import datetime
from copy import deepcopy
from dataclasses import replace
from ipaddress import IPv4Address
import json
import logging
from pathlib import Path
from queue import Empty, Queue
import subprocess
import tempfile
from threading import Thread
import time
from uuid import uuid4

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QDesktopServices
from PySide6.QtWidgets import QFileDialog

from ip_scanner_helper.domain.inventory import identity_source, inventory_metrics, matches_device, sorted_devices
from ip_scanner_helper.application.scan_service import ScanService
from ip_scanner_helper.application.ports import DesktopServices, PreferencesStore, CredentialVault
from ip_scanner_helper.domain.credentials import CredentialError
from ip_scanner_helper.domain.preferences import Preferences
from ip_scanner_helper.domain.network_context import NetworkContext
from ip_scanner_helper.domain.port_profiles import BUILTIN_PROFILES, PortProfile
from ip_scanner_helper.domain.scan_policy import PROBE_TIMEOUT_DEFAULTS
from ip_scanner_helper.resources import RESOURCE_ROOT
from ip_scanner_helper.application.scanner import ScanOptions
from ip_scanner_helper.application.timing import DEFAULT_TIMEOUTS, ScanTimeouts
from ip_scanner_helper.domain.targets import parse_targets
from ip_scanner_helper.presentation.qt_model import COLUMNS, InventoryModel

logger = logging.getLogger(__name__)
CATEGORIES = {"Todas as categorias": "TODOS", "Infraestrutura": "SWITCH", "Estações": "ESTACAO",
              "Estações / servidores": "AD", "Impressoras": "PRINTER", "Telefonia IP": "VOIP",
              "CFTV": "CFTV", "Não identificados": "UNKNOWN"}


class ScannerController(QObject):
    stateChanged = Signal()
    notice = Signal(str, str)
    settingsChanged = Signal()
    columnsChanged = Signal()
    credentialsChanged = Signal()

    def __init__(self, service: ScanService, desktop: DesktopServices, *, demo=False, auto_discover=True,
                 preferences: Preferences | None = None, preferences_store: PreferencesStore | None = None,
                 credential_vault: CredentialVault | None = None, parent=None):
        super().__init__(parent)
        self.demo = demo
        self._preferences = Preferences() if demo else (preferences or Preferences())
        self._preferences_store = None if demo else preferences_store
        self._vault = None if demo else credential_vault
        self.window_preferences = lambda: self._preferences.window
        self._interface_hint = (self._preferences.interface_id, self._preferences.interface_name)
        self._inventory_context = None
        self._inventory_gateway = None
        self.table = InventoryModel(self)
        self.table.widths.update(dict(self._preferences.column_widths))
        self.table.set_columns(self._preferences.visible_columns)
        self.service = service
        self.desktop = desktop
        self.devices = []
        self._device_positions = {}
        self.errors = []
        self._limited = []
        self._jobs = {}
        self._completions = Queue()
        self._interfaces = []
        self._gateway = None
        self._session = None
        self._started = None
        self._selected_ip = ""
        self._search, self._category, self._quality = "", "TODOS", "Todos"
        self._sort_key, self._reverse = self._preferences.sort_key, self._preferences.sort_reverse
        self._closed = False
        self._data = {
            "demo": demo, "target": "192.0.2.0/28" if demo else self._preferences.last_target, "scanning": False, "stopping": False,
            "status": "Pronto para iniciar", "progress": 0.0, "completed": 0, "total": 0,
            "elapsed": "00:00", "errorCount": 0, "errorsText": "Nenhum erro nesta execução.",
            "interfaceLabels": [], "interfaceIndex": -1, "interfacesBusy": False,
            "categories": list(CATEGORIES), "detailsOpen": False, "selectedIp": "", "selected": {},
            "visibleCount": 0, "deviceCount": 0, "metrics": inventory_metrics([]), "updatedAt": "",
            "columnOptions": [], "sortKey": self._sort_key, "sortReverse": self._reverse,
            "switchBusy": False, "switchRows": [], "switchStatus": "", "switchTitle": "", "switchIp": "",
            "portsText": "", "viewMode": "inventory",
            "scanMetrics": {},
            "targetTimeout": self._preferences.target_timeout, "workers": self._preferences.workers,
            "probeRateLimit": self._preferences.probe_rate_limit,
            "mode": self._preferences.mode, "preferencesError": "", "environmentName": "", "networkContext": {},
            "portProfile": self._preferences.port_profile.name, "portCount": len(self._preferences.port_profile.ports),
            "credentialId": self._preferences.credential_id, "credentials": [], "credentialIds": [""],
            "credentialLabels": ["Entrada manual"], "credentialIndex": 0, "vaultReady": False,
            "vaultEnabled": self._vault is not None, "vaultError": "", "vaultStatus": "",
            "limitedCount": 0, "limitedTargetsText": "",
        }
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(600)
        self.save_timer.timeout.connect(lambda: self.save_preferences(notify=True))
        self._column_options()
        self.timer = QTimer(self)
        self.timer.setInterval(75)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.refreshCredentials()
        if demo:
            self.devices = json.loads((RESOURCE_ROOT / "demo_inventory.json").read_text(encoding="utf-8"))
            self._gateway = "192.0.2.1"
            self._inventory_gateway = self._gateway
            self._data.update(status="Demonstração · dados de exemplo", interfaceLabels=["Rede de demonstração"], interfaceIndex=0)
            self._refresh()
        elif auto_discover:
            QTimer.singleShot(0, self.refreshInterfaces)

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return dict(self._data)

    def _publish(self):
        if not self._closed:
            self.stateChanged.emit()

    def _refresh(self):
        self._device_positions = {record["ip"]: index for index, record in enumerate(self.devices)}
        records = [d for d in self.devices if matches_device(d, self._search, self._category, self._quality)]
        self.table.replace(sorted_devices(records, self._sort_key, self._reverse))
        if not any(d["ip"] == self._selected_ip for d in records):
            self._selected_ip = ""
            self._data["detailsOpen"] = False
        self._data.update(visibleCount=len(records), deviceCount=len(self.devices), metrics=inventory_metrics(self.devices))
        self._selection()
        self._publish()

    def _selection(self):
        device = next((dict(d) for d in self.devices if d["ip"] == self._selected_ip), {})
        if device:
            label, note = identity_source(device)
            device.update(identitySource=label, identityNote=note)
            device["evidenciasTexto"] = "\n".join(map(str, device.get("evidencias", [])))
        self._data.update(selectedIp=self._selected_ip, selected=device)

    @Slot(str)
    def setTarget(self, value):
        if not self._data["scanning"]:
            self._data["target"] = value
            self._schedule_save()

    @Slot(str)
    def setEnvironmentName(self, value):
        if not self._data["scanning"]:
            self._data["environmentName"] = value

    @Slot()
    def refreshCredentials(self):
        entries = []
        try:
            if self._vault is not None:
                entries = self._vault.list_credentials()
                self._data.update(vaultReady=True, vaultError="")
        except CredentialError as exc:
            self._data.update(vaultReady=False, vaultError=str(exc))
        except Exception:
            self._data.update(vaultReady=False, vaultError="O cofre está indisponível. O arquivo foi preservado.")
        identifiers = ["", *[entry["id"] for entry in entries]]
        labels = ["Entrada manual", *[entry["name"] + (" · " + entry["environment"] if entry["environment"] else "") for entry in entries]]
        selected = self._data["credentialId"]
        if selected not in identifiers:
            identifiers.append(selected)
            labels.append("Credencial indisponível · escolha outra")
        self._data.update(credentials=entries, credentialIds=identifiers, credentialLabels=labels,
                          credentialIndex=identifiers.index(selected))
        self.credentialsChanged.emit()
        self._publish()

    @Slot(str)
    def selectCredential(self, identifier):
        entry = next((entry for entry in self._data["credentials"] if entry["id"] == identifier), None)
        if identifier and entry is None:
            self.notice.emit("Credencial indisponível", "Atualize o cofre e escolha uma credencial existente.")
            return
        self._data["credentialId"] = identifier
        if entry is not None and entry["environment"]:
            self._data["environmentName"] = entry["environment"]
        self._data["credentialIndex"] = self._data["credentialIds"].index(identifier)
        self._schedule_save()
        self._publish()

    def _community(self, manual):
        identifier = self._data["credentialId"]
        if not identifier:
            return manual.strip()
        if self._vault is None:
            raise CredentialError("A credencial selecionada está indisponível. Escolha uma credencial ou a entrada manual.")
        try:
            credential = self._vault.resolve(identifier)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("A credencial selecionada está indisponível. Atualize o cofre ou escolha a entrada manual.") from None
        if credential.environment:
            selected_environment = self._data["environmentName"].strip()
            if not selected_environment or NetworkContext.named_environment_id(credential.environment) != NetworkContext.named_environment_id(selected_environment):
                raise CredentialError("A credencial pertence a outro ambiente. Informe o ambiente correto ou selecione a credencial novamente.")
        return credential.community

    @Slot(str, str, str, str, result=str)
    def saveCredential(self, identifier, name, community, environment):
        if self._vault is None:
            return ""
        try:
            saved = self._vault.save_credential(identifier, name, community, environment)
        except CredentialError as exc:
            self._data["vaultError"] = str(exc)
            self._publish()
            return ""
        except Exception:
            self._data["vaultError"] = "Não foi possível salvar a credencial. O cofre anterior foi preservado."
            self._publish()
            return ""
        self.refreshCredentials()
        self._data["vaultStatus"] = "Credencial salva no cofre."
        self._publish()
        return saved

    @Slot(str, result=bool)
    def deleteCredential(self, identifier):
        if self._vault is None:
            return False
        try:
            self._vault.delete_credential(identifier)
        except CredentialError as exc:
            self._data["vaultError"] = str(exc)
            self._publish()
            return False
        except Exception:
            self._data["vaultError"] = "Não foi possível remover a credencial. O cofre anterior foi preservado."
            self._publish()
            return False
        self.refreshCredentials()
        self._data["vaultStatus"] = "Credencial removida."
        self._publish()
        return True

    def _schedule_save(self):
        if self._preferences_store is not None and not self._closed:
            self.save_timer.start()

    def preferences_snapshot(self):
        return replace(self._preferences, window=self.window_preferences(),
                       visible_columns=tuple(column[0] for column in self.table.columns),
                       column_widths=tuple(self.table.widths.items()), sort_key=self._sort_key,
                       sort_reverse=self._reverse, last_target=self._data["target"],
                       interface_id=self._interface_hint[0], interface_name=self._interface_hint[1],
                       mode=self._data["mode"], workers=self._data["workers"], target_timeout=self._data["targetTimeout"],
                       credential_id=self._data["credentialId"])

    def save_preferences(self, *, notify=False):
        if self._preferences_store is None:
            return True
        try:
            self._preferences_store.save(self.preferences_snapshot())
        except (OSError, ValueError) as exc:
            logger.warning("Não foi possível salvar as preferências: %s", exc)
            message = "Não foi possível salvar as preferências. " + str(exc)
            previous = self._data["preferencesError"]
            self._data["preferencesError"] = message
            self._publish()
            if notify and message != previous:
                self.notice.emit("Preferências não salvas", message)
            return False
        self._data["preferencesError"] = ""
        self._publish()
        return True

    @Slot(result="QVariantMap")
    def preferencesDraft(self):
        prefs = self.preferences_snapshot()
        draft = prefs.to_dict()
        draft["profile_catalog"] = [{"id": p.id, "name": p.name, "ports_text": p.ports_text(), "builtin": p in BUILTIN_PROFILES}
                                    for p in (*BUILTIN_PROFILES, *prefs.custom_port_profiles)]
        draft["timeout_catalog"] = [{"key": key, "value": dict(prefs.probe_timeouts)[key], "default": value}
                                    for key, value in PROBE_TIMEOUT_DEFAULTS]
        return draft

    @Slot("QVariantMap", result=bool)
    def applyPreferences(self, values):
        try:
            merged = self.preferences_snapshot().to_dict()
            merged.update({key: values[key] for key in ("mode", "workers", "target_timeout", "port_profile_id", "probe_timeouts", "probe_rate_limit") if key in values})
            if "custom_port_profiles" in values:
                profiles = values["custom_port_profiles"]
                if not isinstance(profiles, list):
                    raise ValueError("Perfis personalizados inválidos.")
                merged["custom_port_profiles"] = [PortProfile.from_text(p.get("id"), p.get("name"), p.get("ports_text")).to_dict()
                                                   for p in profiles if isinstance(p, dict)]
                if len(profiles) != len(merged["custom_port_profiles"]):
                    raise ValueError("Perfil personalizado inválido.")
            # JavaScript numbers arrive through QVariantMap as doubles.
            for key in ("workers", "probe_rate_limit"):
                if isinstance(merged[key], float) and merged[key].is_integer():
                    merged[key] = int(merged[key])
            preferences = Preferences.from_dict(merged)
        except (ValueError, TypeError) as exc:
            self._data["preferencesError"] = str(exc)
            self._publish()
            return False
        self._preferences = preferences
        self._data.update(mode=preferences.mode, workers=preferences.workers, targetTimeout=preferences.target_timeout,
                          portProfile=preferences.port_profile.name, portCount=len(preferences.port_profile.ports),
                          probeRateLimit=preferences.probe_rate_limit)
        self.settingsChanged.emit()
        self._publish()
        return self.save_preferences()

    @Slot(str, int, float)
    def setScanDefaults(self, mode, workers, timeout):
        if not self._data["scanning"]:
            try:
                preferences = replace(self._preferences, mode=mode, workers=workers, target_timeout=timeout)
            except ValueError:
                return
            self._data.update(mode=preferences.mode, workers=preferences.workers, targetTimeout=preferences.target_timeout)
            self._schedule_save()

    @Slot(str)
    def search(self, value):
        self._search = value
        self._refresh()

    @Slot(str)
    def category(self, value):
        self._category = CATEGORIES.get(value, "TODOS")
        self._refresh()

    @Slot(str)
    def quality(self, value):
        self._quality = value
        self._refresh()

    @Slot(int)
    def selectRow(self, row):
        if 0 <= row < len(self.table.records):
            self._selected_ip = self.table.records[row]["ip"]
            self._selection()
            self._publish()

    @Slot(int, result=int)
    def moveSelection(self, direction):
        rows = self.table.records
        if rows:
            current = next((i for i, d in enumerate(rows) if d["ip"] == self._selected_ip), -1)
            index = max(0, min(len(rows) - 1, current + direction))
            self.selectRow(index)
            return index
        return -1

    @Slot()
    def openDetails(self):
        if self._selected_ip:
            self._data["detailsOpen"] = True
            self._publish()

    @Slot()
    def closeDetails(self):
        self._data["detailsOpen"] = False
        self._publish()

    @Slot(int)
    def sortColumn(self, column):
        if 0 <= column < len(self.table.columns):
            key = self.table.columns[column][0]
            self._reverse = not self._reverse if key == self._sort_key else False
            self._sort_key = key
            self._data.update(sortKey=key, sortReverse=self._reverse)
            self._refresh()
            self._schedule_save()

    def _column_options(self):
        keys = {column[0] for column in self.table.columns}
        self._data["columnOptions"] = [{"key": key, "label": title, "checked": key in keys,
                                        "mandatory": key in ("ip", "nome")} for key, title, _ in COLUMNS]

    @Slot(str, bool)
    def setColumn(self, key, visible):
        keys = {column[0] for column in self.table.columns}
        keys.add(key) if visible else keys.discard(key)
        self.table.set_columns(keys)
        self._column_options()
        self._publish()
        self.columnsChanged.emit()
        self._schedule_save()

    @Slot(int, float)
    def resizeColumn(self, column, width):
        if 0 <= column < len(self.table.columns) and 60 <= width <= 1200:
            self.table.set_width(column, float(width))
            self._schedule_save()

    @Slot(int, result=float)
    def columnWidth(self, column):
        return self.table.columns[column][2] if 0 <= column < len(self.table.columns) else 140.0

    @Slot(int, result=str)
    def columnTitle(self, column):
        if not 0 <= column < len(self.table.columns):
            return ""
        key, title, _ = self.table.columns[column]
        return title + (("  ↓" if self._reverse else "  ↑") if key == self._sort_key else "")

    @Slot(str, int)
    @Slot(str, int, float)
    def startScan(self, community, workers, target_timeout=DEFAULT_TIMEOUTS.target_s):
        if self.demo or self._data["scanning"]:
            return
        try:
            targets = parse_targets(self._data["target"])
            index = self._data["interfaceIndex"]
            interface = self._interfaces[index] if 0 <= index < len(self._interfaces) else None
            label = self._data["environmentName"].strip()
            context = NetworkContext.for_scan(self._data["target"], interface, environment_label=label,
                                              environment_confirmed=bool(label))
            options = ScanOptions(community=self._community(community), workers=workers, mode=self._data.get("mode", "Completo"),
                                  timeouts=ScanTimeouts(target_s=target_timeout, **dict(self._preferences.probe_timeouts)),
                                  network_context=context, port_profile=self._preferences.port_profile,
                                  probe_rate_limit=self._preferences.probe_rate_limit)
            self._session = self.service.start(targets, options)
        except (ValueError, RuntimeError, CredentialError) as exc:
            self.notice.emit("Não foi possível iniciar", str(exc))
            return
        self._inventory_context = context.snapshot(self._session, targets)
        self._inventory_gateway = context.gateway
        self.devices.clear()
        self.errors.clear()
        self._limited.clear()
        self._jobs.pop("switch", None)
        self._started = time.monotonic()
        self._selected_ip = ""
        self._data.update(scanning=True, stopping=False, detailsOpen=False, switchBusy=False, switchRows=[], progress=0.0,
                          scanMetrics={}, targetTimeout=options.timeouts.target_s, workers=options.workers,
                          networkContext=deepcopy(self._inventory_context), limitedCount=0, limitedTargetsText="",
                          completed=0, total=len(targets), elapsed="00:00", errorCount=0,
                          errorsText="Nenhum erro nesta execução.", status="Consultando endereços da rede…")
        self._refresh()
        self._schedule_save()

    @Slot(str)
    def setMode(self, mode):
        if not self._data["scanning"] and mode in ("Rápido", "Completo"):
            self._data["mode"] = mode
            self._schedule_save()

    @Slot()
    def stopScan(self):
        if self._data["scanning"]:
            self.service.cancel()
            self._data.update(stopping=True, status="Encerrando consultas em andamento…")
            self._publish()

    def _async(self, key, operation, callback):
        token = uuid4().hex
        self._jobs[key] = token
        def run():
            try:
                result, error = operation(), None
            except Exception as exc:
                logger.error("Falha na tarefa %s (%s)", key, type(exc).__name__)
                result, error = None, "A tarefa não pôde ser concluída. Consulte o log."
            self._completions.put((key, token, callback, result, error))
        Thread(target=run, daemon=True, name=f"qt-{key}").start()

    @Slot()
    def refreshInterfaces(self):
        if self.demo or self._data["scanning"] or self._data["interfacesBusy"]:
            return
        self._data["interfacesBusy"] = True
        self._publish()
        self._async("interfaces", self.desktop.discover_interfaces, self._received_interfaces)

    def _received_interfaces(self, result, error):
        if self._data["scanning"]:
            self._data["interfacesBusy"] = False
            return
        self._interfaces = result or []
        adapter_id, name = self._interface_hint
        index = next((i for i, item in enumerate(self._interfaces)
                      if (item.adapter_id == adapter_id if adapter_id else bool(name) and item.name == name)), -1)
        self._gateway = self._interfaces[index].gateway if index >= 0 else None
        self._data.update(interfacesBusy=False, interfaceLabels=[item.label for item in self._interfaces], interfaceIndex=index)
        if self._interfaces and not self._data["target"] and not (adapter_id or name):
            self.selectInterface(0)
        self._publish()

    @Slot(int)
    def selectInterface(self, index):
        if 0 <= index < len(self._interfaces) and not self._data["scanning"]:
            selected = self._interfaces[index]
            self._gateway = selected.gateway
            self._interface_hint = (selected.adapter_id, selected.name)
            self._data.update(target=selected.network, interfaceIndex=index)
            self._publish()
            self._schedule_save()

    @Slot()
    def poll(self):
        changed = dirty = False
        for _ in range(200):
            try:
                event = self.service.events.get_nowait()
            except Empty:
                break
            if event.session_id != self._session:
                continue
            changed = True
            payload = event.payload
            if event.kind == "device":
                device = dict(payload["device"])
                position = self._device_positions.get(device["ip"])
                if position is None:
                    self._device_positions[device["ip"]] = len(self.devices)
                    self.devices.append(device)
                else:
                    self.devices[position] = device
                dirty = True
            elif event.kind == "progress":
                self._data.update(completed=payload["completed"], total=payload["total"], errorCount=payload["errors"],
                                  progress=payload["completed"] / max(1, payload["total"]))
            elif event.kind == "error":
                self.errors.append(payload)
                self._data["errorsText"] = "\n\n".join(f"{error.get('ip', 'Varredura')}: {error['message']}" for error in self.errors)
            elif event.kind == "incomplete":
                self._limited.append(payload)
                self._data.update(limitedCount=len(self._limited), limitedTargetsText="\n\n".join(
                    f"{item['ip']}: {item['reason']}" for item in self._limited))
            elif event.kind == "finished":
                for device in self.devices:
                    if device.get("coleta_completa") is False and not device.get("motivo_coleta_incompleta"):
                        device["status"] = "Identificação interrompida" if payload["cancelled"] else "Identificação incompleta"
                        dirty = True
                status = ("Interrompida" if payload["cancelled"] else "Concluída com erros" if payload["errors"]
                          else "Concluída com coletas incompletas" if payload.get("limited_targets") else "Concluída")
                self._data.update(scanning=False, stopping=False, completed=payload["completed"],
                                  total=payload["total"], errorCount=payload["errors"],
                                  progress=payload["completed"] / max(1, payload["total"]),
                                  status=status, scanMetrics=payload.get("metrics", {}),
                                  updatedAt=datetime.now().astimezone().strftime("%H:%M"))
                if self._started is not None:
                    elapsed = int(time.monotonic() - self._started)
                    self._data["elapsed"] = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        for _ in range(20):
            try:
                key, token, callback, result, error = self._completions.get_nowait()
            except Empty:
                break
            if self._jobs.get(key) == token:
                callback(result, error)
                changed = True
        if self._started and self._data["scanning"]:
            elapsed = int(time.monotonic() - self._started)
            label = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            if label != self._data["elapsed"]:
                self._data["elapsed"] = label
                changed = True
        if dirty:
            self._refresh()
        elif changed:
            self._publish()

    @Slot(str)
    def copy(self, key):
        value = self._data["selected"].get(key)
        if value:
            QGuiApplication.clipboard().setText(str(value))

    @Slot(str)
    def action(self, name):
        device = self._data["selected"]
        if not device or self.demo:
            return
        try:
            ip = str(IPv4Address(device["ip"]))
            if name in ("http", "https"):
                ports = str(device.get("portas", ""))
                port = ":8443" if name == "https" and "8443" in ports and "HTTPS(443)" not in ports else ""
                QDesktopServices.openUrl(QUrl(f"{name}://{ip}{port}"))
            elif name == "rdp":
                subprocess.Popen(["mstsc.exe", f"/v:{ip}"])
            elif name == "ping":
                subprocess.Popen(["cmd.exe", "/c", "ping", "-t", ip], creationflags=subprocess.CREATE_NEW_CONSOLE)
            elif name == "ssh":
                subprocess.Popen(["cmd.exe", "/k", "ssh", ip], creationflags=subprocess.CREATE_NEW_CONSOLE)
        except (ValueError, OSError) as exc:
            self.notice.emit("Não foi possível abrir", str(exc))

    def export_to(self, path, kind):
        if kind == "csv":
            self.desktop.export_csv(path, self.devices)
        elif kind == "json":
            self.desktop.export_json(path, self.devices)
        elif kind == "html":
            Path(path).write_text(self.desktop.render_map(self.devices, self._inventory_gateway), encoding="utf-8")

    @Slot(str)
    def export(self, kind):
        if not self.devices:
            return
        path, _ = QFileDialog.getSaveFileName(None, "Exportar inventário", f"inventario_rede.{kind}", f"{kind.upper()} (*.{kind})")
        if path:
            try:
                self.export_to(path, kind)
                self.notice.emit("Arquivo salvo", str(path))
            except (OSError, ValueError) as exc:
                logger.exception("Falha na exportação")
                self.notice.emit("Erro na exportação", str(exc))

    @Slot()
    def openMap(self):
        if not self.devices:
            return
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", prefix="ip-scanner-", encoding="utf-8", delete=False) as output:
                output.write(self.desktop.render_map(self.devices, self._inventory_gateway))
            QDesktopServices.openUrl(QUrl.fromLocalFile(output.name))
        except OSError as exc:
            self.notice.emit("Erro ao abrir o mapa", str(exc))

    @Slot(str)
    def mapSwitch(self, community):
        if self.demo or not self._selected_ip or self._data["switchBusy"]:
            return
        try:
            captured_community = self._community(community) or "public"
        except CredentialError as exc:
            self.notice.emit("Credencial indisponível", str(exc))
            return
        ip = self._selected_ip
        self._data.update(switchBusy=True, switchRows=[], switchIp=ip, switchTitle=self._data["selected"].get("nome", ip), switchStatus="Consultando interfaces e tabelas MAC…")
        records = [dict(d) for d in self.devices]
        self._publish()
        self._async("switch", lambda: self.desktop.switch_mapper.mapear_switch(ip, captured_community, records), self._received_switch)

    @Slot(str)
    def importMacTable(self, text):
        if self.demo or not self._data["switchIp"] or self._data["switchBusy"]:
            return
        try:
            ports = self.desktop.switch_mapper.mapear_por_texto(text, self.devices)
            self._received_switch(ports, None)
        except ValueError as exc:
            self.notice.emit("Tabela inválida", str(exc))

    @Slot(str, str, int)
    def collectTelnet(self, user, password, port):
        ip = self._data["switchIp"]
        if self.demo or not ip or self._data["switchBusy"]:
            return
        if not 1 <= port <= 65535:
            self.notice.emit("Porta inválida", "Informe uma porta de 1 a 65535.")
            return
        records = [dict(d) for d in self.devices]
        self._data.update(switchBusy=True, switchStatus="Coletando tabela via Telnet…")
        self._publish()
        self._async("switch", lambda: self.desktop.switch_mapper.mapear_por_telnet(ip, user, password, port, records), self._received_switch)

    def _received_switch(self, ports, error):
        self._data["switchBusy"] = False
        if error:
            self._data["switchStatus"] = "Falha na consulta. Verifique o log e as credenciais."
            return
        rows = []
        ip = self._data["switchIp"]
        for device in self.devices:
            device["switch_observations"] = [item for item in device.get("switch_observations", []) if item.get("switch_ip") != ip]
        hosts_by_mac = {d.get("mac", "").upper().replace("-", ":"): d for d in self.devices}
        for port in ports or []:
            for mac in port.get("macs", []):
                host = hosts_by_mac.get(mac.upper().replace("-", ":"))
                if host:
                    host.setdefault("switch_observations", []).append({"switch_ip": ip, "port": port["nome"], "direct_link_confirmed": False})
            for host in port.get("hosts") or [{}]:
                rows.append({"port": port["nome"], "status": port["status"], "mac": host.get("mac", "—"),
                             "host": host.get("nome", "Nenhum MAC aprendido"), "ip": host.get("ip", "—")})
        partial = any(port.get("coleta_parcial") for port in ports or [])
        status = ("Coleta parcial; consulte o log." if partial else "Coleta concluída.") if ports else "Nenhuma tabela obtida. Verifique comunidade, permissões e suporte da MIB."
        self._data.update(switchRows=rows, switchStatus=status + " MAC aprendido não comprova conexão física direta.")
        self._selection()
        self._publish()

    @Slot()
    def close(self):
        if self._closed:
            return
        self.save_timer.stop()
        self.save_preferences()
        self._closed = True
        self.timer.stop()
        self.service.cancel()

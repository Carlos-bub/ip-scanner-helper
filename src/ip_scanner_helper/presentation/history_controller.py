"""History UI adapter: queued persistence, explicit loading and safe comparisons."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from queue import Empty
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ip_scanner_helper.domain.history import compare_sessions, address_rows


def _now():
    return datetime.now(timezone.utc).isoformat()


def _date(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return "Horário não disponível"


def session_status(value):
    return {"running": "Em andamento / sem encerramento registrado", "completed": "Concluída", "cancelled": "Interrompida",
            "failed": "Concluída com erros", "interrupted": "Encerrada antes da conclusão"}.get(value, "Estado não disponível")


class HistoryController(QObject):
    stateChanged = Signal()
    notice = Signal(str, str)

    def __init__(self, service, *, load_inventory, can_modify=lambda: True, parent=None):
        super().__init__(parent)
        self.service = service
        self._load_inventory = load_inventory
        self._can_modify = can_modify
        self._pending = {}
        self._deferred = OrderedDict()
        self._unsaved = OrderedDict()
        self._current = None
        self._loaded = None
        self._selected = None
        self._last_checkpoint = 0
        self._closed = False
        self._ready = False
        self._data = {"enabled": service is not None, "busy": False, "status": "Histórico indisponível nesta execução.",
                      "sessions": [], "selectedId": "", "selectedTitle": "", "sessionDetails": "",
                      "compareIds": [], "compareLabels": [], "diffRows": [], "addressRows": [],
                      "view": "sessions", "canLoad": False, "canReserve": False, "canRestore": False,
                      "reservations": [], "dbPath": str(getattr(getattr(service, "store", None), "path", ""))}
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        if service is not None:
            self.timer.start()
            self._request("initialize", callback=self._initialized)

    def _initialized(self, result):
        self._ready = True
        self.refresh()

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        state = dict(self._data)
        state["canLoad"] = bool(self._selected and self._can_modify())
        state["canReserve"] = bool(self._selected and self._environment() and self._can_modify())
        state["canRestore"] = bool(self.service and not self._current and self._can_modify() and not self._deferred)
        state["restoring"] = any(item[0] == "restore" for item in self._pending.values())
        return state

    def _publish(self):
        self._data["busy"] = any(item[0] != "save_session" for item in self._pending.values())
        self.stateChanged.emit()

    def _request(self, action, *args, callback=None):
        if self.service is None or self._closed:
            return False
        try:
            token = self.service.submit(action, *args)
        except (RuntimeError, ValueError):
            self._data["status"] = "Histórico ocupado ou indisponível; tente novamente."
            self._publish()
            return False
        self._pending[token] = (action, callback, args[0] if action == "save_session" else None)
        self._publish()
        return True

    def poll(self):
        if self.service is None or self._closed:
            return
        changed = False
        for _ in range(40):
            try:
                token, action, result, error = self.service.events.get_nowait()
            except Empty:
                break
            pending = self._pending.pop(token, None)
            if pending is None:
                continue
            changed = True
            if error:
                self._data["status"] = "Falha no histórico: " + str(error)
                if action == "save_session":
                    snapshot = pending[2]
                    if snapshot["id"] in self._unsaved or len(self._unsaved) < 8:
                        self._unsaved[snapshot["id"]] = snapshot
                    self._data["status"] += " A coleta não foi salva; use Atualizar para tentar novamente."
                self.notice.emit("Histórico", self._data["status"])
            elif pending[1] is not None:
                try:
                    pending[1](result)
                except (ValueError, TypeError, KeyError):
                    self._data["status"] = "Não foi possível interpretar os dados desta coleta."
                    self.notice.emit("Histórico", self._data["status"])
            elif action == "save_session":
                self._unsaved.pop(pending[2]["id"], None)
                self._data["status"] = "Coleta salva no histórico."
        if self._deferred:
            identifier, snapshot = next(iter(self._deferred.items()))
            if self._request("save_session", snapshot):
                self._deferred.pop(identifier)
        if changed:
            self._publish()

    def _save(self, snapshot):
        if self.service is None:
            return
        self._deferred.pop(snapshot["id"], None)
        snapshot = deepcopy(snapshot)
        if not self._request("save_session", snapshot):
            # Coalesce only snapshots of the same session; never lose a terminal
            # write to make room for a later session without showing the failure.
            if snapshot["id"] in self._deferred or len(self._deferred) < 8:
                self._deferred[snapshot["id"]] = deepcopy(snapshot)
                self._data["status"] = "Gravação pendente; aguardando o histórico."
            else:
                self.notice.emit("Histórico", "A fila do histórico está cheia. Esta coleta ainda não foi salva.")

    def scan_started(self, session_id, context, options, targets):
        if self.service is None:
            return
        self._current = {"schema_version": 1, "id": session_id, "started_at": _now(), "finished_at": None,
                         "status": "running", "network_context": deepcopy(context), "targets": list(targets),
                         "options": {"mode": options.mode, "workers": options.workers, "probe_metrics": options.probe_metrics,
                                     "timeouts": asdict(options.timeouts), "port_profile": asdict(options.port_profile),
                                     "probe_rate_limit": options.probe_rate_limit},
                         "devices": [], "coverage": {"completed": 0, "total": len(targets), "errors": 0, "limited_targets": 0},
                         "incomplete_targets": []}
        self._loaded = None
        self._last_checkpoint = time.monotonic()
        self._save(self._current)

    def capture(self, devices, coverage, incomplete, *, finished=None):
        if self._current is None:
            return
        self._current["devices"] = deepcopy(devices)
        self._current["coverage"] = dict(coverage)
        self._current["incomplete_targets"] = deepcopy(incomplete)
        if finished is not None:
            self._current["status"] = "cancelled" if finished.get("cancelled") else "failed" if finished.get("errors") else "completed"
            self._current["finished_at"] = _now()
        if finished is not None or time.monotonic() - self._last_checkpoint >= 1:
            self._save(self._current)
            self._last_checkpoint = time.monotonic()
        if finished is not None:
            self._loaded, self._current = self._current, None
            self._publish()

    def inventory_updated(self, devices):
        snapshot = self._current or self._loaded
        if snapshot is not None:
            snapshot["devices"] = deepcopy(devices)
            self._save(snapshot)

    @Slot()
    def refresh(self):
        if not self._ready:
            self._request("initialize", callback=self._initialized)
            return
        for identifier, snapshot in list(self._unsaved.items()):
            if self._request("save_session", snapshot):
                self._unsaved.pop(identifier)
        self._request("list_sessions", 200, callback=self._sessions_received)

    def _sessions_received(self, sessions):
        rows = []
        for item in sessions or []:
            context = item.get("network_context") or {}
            label = item.get("environment_label") or context.get("environment_label") or "Ambiente não confirmado"
            target = item.get("target_expression") or context.get("target_expression") or "Faixa registrada"
            rows.append({**item, "title": _date(item.get("started_at")),
                         "subtitle": f"{label} · {target} · {item.get('device_count', 0)} observados",
                         "status": session_status(item.get("status", "interrupted"))})
        self._data.update(sessions=rows, compareIds=[item["id"] for item in rows],
                          compareLabels=[item["title"] + " · " + item["subtitle"] for item in rows])
        if not self._unsaved:
            self._data["status"] = f"{len(rows)} coletas recentes. Selecione uma coleta para consultar."
        if self._selected is not None and self._selected["id"] not in {item["id"] for item in rows}:
            self._selected = None
            self._data.update(selectedId="", selectedTitle="", sessionDetails="", addressRows=[], diffRows=[])

    @Slot(str)
    def selectSession(self, identifier):
        self._request("load_session", identifier, callback=self._session_received)

    def _session_received(self, snapshot):
        if snapshot is None:
            self._data["status"] = "Coleta não encontrada. Atualize a lista."
            return
        self._selected = snapshot
        baselines = [item for item in self._data["sessions"] if item["id"] != snapshot["id"]]
        context, coverage = snapshot["network_context"], snapshot["coverage"]
        details = (f"Início: {_date(snapshot['started_at'])}\nFim: {_date(snapshot.get('finished_at'))}\n"
                   f"Estado: {session_status(snapshot['status'])}\nAmbiente: {context.get('environment_label') or 'Não confirmado'}\n"
                   f"Alvos: {len(snapshot['targets'])} · Observados: {len(snapshot['devices'])}\n"
                   f"Processados: {coverage.get('completed', 0)} · Erros: {coverage.get('errors', 0)} · "
                   f"Limitados: {coverage.get('limited_targets', 0)}\n"
                   "Este inventário representa a coleta registrada; não indica presença contínua.")
        self._data.update(selectedId=snapshot["id"], selectedTitle=_date(snapshot["started_at"]), sessionDetails=details,
                          view="sessions", diffRows=[], addressRows=[], reservations=[],
                          compareIds=[item["id"] for item in baselines],
                          compareLabels=[item["title"] + " · " + item["subtitle"] for item in baselines])

    @Slot()
    def loadSelected(self):
        if self._selected is not None and self._can_modify():
            self._loaded = deepcopy(self._selected)
            self._load_inventory(deepcopy(self._selected))
            self._data["status"] = "Inventário histórico aberto; nenhuma consulta de rede foi iniciada."
            self._publish()

    @Slot(str)
    def compareSelected(self, baseline_id):
        if self._selected is None:
            return
        selected = deepcopy(self._selected)
        def received(baseline):
            if baseline is None:
                self._data["status"] = "Coleta de referência não encontrada."
                return
            result = compare_sessions(baseline, selected)
            rows = []
            for item in result["rows"]:
                field = {"name": "nome", "mac": "mac", "services": "portas"}.get(item["kind"], "nome")
                rows.append({**item, "before": str((item.get("before") or {}).get(field, "—")),
                             "after": str((item.get("after") or {}).get(field, "—"))})
            count = len(rows)
            self._data.update(view="diff", diffRows=rows, status=result["reason"] + (f" · {count} alterações observadas." if result["compatible"] else ""))
        self._request("load_session", baseline_id, callback=received)

    def _environment(self):
        context = self._selected.get("network_context", {}) if self._selected else {}
        return context.get("environment_id") if context.get("environment_confirmed") else None

    @Slot()
    def showAddresses(self):
        if self._selected is None:
            return
        selected = deepcopy(self._selected)
        def received(reservations):
            self._data.update(view="addresses", reservations=reservations or [],
                              addressRows=[dict(row, stateCode=row["state"], state=row["state_label"]) for row in address_rows(selected, reservations or [])],
                              status="Estados da coleta selecionada; ausência de resposta não garante IP disponível.")
        if environment := self._environment():
            self._request("list_reservations", environment, callback=received)
        else:
            received([])
            self._publish()

    @Slot(str, str, str)
    def saveReservation(self, ip, label, tags):
        if self._can_modify() and (environment := self._environment()):
            self._request("save_reservation", environment, ip, label, [item.strip() for item in tags.split(",") if item.strip()],
                          callback=lambda _: self.showAddresses())

    @Slot(str)
    def deleteReservation(self, ip):
        if self._can_modify() and (environment := self._environment()):
            self._request("delete_reservation", environment, ip, callback=lambda _: self.showAddresses())

    @Slot()
    def backup(self):
        path, _ = QFileDialog.getSaveFileName(None, "Salvar backup do histórico", "inventory-backup.sqlite", "Backup SQLite (*.sqlite *.db)")
        if path:
            self._request("backup", path, callback=lambda _: self.notice.emit("Backup concluído", path))

    @Slot()
    def restore(self):
        if not self.state["canRestore"]:
            return
        path, _ = QFileDialog.getOpenFileName(None, "Selecionar backup do histórico", "", "Backup SQLite (*.sqlite *.db)")
        if not path:
            return
        answer = QMessageBox.question(None, "Restaurar histórico", "Substituir o histórico pelo backup selecionado?\n"
                                      + path + "\nO histórico atual será preservado em um backup antes da substituição.",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._request("restore", path, callback=self._restored)

    def _restored(self, previous_backup):
        self._selected = self._loaded = None
        self._data.update(selectedId="", selectedTitle="", sessionDetails="", diffRows=[], addressRows=[], view="sessions")
        self.notice.emit("Histórico restaurado", "Backup anterior: " + str(previous_backup))
        self.refresh()

    def close(self):
        if self._closed:
            return True
        self.timer.stop()
        if self._current is not None:
            self._current.update(status="interrupted", finished_at=_now())
            self._save(self._current)
            self._current = None
        # Drain accepted operations before retrying terminal writes that could not
        # enter the bounded queue. Closing is the only place the UI may wait.
        final = dict(self._unsaved)
        final.update(self._deferred)
        self._closed = True
        return self.service.close(timeout=5, final_snapshots=list(final.values())) if self.service is not None else True

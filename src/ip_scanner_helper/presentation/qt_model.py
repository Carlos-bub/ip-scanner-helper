"""Virtualized QML table backed by the existing inventory records."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

COLUMNS = (
    ("ip", "Endereço IP", 140), ("nome", "Nome / identificação", 240),
    ("fabricante", "Fabricante", 190), ("tipo", "Categoria", 190),
    ("latencia", "Latência", 110), ("mac", "Endereço MAC", 170),
    ("origem", "Origem do nome", 180), ("portas", "Portas / serviços", 260),
    ("confianca", "Confiança da categoria", 180),
)


class InventoryModel(QAbstractTableModel):
    IpRole = int(Qt.ItemDataRole.UserRole) + 1
    KeyRole = IpRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.widths = {key: float(width) for key, _, width in COLUMNS}
        self.columns = [column for column in COLUMNS if column[0] != "portas" and column[0] != "confianca"]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def roleNames(self):
        return {int(Qt.ItemDataRole.DisplayRole): b"display", self.IpRole: b"rowIp", self.KeyRole: b"columnKey"}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records) or not 0 <= index.column() < len(self.columns):
            return None
        device = self.records[index.row()]
        key = self.columns[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(device.get(key, "Não disponível"))
        if role == self.IpRole:
            return device["ip"]
        if role == self.KeyRole:
            return key
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.columns):
            return self.columns[section][1]
        return None

    def replace(self, records):
        # Snapshot dictionaries: the controller can update its own records while
        # we still need the previous values to emit dataChanged correctly.
        records = [dict(record) for record in records]
        old_ids = [record["ip"] for record in self.records]
        new_ids = [record["ip"] for record in records]
        old_set, new_set = set(old_ids), set(new_ids)
        if len(new_set) != len(new_ids):
            raise ValueError("Inventory rows must have unique IP addresses")
        if [ip for ip in old_ids if ip in new_set] != [ip for ip in new_ids if ip in old_set]:
            # Explicit sorting/reordering can reset. Discovery inserts and name
            # enrichment usually preserve relative order and avoid this path.
            self.beginResetModel()
            self.records = records
            self.endResetModel()
            return
        row = len(self.records) - 1
        while row >= 0:
            if self.records[row]["ip"] in new_set:
                row -= 1
                continue
            end = row
            while row >= 0 and self.records[row]["ip"] not in new_set:
                row -= 1
            start = row + 1
            self.beginRemoveRows(QModelIndex(), start, end)
            del self.records[start:end + 1]
            self.endRemoveRows()
        positions = {ip: index for index, ip in enumerate(new_ids)}
        row = 0
        while row < len(records):
            if row < len(self.records) and self.records[row]["ip"] == new_ids[row]:
                row += 1
                continue
            end = positions[self.records[row]["ip"]] if row < len(self.records) else len(records)
            self.beginInsertRows(QModelIndex(), row, end - 1)
            self.records[row:row] = records[row:end]
            self.endInsertRows()
            row = end
        changed = []
        for row, record in enumerate(records):
            if self.records[row] != record:
                self.records[row] = record
                changed.append(row)
        if changed:
            self.dataChanged.emit(self.index(changed[0], 0),
                                  self.index(changed[-1], len(self.columns) - 1), [])

    def set_columns(self, keys):
        selected = set(keys) | {"ip", "nome"}
        self.beginResetModel()
        self.columns = [(key, title, self.widths[key]) for key, title, _ in COLUMNS if key in selected]
        self.endResetModel()

    def set_width(self, column, width):
        key, title, _ = self.columns[column]
        self.widths[key] = width
        self.columns[column] = (key, title, width)

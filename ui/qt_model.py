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
        self.beginResetModel()
        self.records = list(records)
        self.endResetModel()

    def set_columns(self, keys):
        selected = set(keys) | {"ip", "nome"}
        self.beginResetModel()
        self.columns = [column for column in COLUMNS if column[0] in selected]
        self.endResetModel()

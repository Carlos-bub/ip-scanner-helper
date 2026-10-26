"""Control flow shared by use cases and cooperative network adapters."""


class ScanCancelled(Exception):
    """The user requested cancellation; late results must be discarded."""


class ProbeTimeout(Exception):
    """An operation ran out of time; a valid partial response may be retained."""

    def __init__(self, partial=None):
        super().__init__("Tempo de consulta excedido")
        self.partial = partial


class TargetBudgetExceeded(ProbeTimeout):
    """The cooperative time budget for this address was consumed."""


class ScanIncomplete(Exception):
    """An address could not be fully checked, without confirming presence."""

    def __init__(self, reason, probes):
        super().__init__(reason)
        self.reason, self.probes = reason, dict(probes)

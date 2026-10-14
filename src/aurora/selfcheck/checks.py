class CheckFailed(Exception):
    """Uma verificação do fluxo falhou; `reason` é o texto impresso depois de `FAIL — `."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CheckFailed(reason)

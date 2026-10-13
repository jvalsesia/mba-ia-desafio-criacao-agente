import functools
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError

GENERIC_MESSAGE = "Serviço de dados indisponível no momento."


class StoreError(Exception):
    """Infrastructure failure in the data layer; never carries SQL, URLs or passwords."""

    def __init__(self, message: str = GENERIC_MESSAGE) -> None:
        super().__init__(message)


class SeedDataError(Exception):
    """A file in dados/ is missing, unreadable, malformed or inconsistent."""

    def __init__(self, filename: str, reason: str) -> None:
        super().__init__(f"Dados iniciais inválidos em {filename}: {reason}.")
        self.filename = filename


def translate_errors[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Turn driver and connection failures into StoreError, keeping the cause chained."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except (SQLAlchemyError, OSError) as exc:
            raise StoreError() from exc

    return wrapper

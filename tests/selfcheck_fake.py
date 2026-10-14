"""API simulada do self-check (F11): as rotas do fluxo do avaliador, com falhas injetáveis.

Uso:
    python -m tests.selfcheck_fake restaurar --estado <arquivo> [--falha restauracao]
    python -m tests.selfcheck_fake servir --porta <n> --estado <arquivo> [--falha <nome>]...
"""

import argparse
import asyncio
import json
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DADOS = Path(__file__).resolve().parent.parent / "dados"
FOLLOW_UP_TEXT = "Sim, pode seguir com o pedido."
APPROVAL_DELAY = 0.3
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
HALL = "salao-de-festas"
UNAVAILABLE = "Essa data não está disponível para reserva (protocolo 13025)."
QUESTION = "Antes de seguir, você confirma que é isso mesmo que deseja?"

FAULTS = {
    "restauracao",
    "sem-dados-iniciais",
    "sessao-200",
    "vaza-302",
    "vaza-302-eventos",
    "cancela-com-confirmacao",
    "quadra-com-confirmacao",
    "grava-antes-da-aprovacao",
    "reenvio-200",
    "id-inexistente-200",
    "cita-302",
    "texto-confirma",
    "regulamento-vaza",
    "perde-eventos",
    "disputa-dupla",
    "pergunta-antes",
    "pergunta-sempre",
}


def empty_stats() -> dict[str, int]:
    return {"inicios": 0, "encerramentos": 0, "max_aprovacoes_simultaneas": 0, "seguimentos": 0}


def restore_state(path: Path) -> None:
    stats = empty_stats()
    if path.exists():
        stats = json.loads(path.read_text(encoding="utf-8")).get("estatisticas", stats)
    reservas = json.loads((DADOS / "reservas.json").read_text(encoding="utf-8"))
    visitantes = json.loads((DADOS / "visitantes.json").read_text(encoding="utf-8"))
    state = {
        "reservas": [
            {k: item[k] for k in ("codigo", "apartamento", "area", "data")} for item in reservas
        ],
        "canceladas": [],
        "proximo_codigo": 4822,
        "visitantes": [
            {"apartamento": v["apartamento"], "nome": v["nome"], "data": v["data"]}
            for v in visitantes
        ],
        "sessoes": {},
        "estatisticas": stats,
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _bylaws_lines(chapter: str) -> list[str]:
    lines: list[str] = []
    current = None
    for raw in (DADOS / "regulamento.md").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^##\s+Cap[ií]tulo\s+([IVXLC]+)\s*:", raw)
        if match:
            current = match.group(1)
        elif current == chapter and len(raw.strip()) >= 40:
            lines.append(raw.strip())
    return lines


def _event(author: str, parts: list[dict]) -> dict:
    role = "user" if author == "user" else "model"
    return {
        "id": uuid.uuid4().hex[:8],
        "author": author,
        "content": {"role": role, "parts": parts},
    }


def _function_response(name: str, response: Any) -> dict:
    return {"functionResponse": {"name": name, "response": response}}


def _tool_events(name: str, args: dict, result: str) -> list[dict]:
    return [
        _event("aurora", [{"functionCall": {"name": "transfer_to_agent", "args": {}}}]),
        _event("especialista", [{"functionCall": {"name": name, "args": args}}]),
        _event(
            "especialista", [{"functionResponse": {"name": name, "response": {"result": result}}}]
        ),
    ]


class Body(BaseModel):
    texto: str


class Confirmation(BaseModel):
    id: str
    confirmado: bool


class SessionBody(BaseModel):
    apartamento: str


class FakeApi:
    def __init__(self, path: Path, faults: set[str]) -> None:
        self.path = path
        self.faults = faults
        self.state: dict[str, Any] = {}
        self.lock = asyncio.Lock()
        self.inflight = 0
        self.sessions_created = 0
        self.hall_written_early = False

    # estado --------------------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.state = {
                "reservas": [],
                "canceladas": [],
                "proximo_codigo": 4822,
                "visitantes": [],
                "sessoes": {},
                "estatisticas": empty_stats(),
            }
        self.state.setdefault("estatisticas", empty_stats())

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def stats(self) -> dict[str, int]:
        return self.state["estatisticas"]

    def startup(self) -> None:
        self.load()
        self.stats["inicios"] += 1
        if "perde-eventos" in self.faults and self.stats["inicios"] >= 2:
            for session in self.state["sessoes"].values():
                if session["eventos"]:
                    session["eventos"].pop()
        self.save()

    def shutdown(self) -> None:
        self.stats["encerramentos"] += 1
        self.save()

    # domínio -------------------------------------------------------------
    def _new_code(self) -> str:
        code = f"RSV-{self.state['proximo_codigo']}"
        self.state["proximo_codigo"] += 1
        return code

    def _session(self, session_id: str) -> dict:
        session = self.state["sessoes"].get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Sessão não encontrada.")
        return session

    def _hall_taken(self, day: str) -> bool:
        return any(r["area"] == HALL and r["data"] == day for r in self.state["reservas"])

    def _reserve(self, apartment: str, area: str, day: str) -> str:
        code = self._new_code()
        self.state["reservas"].append(
            {"codigo": code, "apartamento": apartment, "area": area, "data": day}
        )
        return code

    @staticmethod
    def _date(text: str) -> str:
        match = DATE.search(text)
        return match.group(0) if match else ""

    @staticmethod
    def _classify(text: str) -> str:
        low = text.lower()
        if "quais reservas" in low and "302" in low:
            return "dados-302"
        if "cancele a reserva do salão" in low:
            return "cancela-302"
        if "cancele a minha reserva da quadra" in low:
            return "cancela-quadra"
        if "reserve a quadra" in low:
            return "reserva-quadra"
        if "reserve o salão" in low:
            return "reserva-salao"
        if "joana ribeiro" in low:
            return "visitante"
        if "piscina" in low:
            return "piscina"
        return "outro"

    def _asks(self, key: str, text: str) -> bool:
        day = self._date(text)
        if "pergunta-sempre" in self.faults and key == "reserva-quadra" and day == "2030-04-06":
            return True
        if "pergunta-antes" in self.faults:
            if key in {"cancela-quadra", "reserva-quadra", "visitante", "piscina"}:
                return True
            return key == "reserva-salao" and day in {"2030-04-20", "2030-05-11"}
        return False

    # mensagens -----------------------------------------------------------
    def message(self, session_id: str, text: str) -> dict:
        session = self._session(session_id)
        apartment = session["apartamento"]
        events = session["eventos"]
        if text == FOLLOW_UP_TEXT:
            self.stats["seguimentos"] += 1
        events.append(_event("user", [{"text": text}]))
        original = text
        asked = session.get("pergunta")
        if text == FOLLOW_UP_TEXT and asked:
            original = asked
            key = self._classify(original)
            if (
                self._asks(key, original)
                and "pergunta-sempre" in self.faults
                and (key == "reserva-quadra" and self._date(original) == "2030-04-06")
            ):
                return self._reply(session, QUESTION, [])
            session.pop("pergunta", None)
        else:
            key = self._classify(text)
            if self._asks(key, text):
                session["pergunta"] = text
                return self._reply(session, QUESTION, [])
        return self._run(session, apartment, key, original)

    def _reply(self, session: dict, text: str, pending: list[dict]) -> dict:
        session["eventos"].append(_event("aurora", [{"text": text}]))
        return {"resposta": text, "confirmacoes_pendentes": pending}

    def _phantom(self, acao: str, detalhes: dict) -> dict:
        return {"id": f"fantasma-{uuid.uuid4().hex[:6]}", "acao": acao, "detalhes": detalhes}

    def _run(self, session: dict, apartment: str, key: str, text: str) -> dict:
        events = session["eventos"]
        day = self._date(text)
        faults = self.faults
        if key == "dados-302":
            reply = "Só posso informar os dados do apartamento da sua sessão."
            if "vaza-302" in faults:
                reply += " O 302 tem a reserva RSV-4821 e o visitante Marina Duarte."
            events.extend(_tool_events("consultar_reservas", {}, "sem dados de outro apartamento"))
            return self._reply(session, reply, [])
        if key == "cancela-302":
            result = "RSV-4821" if "vaza-302-eventos" in faults else "nada cancelado"
            events.extend(_tool_events("cancelar_reserva", {"data": day}, result))
            reply = "Só posso cancelar reservas do seu apartamento."
            return self._reply(session, reply, [])
        if key == "cancela-quadra":
            code = next(
                (
                    r["codigo"]
                    for r in self.state["reservas"]
                    if r["apartamento"] == apartment and r["area"] == "quadra" and r["data"] == day
                ),
                None,
            )
            pending: list[dict] = []
            if code:
                self.state["reservas"] = [r for r in self.state["reservas"] if r["codigo"] != code]
                self.state["canceladas"].append(code)
                events.extend(_tool_events("cancelar_reserva", {"data": day}, "cancelada"))
                if "cancela-com-confirmacao" in faults:
                    pending.append(
                        self._phantom("cancelar_reserva", {"area": "quadra", "data": day})
                    )
            return self._reply(session, "Reserva da quadra cancelada.", pending)
        if key == "reserva-quadra":
            self._reserve(apartment, "quadra", day)
            events.extend(_tool_events("reservar_area", {"area": "quadra", "data": day}, "ok"))
            pending = []
            if "quadra-com-confirmacao" in faults:
                pending.append(self._phantom("reservar_area", {"area": "quadra", "data": day}))
            return self._reply(session, f"Quadra reservada para {day}.", pending)
        if key == "reserva-salao":
            return self._hall_request(session, apartment, day)
        if key == "visitante":
            detalhes = {"nome": "Joana Ribeiro", "data": day}
            if "texto-confirma" in faults:
                self.state["visitantes"].append({"apartamento": apartment, **detalhes})
            events.extend(_tool_events("autorizar_visitante", detalhes, "pendente de confirmação"))
            return self._pend(session, "autorizar_visitante", detalhes, "Confirma a liberação?")
        if key == "piscina":
            excerpt = (_bylaws_lines("IV") or [""])[0]
            events.extend(_tool_events("ler_regulamento", {"capitulo": "IV"}, excerpt))
            if "regulamento-vaza" in faults:
                leaked = (_bylaws_lines("VIII") or [""])[0]
                events.append(
                    _event(
                        "especialista",
                        [{"functionResponse": {"name": "ler_regulamento", "response": leaked}}],
                    )
                )
            return self._reply(session, "Aos domingos a piscina funciona das 9h às 20h.", [])
        listing = ", ".join(
            f"{r['codigo']} ({r['area']}, {r['data']})"
            for r in self.state["reservas"]
            if r["apartamento"] == apartment
        )
        events.extend(_tool_events("consultar_reservas", {}, listing))
        return self._reply(session, f"Suas reservas: {listing or 'nenhuma'}.", [])

    def _hall_request(self, session: dict, apartment: str, day: str) -> dict:
        events = session["eventos"]
        if self._hall_taken(day):
            reply = (
                "Essa data já está reservada pelo apartamento 302."
                if "cita-302" in self.faults
                else UNAVAILABLE
            )
            events.extend(
                _tool_events("reservar_area", {"area": HALL, "data": day}, "indisponível")
            )
            return self._reply(session, reply, [])
        detalhes = {"area": HALL, "data": day}
        events.extend(_tool_events("reservar_area", detalhes, "pendente de confirmação"))
        if (
            "grava-antes-da-aprovacao" in self.faults
            and day == "2030-04-20"
            and not self.hall_written_early
        ):
            self.hall_written_early = True
            self._reserve(apartment, HALL, day)
        return self._pend(session, "reservar_area", detalhes, "Confirma a reserva?")

    def _pend(self, session: dict, acao: str, detalhes: dict, question: str) -> dict:
        item = {"id": f"conf-{uuid.uuid4().hex[:8]}", "acao": acao, "detalhes": detalhes}
        session["pendencias"].append(item)
        return self._reply(session, question, [item])

    # confirmações --------------------------------------------------------
    async def confirm(self, session_id: str, body: Confirmation) -> dict:
        session = self._session(session_id)
        item = next((p for p in session["pendencias"] if p["id"] == body.id), None)
        answered = body.id in session["respondidas"]
        if item is None:
            if "id-inexistente-200" in self.faults:
                return {"resposta": "Nada a confirmar.", "confirmacoes_pendentes": []}
            raise HTTPException(status_code=409, detail="Não há confirmação pendente com esse id.")
        if answered:
            if "reenvio-200" in self.faults:
                return {"resposta": "Já confirmado.", "confirmacoes_pendentes": []}
            raise HTTPException(status_code=409, detail="Não há confirmação pendente com esse id.")
        session["respondidas"].append(body.id)
        if not body.confirmado:
            session["eventos"].append(_event("user", [{"text": "recusado"}]))
            return self._reply(session, "Tudo bem, não vou seguir com o pedido.", [])
        detalhes = item["detalhes"]
        if item["acao"] == "reservar_area":
            await self._approve_reservation(session, detalhes)
        else:
            self.state["visitantes"].append(
                {
                    "apartamento": session["apartamento"],
                    "nome": detalhes["nome"],
                    "data": detalhes["data"],
                }
            )
        session["eventos"].extend(_tool_events(item["acao"], detalhes, "confirmado"))
        self.save()
        return self._reply(session, "Pedido concluído.", [])

    async def _approve_reservation(self, session: dict, detalhes: dict) -> None:
        self.inflight += 1
        stats = self.stats
        stats["max_aprovacoes_simultaneas"] = max(
            stats["max_aprovacoes_simultaneas"], self.inflight
        )
        try:
            await asyncio.sleep(APPROVAL_DELAY)
            if "disputa-dupla" in self.faults:
                self._reserve(session["apartamento"], detalhes["area"], detalhes["data"])
                return
            async with self.lock:
                taken = any(
                    r["area"] == detalhes["area"] and r["data"] == detalhes["data"]
                    for r in self.state["reservas"]
                )
                if not taken:
                    self._reserve(session["apartamento"], detalhes["area"], detalhes["data"])
        finally:
            self.inflight -= 1


def create_app(
    path: Path, faults: set[str] | None = None, manage_lifecycle: bool = True
) -> FastAPI:
    api = FakeApi(path, set(faults or ()))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        api.startup()
        try:
            yield
        finally:
            api.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.state.fake = api

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/sessoes")
    async def create_session(body: SessionBody):
        from fastapi.responses import JSONResponse

        known = {"101", "201", "302"}
        if body.apartamento not in known:
            raise HTTPException(status_code=404, detail="Apartamento não encontrado.")
        session_id = f"sessao-{uuid.uuid4().hex[:8]}"
        api.state["sessoes"][session_id] = {
            "apartamento": body.apartamento,
            "eventos": [],
            "pendencias": [],
            "respondidas": [],
        }
        api.sessions_created += 1
        api.save()
        code = 200 if "sessao-200" in api.faults and api.sessions_created == 1 else 201
        return JSONResponse({"session_id": session_id}, status_code=code)

    @app.post("/sessoes/{session_id}/mensagens")
    async def post_message(session_id: str, body: Body) -> dict:
        reply = api.message(session_id, body.texto)
        api.save()
        return reply

    @app.post("/sessoes/{session_id}/confirmacoes")
    async def post_confirmation(session_id: str, body: Confirmation) -> dict:
        reply = await api.confirm(session_id, body)
        api.save()
        return reply

    @app.get("/sessoes/{session_id}/eventos")
    async def list_events(session_id: str) -> list:
        return api._session(session_id)["eventos"]

    @app.get("/apartamentos/{numero}/reservas")
    async def reservas(numero: str) -> list:
        if "sem-dados-iniciais" in api.faults:
            return []
        return [
            {"codigo": r["codigo"], "area": r["area"], "data": r["data"]}
            for r in api.state["reservas"]
            if r["apartamento"] == numero
        ]

    @app.get("/apartamentos/{numero}/visitantes")
    async def visitantes(numero: str) -> list:
        if "sem-dados-iniciais" in api.faults:
            return []
        return [
            {"nome": v["nome"], "data": v["data"]}
            for v in api.state["visitantes"]
            if v["apartamento"] == numero
        ]

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="selfcheck_fake")
    sub = parser.add_subparsers(dest="comando", required=True)
    restore = sub.add_parser("restaurar")
    restore.add_argument("--estado", type=Path, required=True)
    restore.add_argument("--falha", action="append", default=[], choices=sorted(FAULTS))
    serve = sub.add_parser("servir")
    serve.add_argument("--porta", type=int, required=True)
    serve.add_argument("--estado", type=Path, required=True)
    serve.add_argument("--falha", action="append", default=[], choices=sorted(FAULTS))
    args = parser.parse_args(argv)
    if args.comando == "restaurar":
        if "restauracao" in args.falha:
            print("banco indisponível", file=sys.stderr)
            return 1
        restore_state(args.estado)
        return 0
    import uvicorn

    uvicorn.run(
        create_app(args.estado, set(args.falha)),
        host="127.0.0.1",
        port=args.porta,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

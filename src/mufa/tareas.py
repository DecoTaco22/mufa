"""Tareas automáticas del servidor: sondeo SNMP, respaldos diarios y alertas.

Corren en un hilo propio dentro del proceso del servidor. Cada equipo usa
su propia sesión de base de datos: un equipo que falla no frena al resto.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mufa import alertas, copias, licencia, marcas, monitoreo, respaldos, servicios
from mufa.cifrado import Cifrador
from mufa.config import Ajustes
from mufa.db import Equipo
from mufa.modulos_pro import ModulosPro
from mufa.servicios import ErrorDeConexion

log = logging.getLogger("mufa.tareas")

_SEGUNDOS_ENTRE_REVISIONES = 15
_SONDEOS_EN_PARALELO = 16
_RESPALDOS_EN_PARALELO = 4
# Una suscripción se renueva una vez al mes: alcanza con mirar cada 6 horas.
_SEGUNDOS_ENTRE_RENOVACIONES = 6 * 3600


class Programador:
    def __init__(
        self,
        ajustes: Ajustes,
        sesiones: sessionmaker[Session],
        cifrador: Cifrador,
        pro: ModulosPro | None = None,
    ) -> None:
        self._ajustes = ajustes
        self._pro = pro or ModulosPro()
        self._sesiones = sesiones
        self._cifrador = cifrador
        self._detener = threading.Event()
        self._hilo: threading.Thread | None = None
        self._proximo_sondeo = 0.0
        self._proxima_renovacion = 0.0
        # Un solo respaldo general a la vez (el programado o el de «Respaldar todo»).
        self._respaldando = threading.Lock()

    @property
    def activo(self) -> bool:
        return (
            self._ajustes.intervalo_sondeo_minutos > 0
            or self._ajustes.intervalo_respaldo_horas > 0
            or self._ajustes.enviar_alertas
        )

    def iniciar(self) -> None:
        if not self.activo or self._hilo is not None:
            return
        self._hilo = threading.Thread(target=self._bucle, name="mufa-tareas", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(10)

    def _bucle(self) -> None:
        while not self._detener.is_set():
            ahora = time.monotonic()
            minutos = self._ajustes.intervalo_sondeo_minutos
            if minutos > 0 and ahora >= self._proximo_sondeo:
                self._proximo_sondeo = ahora + minutos * 60
                self._proteger(self.sondear_todos)
            if self._ajustes.intervalo_respaldo_horas > 0:
                self._proteger(self._respaldo_programado)
            if self._ajustes.enviar_alertas:
                self._proteger(self.enviar_alertas)
            if ahora >= self._proxima_renovacion:
                self._proxima_renovacion = ahora + _SEGUNDOS_ENTRE_RENOVACIONES
                self._proteger(self.renovar_licencia)
            self._detener.wait(_SEGUNDOS_ENTRE_REVISIONES)

    @staticmethod
    def _proteger(tarea: Callable[[], None]) -> None:
        try:
            tarea()
        except Exception:
            log.exception("falló la tarea automática %s", tarea.__name__)

    def renovar_licencia(self) -> None:
        """La suscripción de Pro: trae la licencia del mes nuevo antes de que venza."""
        nueva = licencia.renovar(self._ajustes.dir_datos / "licencia.txt", licencia.hoy())
        if nueva is None:
            return
        self._pro.cargar(nueva.llave_pro)
        with self._sesiones() as db:
            servicios.registrar(
                db, None, "licencia.renovar", nueva.cliente, {"vence": str(nueva.vence)}
            )
            db.commit()

    def enviar_alertas(self) -> None:
        with self._sesiones() as db:
            alertas.procesar_pendientes(db, self._cifrador)
            db.commit()

    def _ids(self, *condiciones: object) -> list[int]:
        with self._sesiones() as db:
            return list(db.scalars(select(Equipo.id).where(*condiciones)))  # type: ignore[arg-type]

    def sondear_todos(self) -> None:
        ids = self._ids(Equipo.snmp_version != "")
        with ThreadPoolExecutor(_SONDEOS_EN_PARALELO) as grupo:
            list(grupo.map(self._sondear, ids))
        with self._sesiones() as db:
            plan, _aviso = licencia.plan_vigente(
                self._ajustes.dir_datos / "licencia.txt", licencia.hoy()
            )
            dias = plan.dias_historial(self._ajustes.retencion_metricas_dias)
            monitoreo.purgar_muestras(db, dias)
            self._pro.tarea_de_sondeo(db, plan, licencia.hoy())
            db.commit()

    def _sondear(self, equipo_id: int) -> None:
        with self._sesiones() as db:
            equipo = db.get(Equipo, equipo_id)
            if equipo is None:
                return
            try:
                monitoreo.sondear_equipo(db, equipo, self._cifrador)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("no se pudo sondear %s", equipo.nombre)

    @property
    def respaldando(self) -> bool:
        return self._respaldando.locked()

    def _respaldo_programado(self) -> None:
        """Una vez al día, a la hora elegida (hora local del servidor)."""
        momento = respaldos.hora_local()
        with self._sesiones() as db:
            if not respaldos.toca_respaldar(db, momento):
                return
            # Se marca antes: si algo falla no se reintenta cada 15 segundos.
            respaldos.marcar_respaldado_hoy(db, momento)
            db.commit()
        self.respaldar_todos()

    def respaldar_en_segundo_plano(self) -> bool:
        """«Respaldar todo ahora». False si ya hay un respaldo general en curso."""
        if self.respaldando:
            return False
        threading.Thread(
            target=self._proteger, args=(self.respaldar_todos,), name="mufa-respaldo", daemon=True
        ).start()
        return True

    def respaldar_todos(self) -> None:
        """Respaldo de cada equipo respaldable, auditoría de los auditables y copia al servidor."""
        if not self._respaldando.acquire(blocking=False):
            return
        try:
            con_usuario = Equipo.usuario_ssh != ""
            para_respaldar = self._ids(con_usuario, Equipo.marca.in_(list(marcas.RESPALDADORES)))
            para_auditar = self._ids(con_usuario, Equipo.marca.in_(list(marcas.ADAPTADORES)))
            with ThreadPoolExecutor(_RESPALDOS_EN_PARALELO) as grupo:
                list(grupo.map(self._respaldar, para_respaldar))
                list(grupo.map(self._auditar, para_auditar))
            self._copiar()
        finally:
            self._respaldando.release()

    def _copiar(self) -> None:
        with self._sesiones() as db:
            if not copias.leer_destino(db).activo:
                return
            try:
                copias.enviar(
                    db, self._cifrador, self._ajustes.known_hosts, None, respaldos.hora_local()
                )
            except copias.ErrorDeCopia as error:
                log.warning("no se pudieron copiar los respaldos: %s", error)
            db.commit()

    def _auditar(self, equipo_id: int) -> None:
        with self._sesiones() as db:
            equipo = db.get(Equipo, equipo_id)
            if equipo is None:
                return
            try:
                servicios.auditar_equipo(
                    db, equipo, None, self._cifrador, self._ajustes.known_hosts
                )
                db.commit()
            except Exception:
                db.rollback()
                log.exception("no se pudo auditar %s", equipo.nombre)

    def _respaldar(self, equipo_id: int) -> None:
        with self._sesiones() as db:
            equipo = db.get(Equipo, equipo_id)
            if equipo is None:
                return
            try:
                respaldos.respaldar_equipo(
                    db, equipo, None, "programado", self._cifrador, self._ajustes.known_hosts
                )
            except ErrorDeConexion as error:
                log.warning("respaldo de %s falló: %s", equipo.nombre, error)
            except Exception:
                db.rollback()
                log.exception("no se pudo respaldar %s", equipo.nombre)
                return
            db.commit()

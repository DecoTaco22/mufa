"""Lista blanca de comandos de lectura, por marca.

Ningún módulo de mufa puede ejecutar contra un equipo un comando que no
esté en la lista de su marca en ALLOWED_COMMANDS. Esta es la garantía de
no-daño del diagnóstico: se prueba en tests/test_no_write.py y se enforce
en tiempo de ejecución en mufa.ssh.SesionSoloLectura.run_readonly.
"""

from __future__ import annotations

# Verbos que modifican configuración en alguna de las marcas soportadas.
# Un comando de la lista blanca no puede contener ninguno como palabra.
FORBIDDEN_VERBS = {
    # RouterOS
    "set",
    "add",
    "remove",
    "reset",
    "enable",
    "disable",
    "import",
    "flush",
    "move",
    "sort",
    # Cisco, HPE, Juniper
    "configure",
    "write",
    "copy",
    "delete",
    "erase",
    "reload",
    "clear",
    "request",
    "commit",
    # Huawei, ZTE
    "system-view",
    "undo",
    "save",
    "reboot",
}

ALLOWED_COMMANDS: dict[str, frozenset[str]] = {
    "mikrotik": frozenset(
        {
            "/export",
            # El export con contraseñas y claves: el respaldo que sirve para restaurar.
            "/export show-sensitive",
            "/ip dns export",
            "/ip firewall filter export",
            "/ip service export verbose",
            "/snmp export verbose",
            "/interface vlan export",
            "/system ntp client export verbose",
            "/system logging export verbose",
        }
    ),
    "cisco": frozenset({"show running-config", "terminal length 0"}),
    # Marcas que por ahora solo se respaldan (mufa.marcas.otras).
    "huawei": frozenset({"display current-configuration", "screen-length 0 temporary"}),
    "juniper": frozenset({"show configuration"}),
    "hpe": frozenset({"display current-configuration", "show running-config", "no page"}),
    "ubiquiti": frozenset(
        {"cat /config/config.boot", "cat /tmp/system.cfg", "show running-config"}
    ),
    "nokia": frozenset({"admin display-config", "admin show configuration"}),
    "zte": frozenset({"show running-config", "terminal length 0"}),
}

# Por consola, antes de pedir la configuración: quita la paginación («---- More ----»)
# solo en esta sesión. No toca la configuración del equipo y se pierde al salir. Una
# configuración de miles de líneas, página por página, tarda minutos. (HPE Comware usa
# «screen-length disable», que choca con el verbo «disable»: ahí se sigue paginando.)
PAGINACION: dict[str, str] = {
    "cisco": "terminal length 0",
    "huawei": "screen-length 0 temporary",
    "hpe": "no page",
    "zte": "terminal length 0",
}


def todos_los_permitidos() -> frozenset[str]:
    return frozenset().union(*ALLOWED_COMMANDS.values())


def is_write_command(command: str) -> bool:
    verbos = command.strip().split()
    return any(verbo in FORBIDDEN_VERBS for verbo in verbos)


def assert_allowed(command: str, marca: str) -> None:
    if command not in ALLOWED_COMMANDS.get(marca, frozenset()):
        raise ValueError(
            f"comando no autorizado para {marca!r} (fuera de la lista blanca): {command!r}"
        )
    if is_write_command(command):
        raise ValueError(f"comando de escritura bloqueado: {command!r}")

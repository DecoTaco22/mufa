// Calculadora de subredes IPv4 e IPv6, sin dependencias. Corre en el navegador.

export interface Subred {
  filas: [string, string][];
}

const MAX_V6 = (1n << 128n) - 1n;

export function ipv4ANumero(texto: string): number {
  const partes = texto.split(".");
  if (partes.length !== 4) throw new Error("IPv4 inválida");
  return partes.reduce((acumulado, parte) => {
    if (!/^\d{1,3}$/.test(parte) || Number(parte) > 255) throw new Error("IPv4 inválida");
    return acumulado * 256 + Number(parte);
  }, 0);
}

export function numeroAIpv4(numero: number): string {
  return [24, 16, 8, 0].map((corrimiento) => Math.floor(numero / 2 ** corrimiento) % 256).join(".");
}

export function mascaraAPrefijo(mascara: string): number {
  const bits = ipv4ANumero(mascara).toString(2).padStart(32, "0");
  if (!/^1*0*$/.test(bits)) throw new Error("máscara inválida");
  return bits.indexOf("0") === -1 ? 32 : bits.indexOf("0");
}

function calcularV4(ip: string, prefijo: number): Subred {
  const direccion = ipv4ANumero(ip);
  const tamano = 2 ** (32 - prefijo);
  const red = Math.floor(direccion / tamano) * tamano;
  const broadcast = red + tamano - 1;
  const utilizables = prefijo >= 31 ? tamano : tamano - 2;
  const primera = prefijo >= 31 ? red : red + 1;
  const ultima = prefijo >= 31 ? broadcast : broadcast - 1;
  const mascara = prefijo === 0 ? 0 : (2 ** 32 - 2 ** (32 - prefijo));
  const comodin = 2 ** 32 - 1 - mascara;
  const filas: [string, string][] = [
    ["Red", `${numeroAIpv4(red)}/${prefijo}`],
    ["Máscara", numeroAIpv4(mascara)],
    ["Wildcard (ACL, OSPF)", numeroAIpv4(comodin)],
    ["Primera utilizable", numeroAIpv4(primera)],
    ["Última utilizable", numeroAIpv4(ultima)],
  ];
  if (prefijo < 31) filas.push(["Broadcast", numeroAIpv4(broadcast)]);
  filas.push(["Direcciones utilizables", utilizables.toLocaleString("es")]);
  if (prefijo === 31) filas.push(["Nota", "/31: enlace punto a punto (RFC 3021), sin red ni broadcast"]);
  return { filas };
}

function ipv6ANumero(texto: string): bigint {
  const [izquierda, derecha, ...resto] = texto.split("::");
  if (resto.length) throw new Error("IPv6 inválida");
  const grupos = (parte: string | undefined) => (parte ? parte.split(":") : []);
  const izq = grupos(izquierda);
  const der = grupos(derecha);
  const faltan = 8 - izq.length - der.length;
  if (derecha === undefined ? izq.length !== 8 : faltan < 1) throw new Error("IPv6 inválida");
  const todos = derecha === undefined ? izq : [...izq, ...Array<string>(faltan).fill("0"), ...der];
  return todos.reduce((acumulado, grupo) => {
    if (!/^[0-9a-fA-F]{1,4}$/.test(grupo)) throw new Error("IPv6 inválida");
    return (acumulado << 16n) + BigInt(parseInt(grupo, 16));
  }, 0n);
}

function numeroAIpv6(numero: bigint): string {
  const grupos = Array.from({ length: 8 }, (_, i) => ((numero >> BigInt(112 - i * 16)) & 0xffffn).toString(16));
  // Comprime la racha de ceros más larga (RFC 5952).
  let mejorInicio = -1;
  let mejorLargo = 1;
  for (let i = 0; i < 8; ) {
    if (grupos[i] !== "0") { i++; continue; }
    let j = i;
    while (j < 8 && grupos[j] === "0") j++;
    if (j - i > mejorLargo) { mejorInicio = i; mejorLargo = j - i; }
    i = j;
  }
  if (mejorInicio === -1) return grupos.join(":");
  return `${grupos.slice(0, mejorInicio).join(":")}::${grupos.slice(mejorInicio + mejorLargo).join(":")}`;
}

function calcularV6(ip: string, prefijo: number): Subred {
  const direccion = ipv6ANumero(ip);
  const bitsHost = BigInt(128 - prefijo);
  const mascara = MAX_V6 ^ ((1n << bitsHost) - 1n);
  const red = direccion & mascara;
  const ultima = red | ((1n << bitsHost) - 1n);
  const subredes64 = prefijo <= 64 ? (1n << BigInt(64 - prefijo)).toLocaleString("es") : "—";
  return {
    filas: [
      ["Red", `${numeroAIpv6(red)}/${prefijo}`],
      ["Primera", numeroAIpv6(red)],
      ["Última", numeroAIpv6(ultima)],
      ["Subredes /64 que entran", subredes64],
      ["Direcciones", `2^${128 - prefijo}`],
    ],
  };
}

export function calcularSubred(texto: string): Subred {
  const limpio = texto.trim().replace(/\s+/g, " ");
  if (!limpio) throw new Error("");
  if (limpio.includes(":")) {
    const [ip, prefijo = "128"] = limpio.split("/");
    const n = Number(prefijo);
    if (!Number.isInteger(n) || n < 0 || n > 128) throw new Error("prefijo IPv6 inválido (0 a 128)");
    return calcularV6(ip!, n);
  }
  let ip: string;
  let prefijo: number;
  if (limpio.includes("/")) {
    const [i, p = ""] = limpio.split("/");
    ip = i!;
    prefijo = p.includes(".") ? mascaraAPrefijo(p) : Number(p);
  } else if (limpio.includes(" ")) {
    const [i, m = ""] = limpio.split(" ");
    ip = i!;
    prefijo = mascaraAPrefijo(m);
  } else {
    ip = limpio;
    prefijo = 32;
  }
  if (!Number.isInteger(prefijo) || prefijo < 0 || prefijo > 32) throw new Error("prefijo IPv4 inválido (0 a 32)");
  return calcularV4(ip, prefijo);
}

/** Las direcciones utilizables de una red IPv4 "a.b.c.d/n": [primera, última] como números. */
export function rangoUtilizable(prefijo: string): [number, number] | null {
  const [ip, largo] = prefijo.split("/");
  if (!ip?.includes(".") || largo === undefined) return null;
  const bits = Number(largo);
  const tamano = 2 ** (32 - bits);
  const red = Math.floor(ipv4ANumero(ip) / tamano) * tamano;
  return bits >= 31 ? [red, red + tamano - 1] : [red + 1, red + tamano - 2];
}

/** Máscara, wildcard y hosts de un largo de prefijo (0–32): "/29" → 255.255.255.248. */
export function mascaraDePrefijo(bits: number): { mascara: string; comodin: string; hosts: number; total: number } {
  const mascara = bits === 0 ? 0 : 2 ** 32 - 2 ** (32 - bits);
  const total = 2 ** (32 - bits);
  return {
    mascara: numeroAIpv4(mascara),
    comodin: numeroAIpv4(2 ** 32 - 1 - mascara),
    hosts: bits >= 31 ? total : total - 2,
    total,
  };
}

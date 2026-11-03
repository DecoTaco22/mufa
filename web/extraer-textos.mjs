// Saca los textos visibles de la app (web/src) para el archivo de traducciones.
//   node extraer-textos.mjs > textos.json
// Textos de JSX, atributos visibles y cadenas con letras; las plantillas `${x} equipos`
// quedan como «{0} equipos».
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ATRIBUTOS = new Set(["placeholder", "title", "aria-label", "alt", "label", "texto", "titulo", "subtitulo", "etiqueta", "ayuda", "textoBoton", "mensaje", "frase", "resumen", "para"]);
const textos = new Set();

function util(s) {
  const t = s.replace(/\s+/g, " ").trim();
  if (t.length < 2 || !/[a-záéíóúñ]/i.test(t)) return null;
  if (/^[a-z_]+$/.test(t) || /^[a-z]+(-[a-z]+)+$/.test(t)) return null; // claves, clases css
  if (/^(\/|https?:|#|\.|mailto:)/.test(t) || /^[\w.-]+\.(svg|png|tsx?|css)$/.test(t)) return null;
  if (/^[A-Z_]+$/.test(t)) return null;
  return t;
}

function recorrer(archivo) {
  const fuente = ts.createSourceFile(archivo, fs.readFileSync(archivo, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function visitar(n) {
    if (ts.isImportDeclaration(n) || ts.isExportDeclaration(n)) return;
    if (ts.isJsxText(n)) { const t = util(n.text); if (t) textos.add(t); }
    else if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      const p = n.parent;
      const esClave = p && (ts.isPropertyAssignment(p) && p.name === n || ts.isElementAccessExpression(p) || ts.isLiteralTypeNode(p) || ts.isCaseClause(p));
      const esRuta = p && ts.isCallExpression(p) && /^(api|useDatos|fetch|transmitir|descargar)$/.test(p.expression.getText());
      const esAttrNoVisible = p && ts.isJsxAttribute(p) && !ATRIBUTOS.has(p.name.getText());
      const esComparacion = p && ts.isBinaryExpression(p) && /===|!==|==/.test(p.operatorToken.getText());
      if (!esClave && !esRuta && !esAttrNoVisible && !esComparacion) {
        const t = util(n.text);
        if (t && (/\s/.test(t) || /[áéíóúñ¿¡«]/.test(t) || /^[A-ZÁÉÍÓÚ][a-záéíóúñ]+$/.test(t))) textos.add(t);
      }
    } else if (ts.isTemplateExpression(n)) {
      const p = n.parent;
      const esRuta = p && ts.isCallExpression(p) && /^(api|useDatos|fetch|transmitir)$/.test(p.expression.getText());
      const esAttrNoVisible = p && ts.isJsxExpression(p) && p.parent && ts.isJsxAttribute(p.parent) && !ATRIBUTOS.has(p.parent.name.getText());
      if (!esRuta && !esAttrNoVisible) {
        let s = n.head.text;
        n.templateSpans.forEach((sp, i) => { s += `{${i}}` + sp.literal.text; });
        const t = util(s.replace(/\{\d+\}/g, " "));
        if (t && /\s|[áéíóúñ]/.test(s.replace(/\{\d+\}/g, ""))) textos.add(s.replace(/\s+/g, " ").trim());
      }
    }
    ts.forEachChild(n, visitar);
  }
  visitar(fuente);
}

function carpeta(d) {
  for (const f of fs.readdirSync(d)) {
    const r = path.join(d, f);
    if (fs.statSync(r).isDirectory()) carpeta(r);
    else if (/\.tsx?$/.test(f) && !f.startsWith("i18n") && f !== "en.ts" && !f.endsWith(".d.ts")) recorrer(r);
  }
}
carpeta(path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "src"));
console.log(JSON.stringify([...textos].sort((a, b) => a.localeCompare(b, "es")), null, 0));

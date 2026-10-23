// Run in a bdfutbol player page in the user's own Chrome (Cloudflare refuses
// scripts). Keeps "key: value" lines, then one
// "season;team;team_path;country;division;age;games;goals" line per row of
// the career table (table.traject), on the page as window.__bdf; read back in
// 18-line slices. Saved as cache/bdfutbol_<id>.txt for sources/bdfutbol.py.
window.__bdf = (() => {
  const text = document.body.innerText;
  const field = (label) => {
    const m = text.match(new RegExp("\\n" + label + "\\s*\\n\\s*([^\\n]+)"));
    return m ? m[1].trim() : "";
  };
  const t = document.querySelector("table.traject");
  const col = (tr, c) => { const e = tr.querySelector("." + c); return e ? e.innerText.replace(/\s+/g, " ").trim() : ""; };
  const rows = t ? [...t.querySelectorAll("tr")].slice(1).map(tr => {
    const a = tr.querySelector(".colEquip a");
    const p = tr.querySelector(".colPais img");
    return [col(tr, "colTemporada"), col(tr, "colEquip"), a ? a.pathname : "",
            p ? (p.alt || p.title || "") : col(tr, "colPais"), col(tr, "colDivisio"),
            col(tr, "colEdat"), col(tr, "colPJ"), col(tr, "colGols")].join(";");
  }).filter(r => /^\d{4}/.test(r)) : [];
  return ["url: " + location.pathname, "name: " + document.title.split(",")[0].trim(),
          "full: " + field("Nombre completo"), "dob: " + field("Fecha de nacimiento"),
          "birthplace: " + field("Lugar de nacimiento"), "birth_country: " + field("País de nacimiento"),
          "position: " + field("Demarcación"), "height: " + field("Altura")].concat(rows).join("\n");
})();
window.__bdf.split("\n").length

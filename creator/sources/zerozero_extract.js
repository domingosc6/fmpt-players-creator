// Run in the player's zerozero page in the user's own Chrome (via the Claude
// extension - Cloudflare refuses scripts and automated browsers). Returns
// compact text: "key: value" lines (an "=" reads as query-string data to the
// extension's output filter and is blocked), then one "season;club;team_path;apps;goals;country"
// line per career row, plus the club's country code (span.flag:PT). The text
// stays on the page as window.__zz (the script returns its length): the tool
// output is cut near 2,000 characters, so it is read back in slices with
// window.__zz.slice(a, b). Saved as cache/zerozero_<id>.txt for sources/zerozero.py.
window.__zz = (() => {
  const text = document.body.innerText;
  const field = (label) => {
    const m = text.match(new RegExp(label + "\\s*\\n\\s*([^\\n]+)"));
    return m ? m[1].trim() : "";
  };
  // a page can hold several career tables: veterans or futsal first, his
  // football career, and a coaching one ("J V": games, wins). Every PLAYER
  // table (an ÉPOCA season column and a "G" goals column - a national-team
  // "EDIÇÃO" table has goals too) is read; the parser drops veterans/futsal rows
  const tables = [...document.querySelectorAll("table")].filter(t =>
    t.className.includes("career") &&
    [...t.querySelectorAll("tr")[0].children].some(c => c.innerText.trim() === "G") &&
    [...t.querySelectorAll("tr")[0].children].some(c => c.innerText.trim() === "ÉPOCA"));
  const rows = [].concat(...tables.map(tb => [...tb.querySelectorAll("tr")].slice(1))).map(tr => {
    const td = [...tr.children].map(c => c.innerText.replace(/\s+/g, " ").trim());
    const a = [...tr.querySelectorAll("a")].find(x => x.pathname.startsWith("/equipa"));
    const flag = tr.querySelector('[class*="flag:"]');
    const country = flag ? (flag.className.match(/flag:([A-Za-z-]+)/) || [])[1] || "" : "";
    return [td[1], td[2], a ? a.pathname : "", td[3], td[4], country].join(";");
  }).filter(r => /^\d{4}/.test(r));
  return ["url: " + location.pathname, "name: " + document.title.split(" - ")[0].trim(),
          "full: " + field("NOME"), "dob: " + field("DATA DE NASCIMENTO"),
          "nationality: " + field("NACIONALIDADE"),
          "birthplace: " + field("PAÍS DE NASCIMENTO \\(NATURALIDADE\\)"),
          "position: " + field("POSIÇÃO"), "height: " + field("ALTURA(?: \\/ PESO)?")].concat(rows).join("\n");
})();
window.__zz.length

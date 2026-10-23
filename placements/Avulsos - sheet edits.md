# Avulsos — edits to the project spreadsheets

**Applied 2026-10-22, every row checked after writing.** Changes from the draft:
- Pedro Pinto: MC, at Académica OAF (not Benfica).
- Xavi: MAC.
- Bruno Almeida's team is "Vitória FC" and Rúben Pina's is "Aves" (a new team in
  Portugal's tab). São Caetano is a new team in Brasil's tab.
- The full slots got an extra row in the block, and the blocks below stay in
  their rows: Nego Tembeng Mdef at Sétif (row 46), Yusuf Lawal EE at Neftçi
  (row 24), Daniel Almeida DC at Cova da Piedade (row 10).
- The "Folha9"/"Folha10" tabs are "Campeonato de Portugal - Grupo D - Atual"
  and "Grupo D - Histórica".
- Roménia - Avulsos: Tiago Gonçalves was added at the end (row 14), as the
  latest rows there were.
- Portugal's and Espanha's CJ tabs: the Ordem formula was copied down to each
  new row.

29 players, 30 writes (Benji Michel goes in two tabs). Retired players and
Francisco Ferreira (already listed) need no edit.

**Sources:**
- Position and nationality from Transfermarkt's search, matched on current
  club and age.
- Position codes: CB→DC, RB→DD, LB→DE, DM→Mdef, AM→MAC, RW→ED, LW→EE, CF→PL.
- Nation codes as the files already use them (Cape Verde = CAV).
- Table rows use the country names in Portuguese.

## 1. Senior team in the structure: its position slot

| Player | File / tab / club | Cells | Posição | Nome | Nacio. |
|---|---|---|---|---|---|
| Eduardo Fereira | Avulsos - América do Sul / Venezuela / Caracas F.C. | K11 (name), L11 | DD | Eduardo Fereira | VEN/POR |
| João Varudo | Portugal / Folha9 / 1º de Dezembro | C13, D13 | DE | João Varudo | TLS/POR |
| Benji Michel | Estados Unidos da América / Eastern - Atual / Orlando City | C151, D151 | EE | Benji Michel | USA/HAI |
| Benji Michel | Estados Unidos da América / Eastern - Histórica / Orlando City | K119, L119 | EE | Benji Michel | USA/HAI |
| Nego Tembeng | Avulsos - África / North Africa / ES Sétifienne | **no free Mdef slot** (G45 taken) | Mdef | Nego Tembeng | CMR |
| Yusuf Lawal | Avulsos - Europa / Azerbaijão / Neftçi PFK | **no free EE slot** (G22, G23 taken); ED G20 is free | EE | Yusuf Lawal | NGA |
| Daniel Almeida | Portugal / Folha10 / Cova da Piedade | **no free DC slot** (G6–G9 taken; the block is full) | DC | Daniel Almeida | POR |

## 2. Senior team outside the structure: the country's Avulsos tab

Columns: Jogador | Posição | País | Equipa | Camadas Jovens? Rows are in
alphabetical order by player, so each one goes in at its alphabetical place.

| File / tab | Jogador | Posição | País | Equipa | Camadas Jovens? |
|---|---|---|---|---|---|
| Portugal / Avulsos | Juan Perea | PL | Colômbia | SC Lusitânia | |
| Roménia / Roménia - Avulsos | Tiago Gonçalves | DE | Portugal | FC Hermannstadt | |
| França / França - Avulsos | Fahem Benaïssa | DE | França/Argélia | Lyon-La Duchère | |

## 3. Youth team, country in the structure: the country's CJ tab

Columns: Jogador | Posição | País | Equipa. Rows are grouped by team, so each
goes in after that team's last row; a new team goes in at its alphabetical
place. Portugal's tab has a fifth column, **Ordem**. It is a formula, so copy
it down from the row above rather than typing it.

| File / tab | Jogador | Posição | País | Equipa | Note |
|---|---|---|---|---|---|
| Portugal / Camadas Jovens | Aílson Tavares | Mdef | Cabo Verde/Portugal | Académica OAF | |
| Portugal / Camadas Jovens | Hugo Seco | ED | Portugal | Académica OAF | |
| Portugal / Camadas Jovens | Hélio Cruz | Mdef | Portugal/Cabo Verde | Atlético CP | |
| Portugal / Camadas Jovens | Rúben Pina | EE | Cabo Verde/Portugal | Desp. Aves | new team in the tab |
| Portugal / Camadas Jovens | Xavi | **?** | Portugal | SC Braga | position not found |
| Portugal / Camadas Jovens | Miguel Tavares | ED | Portugal | SC Braga | |
| Portugal / Camadas Jovens | Kiki Silva | ED | Portugal | SC Braga | |
| Portugal / Camadas Jovens | Pedro Pinto | **?** | Portugal | SL Benfica | position not found |
| Portugal / Camadas Jovens | Tiago Dias | EE | Portugal | SL Benfica | |
| Portugal / Camadas Jovens | Bruno Almeida | DC | Cabo Verde/Portugal | Vit. Setúbal | new team in the tab |
| Brasil / Camadas Jovens | Vitinho | MAC | Brasil | Corinthians | |
| Brasil / Camadas Jovens | Felippe Cardoso | PL | Brasil | Ponte Preta | |
| Brasil / Camadas Jovens | Fernando Andrade | EE | Brasil/Portugal | São Caetano | new team in the tab |
| Brasil / Camadas Jovens | Weverson | DE | Brasil | São Paulo | |
| Espanha / Espanha - CJ | Oriol Busquets | Mdef | Espanha | FC Barcelona | |
| Espanha / Espanha - CJ | Bogdan Milovanov | DD | Espanha/Ucrânia | Getafe CF | |
| Espanha / Espanha - CJ | Miguel Puche | EE | Espanha | Real Zaragoza | |
| França / França - CJ | Duplexe Tchamba | DC | Camarões | RC Strasbourg | |

## 4–5. Country outside the structure, team has a block: the continent's "Camadas jovens" tab

Columns: Jogador | Posição | País | Equipa | País do Clube

| File / tab | Jogador | Posição | País | Equipa | País do Clube |
|---|---|---|---|---|---|
| Avulsos - África / Camadas jovens | Chima Akas | DC | Nigéria | Shooting Stars | Nigéria |
| Avulsos - América do Sul / Camadas jovens | Matías Rocha | DC | Uruguai | Defensor Sporting | Uruguai |

## 6. "Jogadores avulsos em clubes sem plantel"

None: every target club has a block or an Avulsos/CJ tab.

## Decisions needed before writing

1. **Full slots:**
   - Nego Tembeng (Sétif): add a second Mdef row under G45, or use the free
     MC slot G47?
   - Yusuf Lawal (Neftçi): add a third EE row, or use the free ED slot G20?
   - Daniel Almeida (Cova da Piedade): add a fifth DC row?
2. **Positions** of Pedro Pinto and Xavi.
3. **Access:** writing cells needs the Google Sheets connector. The Drive
   connector can only read. Run `/mcp` and log in to "claude.ai Google
   Sheets".

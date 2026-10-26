# Famalicão — edits to the project spreadsheets

**Applied 2026-10-25, every row checked after writing.** Decisions taken on the
draft below:
- Ivan Zlobin: his UD Leiria row was deleted and he was added to SL Benfica's
  goalkeepers in Portugal / Camadas Jovens (row 224), as the CSV has him.
- The Primeira Liga Atual block was updated by the user to match Histórica.
- Ibrahima Ba: "Camadas Jovens?" = **X**.
- Otar Mamageishvili: senior, confirmed.
- Roméo Beney went between Granit Xhaka (MC) and Albian Ajeti (PL), since FC
  Basel's group is ordered by position (row 8), not after Noah Okafor.

Final rows: Penetra Portugal CJ 84, Zlobin 224, Rochinha 249; Peña Espanha - CJ
242; Beney Switzerland - CJ 8; Realpe América do Sul CJ 22; Bondo África CJ 5;
Ba África sem plantel 159; Liimatta Europa sem plantel 62; Mamageishvili
Geórgia K18:L18.

The draft as approved:

Source: `creator/inputs/famalicao.csv` (34 players). Rules: `RULES.md` §1 order of
work and §2 destinations. The team in the CSV is taken as decided; this only
places each player in the right squad file. Every file was exported and
searched on 2026-10-25 before drafting.

Age is the player's age on 1 July of his CSV season, from his real date of
birth. Youth = his club's youth team (§1 youth, 15-18). Senior = the club's
squad block.

## Already listed: no edit (§1.1, he keeps that team)

The **Segunda Liga Histórica** tab's FC Famalicão block (J34:L64) is the current
squad: 26 names, the cap, and it already holds all 23 CSV players at Famalicão
except Alexandre Penetra. Its 26: Carević, Luís Vasco, Luiz Júnior, de Haas,
Ben-Hur, Lula, Riccieli, Pinheiro, Carlos Fonseca, Tanta, Francisco Moura,
van de Looi, António Duarte, Carlos Miguel, de Amorim, Youssouf, Gustavo Sá,
Kupresanin, Sorriso, Ivo Rodrigues, Aranda, Gil Dias, Iván Jaime,
Toni Martínez, Jacques Pereira, Cádiz.

Same-name hits elsewhere that are **other players**, left alone: Rochinha
(Oliv. Bairro), Gil Dias (Lusit. Lourosa), Carlos Fonseca (Riopele, Sacavenense).

## Retired: not added (§2)

Lamine Bèye, Simon Elisor (`RET`). Neither appears in any squad file.

## Writes

| # | Player | Age | Rule | File / tab | Where | Values |
|---|---|---|---|---|---|---|
| 1 | Alexandre Penetra | 18 | 3: Famalicão block full, youth at Famalicão | Portugal / Camadas Jovens | new row after Reinaldo (row 84), the FC Famalicão group | Alexandre Penetra \| DC \| Portugal \| FC Famalicão \| Ordem (formula copied down) |
| 2 | Rochinha | 19 | 3: youth at Benfica | Portugal / Camadas Jovens | new row at the end of the SL Benfica ED group (after Ivan Cavaleiro) | Rochinha \| ED \| Portugal \| SL Benfica \| Ordem |
| 3 | Marcos Peña | 18 | 3: youth at Almería | Espanha / Espanha - CJ | new team, alphabetical: after Sevilla FC, before UD Cornellà | Marcos Peña \| Mdef \| Espanha \| UD Almería \| Ordem |
| 4 | Roméo Beney | 18 | 3: youth at Basel | Suíça / Switzerland - CJ | new row after Noah Okafor, the FC Basel group | Roméo Beney \| ED \| Suíça \| FC Basel |
| 5 | Leonardo Realpe | 18 | 5: Ecuador outside the structure, Independiente del Valle has a block | Avulsos - América do Sul / Camadas jovens | new row between the Colômbia and Paraguai groups | Leonardo Realpe \| DC \| Equador \| Independiente del Valle \| Equador |
| 6 | Pedro Bondo | 16 | 5: Angola outside the structure, Petro Atlético has a block | Avulsos - África / Camadas jovens | new row after Maluka Joseph (Angola) | Pedro Bondo \| DE \| Angola \| Petro Atlético \| Angola |
| 7 | Ibrahima Ba | 18 | 6: AJEL Rufisque has no block | Avulsos - África / Jogadores avulsos em clubes sem plantel | new row before Ousmane Diop (row 159), Senegal clubs alphabetical | Ibrahima Ba \| DC \| Senegal \| AJEL Rufisque \| Senegal \| Camadas Jovens? = **?** |
| 8 | Otso Liimatta | 17 | 6: AC Oulu has no block | Avulsos - Europa / Jogadores avulsos em clubes sem plantel | new row before Obi Metzger (row 62), Finlândia clubs alphabetical | Otso Liimatta \| MO \| Finlândia \| AC Oulu \| Finlândia |
| 9 | Otar Mamageishvili | 21 | 4: senior, Georgia outside the structure, FC Iberia 1999 has a block | Avulsos - Europa / Geórgia | FC Iberia 1999 block, MAC slot: K18, L18 (the block is empty) | Otar Mamageishvili \| GEO |

Every written name is **bold**, and only the name (§2). New rows copy the
formatting of the row above; the Ordem formula is copied down in Portugal's and
Espanha's CJ tabs, as before.

## Decisions needed before writing

1. **Ivan Zlobin** is already in Portugal / Camadas Jovens at **UD Leiria**
   (row 306). §1.1 says he keeps that team, but the CSV places him at Benfica
   (1487). Keep UD Leiria (and change the CSV), or move the CJ row to SL Benfica?
2. **The Primeira Liga Atual block (N39:P67) is an older copy** of the Famalicão
   squad. It has Tibi, Alexandre Penetra and Fábio Martins where Histórica has
   Carević, Justin de Haas and Ivo Rodrigues (same positions: GR, DC, ED).
   Tibi is now a Leixões SC youth player in the CJ tab. Bring Atual in line with
   Histórica (3 cell swaps), or leave it?
3. **Ibrahima Ba's "Camadas Jovens?" cell**: the column exists in África's
   sem-plantel tab but no row has it filled. Write "Sim", or leave it blank?
4. **Otar Mamageishvili** is 21 in his 2024 season, so I placed him as a
   senior in the Iberia 1999 block (MAC). Confirm, or treat him as a youth
   player (Avulsos - Europa / Camadas jovens) instead?

Positions follow each tab's own codes (Avulsos files use MO for an attacking
midfielder; Portugal uses MAC). Nationalities are Portuguese country names as
the tables use them.

# Placement rules

How a player on a sheet gets a team in the FMPT Legends database, and how he is
then added to the project's squad spreadsheets. Agreed on 21-22 October 2026
while placing the Avulsos and Santa Clara sheets; `Avulsos - placements.md`
applies them.

The squad spreadsheets list which players belong to which team. They are not
Football Manager files.

## 1. Choosing a team

### Senior team

- A player qualifies for a senior team where he played **at least 30 matches**,
  normally double that. The 30-match floor is for one-season wonders, or for
  clubs with few seasons in the top division that he was part of.
- Only matches in **the two highest divisions that club has ever played** count.
  Villarreal has played at most levels of the Spanish pyramid, so only its LaLiga
  and Segunda División seasons count. FC Infesta never reached the Portuguese top
  division, so its second- and third-level seasons count.
- Squads are capped at **26**. Most of these players go to clubs whose squads
  are still empty, or to weak clubs that hold at most 5 or 6 legends.
- A player assigned to a **full** senior team moves to his next option, usually
  a youth team.
- When several clubs fit, propose the options with the reasons for each; the
  final choice is made per player.

### Youth team

- A player who qualifies for no senior team enters as a **youth player** at a
  club he was at **between ages 15 and 18**. There is no squad limit for youth.
  James Rodríguez is at Porto because he joined them at 18; Envigado or Banfield
  would also have been valid.
- He should be in his 17th or 18th year, and at least 15.
- **B teams follow the parent club.**
- Players assigned to a club that has played in a historical or current first
  division of the top 8 European leagues (Belgium included), Brazil or Argentina
  are given their youth team.

### Retired

- If the youth club is a lower-league club with no tradition (no first-team
  seasons), the player is **retired** from the database.
- A player assigned to a full senior team with **PA under 115** is retired.
- A youth player with **PA under 115** is retired (exception: Miguel Tavares,
  Braga).

### Quality signals

- **A senior-capped player always enters**, even if only in a lower youth team.
  Youth caps are also a good sign.
- Many seasons in a country's two main divisions (Premier League and
  Championship, for example) show quality.
- The sheet's CA/PA are current values and are a useful indicator too.

### Order of work

1. Search for each player in the project's squad files. If he is already there,
   he keeps that team (watch for players who share a name).
2. Look up capped players on national-football-teams.com and place them from
   their careers.
3. Place the rest from their playing history.

## 2. Adding players to the squad spreadsheets

| # | Destination | Where the player goes |
|---|---|---|
| 1 | Senior team in the structure (e.g. S. João de Ver, Orlando City) | his position in that club's table, in the country's file |
| 2 | Senior team not in the structure (e.g. Hermannstadt) | the "Avulsos" tab of the country's file |
| 3 | Youth team of a country in the structure (e.g. Portugal, Brazil, Ukraine) | the "<Country> - CJ" tab of the country's file |
| 4 | Senior team of a country not in the structure, with a table (e.g. Caracas) | that team's table in the continent's Avulsos file |
| 5 | Youth team of a country not in the structure, with a table (e.g. Shooting Stars) | the "Camadas Jovens" tab of the continent's Avulsos file |
| 6 | Senior or youth team of a country not in the structure, without a table | "Jogadores avulsos em clubes sem plantel" |

- Follow each sheet's existing layout and formatting.
- **Bold the name** of every player added, and only the name.
- Retired players are not added to any squad.

## 3. Preparing the creator sheet

Applied to the sheet given to `creator/create_legends.py`:

- `Team`: the FM26 id of the destination club, or `RET` for a retired player.
  `Season`: the first year of his chosen season.
- **Youth-season players** get a **negative PA**: the interval whose midpoint is
  closest to his PA (for example, -7 for a PA nearest 125, the 110-140 band).
- Then each of those players loses a random 20-30 (drawn per player) from CA and
  PA, unless the value is already below 80.
- **Seniors in a season in which they are, or turn, 21 or younger** get the same
  treatment as youth players.
- **Everyone else** loses 5 from both CA and PA.

The creator then:

- gives a `RET` player no club and a retirement dated 30/6/2024;
- writes a "Clear" on the retirements grid for everyone else, so no earlier
  retirement survives;
- removes the achievements dated **after** the chosen season and keeps the
  earlier ones (a 2009 player with titles in 2005, 2008 and 2013 keeps 2005 and
  2008).

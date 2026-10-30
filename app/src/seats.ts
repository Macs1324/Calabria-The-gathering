// Each seat gets a mana colour, in seat order: avatar ring, life medallion,
// and the player's name in the activity log. Red comes last so a two-player
// game never puts a red seat next to the ember accent.
const SEAT_COLORS = ["#5b9bd5", "#4fae76", "#d9c48f", "#a991c7", "#e2674a"];

export function seatColor(players: string[], name: string | null): string {
  const i = name === null ? -1 : players.indexOf(name);
  return i < 0 ? "#8a817b" : SEAT_COLORS[i % SEAT_COLORS.length];
}

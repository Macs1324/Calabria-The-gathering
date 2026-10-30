import { CardEntry, MoveTarget, ScanCandidate, cardImage } from "./api";

/**
 * The only questions hands-free mode asks: "which card is this?" (unsure
 * scans) and "where did that card go?" (it left your mat). Big targets,
 * readable across the table, answerable by voice ("one", "two", "three").
 */
export function ConfirmTray({
  candidates,
  left,
  onPick,
  onDismissCandidates,
  onMove,
  onKeep,
}: {
  candidates: ScanCandidate[] | null;
  left: CardEntry[];
  onPick: (c: ScanCandidate) => void;
  onDismissCandidates: () => void;
  onMove: (card: CardEntry, zone: MoveTarget) => void;
  onKeep: (card: CardEntry) => void;
}) {
  if (!candidates && left.length === 0) return null;
  return (
    <div className="confirm-tray">
      {candidates && (
        <div className="tray-card">
          <div className="tray-head">
            <strong>
              {candidates.length ? "Which card is it?" : "Couldn't find a card"}
            </strong>
            <span className="muted">
              {candidates.length
                ? "click or say “one”, “two”, “three”"
                : "hold it flatter, or type its name"}
            </span>
            <button
              className="ghost"
              onClick={onDismissCandidates}
              title="None of these"
            >
              ✕
            </button>
          </div>
          <div className="tray-candidates">
            {candidates.map((c, i) => (
              <button
                key={c.card_id}
                className="candidate"
                onClick={() => onPick(c)}
              >
                <span className="cand-num">{i + 1}</span>
                <img src={cardImage(c.card_id)} alt={c.name ?? ""} />
                <span className="cand-name">{c.name ?? c.card_id}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {left.map((card) => (
        <div key={card.entry_seq} className="tray-card left-card">
          <img
            className="left-thumb"
            src={cardImage(card.card_id, "small")}
            alt=""
          />
          <div className="left-body">
            <strong>{card.name} left your mat</strong>
            <div className="row">
              <button
                className="primary"
                onClick={() => onMove(card, "graveyard")}
              >
                Graveyard
              </button>
              <button onClick={() => onMove(card, "exile")}>Exile</button>
              <button onClick={() => onMove(card, "hand")}>Hand</button>
              <button onClick={() => onMove(card, "library")}>Library</button>
              <button className="ghost" onClick={() => onKeep(card)}>
                Still in play
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

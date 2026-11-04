/* ============================================================
   Minesweeper
   ============================================================ */

const MINE_ROWS = 8;
const MINE_COLS = 8;
const MINE_COUNT = 10;

let mines = [];
let revealed = [];
let flags = [];
let minesDone = false;

const minesGrid = document.getElementById("mines-grid");
const minesStatus = document.getElementById("mines-status");

function initMinesweeper() {
  mines = Array.from({ length: MINE_ROWS }, () => Array(MINE_COLS).fill(false));
  revealed = Array.from({ length: MINE_ROWS }, () => Array(MINE_COLS).fill(false));
  flags = Array.from({ length: MINE_ROWS }, () => Array(MINE_COLS).fill(false));
  minesDone = false;

  let placed = 0;
  while (placed < MINE_COUNT) {
    const row = Math.floor(Math.random() * MINE_ROWS);
    const col = Math.floor(Math.random() * MINE_COLS);
    if (!mines[row][col]) {
      mines[row][col] = true;
      placed++;
    }
  }

  renderMinesweeper();
}

function adjacentCount(row, col) {
  let count = 0;
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const nr = row + dr;
      const nc = col + dc;
      if (nr >= 0 && nr < MINE_ROWS && nc >= 0 && nc < MINE_COLS && mines[nr][nc]) {
        count++;
      }
    }
  }
  return count;
}

function revealFlood(row, col) {
  const stack = [[row, col]];

  while (stack.length) {
    const [r, c] = stack.pop();
    if (revealed[r][c] || flags[r][c] || mines[r][c]) continue;

    revealed[r][c] = true;
    const count = adjacentCount(r, c);

    if (count === 0) {
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          const nr = r + dr;
          const nc = c + dc;
          if (nr >= 0 && nr < MINE_ROWS && nc >= 0 && nc < MINE_COLS) {
            stack.push([nr, nc]);
          }
        }
      }
    }
  }
}

function revealCell(row, col) {
  if (minesDone || revealed[row][col] || flags[row][col]) return;

  if (mines[row][col]) {
    minesDone = true;
    revealed[row][col] = true;
    renderMinesweeper();
    minesStatus.textContent = "Boom! Game over.";
    return;
  }

  revealFlood(row, col);
  renderMinesweeper();

  if (checkMinesWin()) {
    minesDone = true;
    minesStatus.textContent = "You win!";
  }
}

function flagCell(row, col) {
  if (minesDone || revealed[row][col]) return;
  flags[row][col] = !flags[row][col];
  renderMinesweeper();
}

function checkMinesWin() {
  let safeCells = 0;
  let revealedSafe = 0;

  for (let row = 0; row < MINE_ROWS; row++) {
    for (let col = 0; col < MINE_COLS; col++) {
      if (!mines[row][col]) {
        safeCells++;
        if (revealed[row][col]) revealedSafe++;
      }
    }
  }

  return safeCells === revealedSafe;
}

function renderMinesweeper() {
  minesGrid.innerHTML = "";

  for (let row = 0; row < MINE_ROWS; row++) {
    for (let col = 0; col < MINE_COLS; col++) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "mine-cell";
      cell.dataset.row = row;
      cell.dataset.col = col;

      if (flags[row][col] && !revealed[row][col]) {
        cell.textContent = "⚑";
        cell.classList.add("flag");
      } else if (revealed[row][col]) {
        cell.classList.add("revealed");
        if (mines[row][col]) {
          cell.textContent = "💥";
        } else {
          const count = adjacentCount(row, col);
          cell.textContent = count > 0 ? String(count) : "";
        }
      }

      cell.addEventListener("click", () => revealCell(row, col));
      cell.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        flagCell(row, col);
      });

      minesGrid.appendChild(cell);
    }
  }

  if (!minesDone) {
    minesStatus.textContent = "Find 10 mines. Left-click to reveal, right-click to flag.";
  }
}

document.getElementById("mines-reset").addEventListener("click", initMinesweeper);

/* ============================================================
   Solitaire (simple Klondike-style)
   ============================================================ */

const SUITS = ["♠", "♥", "♦", "♣"];
const RANK_LABELS = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

let solitaire = {
  stock: [],
  waste: [],
  foundations: [[], [], [], []],
  tableau: [],
  selected: null,
  dragSource: null,
  done: false,
};

function isRed(suit) {
  return suit === "♥" || suit === "♦";
}

function rankLabel(rank) {
  return RANK_LABELS[rank];
}

function makeDeck() {
  const deck = [];
  for (let suit = 0; suit < 4; suit++) {
    for (let rank = 1; rank <= 13; rank++) {
      deck.push({ rank, suit: SUITS[suit] });
    }
  }
  return deck;
}

function shuffle(deck) {
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

function initSolitaire() {
  const deck = shuffle(makeDeck());

  solitaire = {
    stock: [],
    waste: [],
    foundations: [[], [], [], []],
    tableau: [],
    selected: null,
    dragSource: null,
    done: false,
  };

  for (let pile = 0; pile < 7; pile++) {
    const column = [];
    for (let card = 0; card <= pile; card++) {
      column.push(deck.pop());
    }
    solitaire.tableau.push(column);
  }

  solitaire.stock = deck;
  renderSolitaire();
}

function selectedCard() {
  if (!solitaire.selected) return null;

  if (solitaire.selected.kind === "waste") {
    return solitaire.waste[solitaire.waste.length - 1] || null;
  }

  if (solitaire.selected.kind === "tableau") {
    const pile = solitaire.tableau[solitaire.selected.index];
    return pile[pile.length - 1] || null;
  }

  return null;
}

function removeSelectedCard() {
  if (!solitaire.selected) return;

  if (solitaire.selected.kind === "waste") {
    solitaire.waste.pop();
  } else if (solitaire.selected.kind === "tableau") {
    solitaire.tableau[solitaire.selected.index].pop();
  }

  solitaire.selected = null;
}

function selectWaste() {
  if (solitaire.done || !solitaire.waste.length) return;
  solitaire.selected = { kind: "waste" };
  renderSolitaire();
}

function selectTableau(index) {
  if (solitaire.done) return;
  const pile = solitaire.tableau[index];
  if (!pile.length) return;

  solitaire.selected = { kind: "tableau", index };
  renderSolitaire();
}

function drawStock() {
  if (solitaire.done) return;

  if (solitaire.stock.length > 0) {
    solitaire.waste.push(solitaire.stock.pop());
  } else if (solitaire.waste.length > 0) {
    solitaire.stock = solitaire.waste.reverse();
    solitaire.waste = [];
  }

  solitaire.selected = null;
  renderSolitaire();
}

function moveToFoundation(suitIndex) {
  if (solitaire.done) return;

  const card = selectedCard();
  if (!card) return;
  if (card.suit !== SUITS[suitIndex]) return;
  if (card.rank !== solitaire.foundations[suitIndex].length + 1) return;

  removeSelectedCard();
  solitaire.foundations[suitIndex].push(card);
  renderSolitaire();
  checkSolitaireWin();
}

function moveToTableau(targetIndex) {
  if (solitaire.done) return;

  if (solitaire.selected?.kind === "tableau" && solitaire.selected.index === targetIndex) {
    return;
  }

  const card = selectedCard();
  if (!card) return;

  const targetPile = solitaire.tableau[targetIndex];
  const targetTop = targetPile[targetPile.length - 1];

  if (targetTop) {
    if (targetTop.rank !== card.rank + 1) return;
    if (isRed(targetTop.suit) === isRed(card.suit)) return;
  }

  removeSelectedCard();
  targetPile.push(card);
  renderSolitaire();
  checkSolitaireWin();
}

function checkSolitaireWin() {
  const total = solitaire.foundations.reduce((sum, pile) => sum + pile.length, 0);

  if (total === 52) {
    solitaire.done = true;
    document.getElementById("solitaire-status").textContent = "You win!";
    return;
  }

  document.getElementById("solitaire-status").textContent =
    "Click the stock to draw. Click a top card to select it, or drag it to a foundation or another tableau pile.";
}

function renderSolitaire() {
  const stockEl = document.getElementById("stock");
  const wasteEl = document.getElementById("waste");
  const foundationsEl = document.getElementById("foundations");
  const tableauEl = document.getElementById("tableau");

  stockEl.innerHTML = "";
  wasteEl.innerHTML = "";
  foundationsEl.innerHTML = "";
  tableauEl.innerHTML = "";

  const stockButton = document.createElement("button");
  stockButton.type = "button";
  stockButton.className = "card-pile";
  stockButton.textContent = solitaire.stock.length ? `Stock ${solitaire.stock.length}` : "Stock empty";
  stockButton.addEventListener("click", drawStock);
  stockEl.appendChild(stockButton);

  if (solitaire.waste.length) {
    const card = solitaire.waste[solitaire.waste.length - 1];
    const wasteCard = document.createElement("button");
    wasteCard.type = "button";
    wasteCard.className = "card";
    if (solitaire.selected?.kind === "waste") wasteCard.classList.add("selected");
    wasteCard.textContent = `${rankLabel(card.rank)}${card.suit}`;
    wasteCard.draggable = true;
    wasteCard.addEventListener("click", selectWaste);
    wasteCard.addEventListener("dragstart", () => {
      solitaire.dragSource = { kind: "waste" };
    });
    wasteEl.appendChild(wasteCard);
  } else {
    const empty = document.createElement("div");
    empty.className = "empty-card";
    empty.textContent = "empty";
    wasteEl.appendChild(empty);
  }

  for (let suit = 0; suit < 4; suit++) {
    const foundation = document.createElement("button");
    foundation.type = "button";
    foundation.className = "foundation";
    const top = solitaire.foundations[suit][solitaire.foundations[suit].length - 1];
    foundation.textContent = top ? `${rankLabel(top.rank)}${top.suit}` : SUITS[suit];
    foundation.addEventListener("click", () => moveToFoundation(suit));
    foundation.addEventListener("dragover", (event) => event.preventDefault());
    foundation.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!solitaire.dragSource) return;
      solitaire.selected = solitaire.dragSource;
      moveToFoundation(suit);
      solitaire.dragSource = null;
    });
    foundationsEl.appendChild(foundation);
  }

  for (let pileIndex = 0; pileIndex < 7; pileIndex++) {
    const pileEl = document.createElement("div");
    pileEl.className = "tableau-pile";
    pileEl.addEventListener("dragover", (event) => event.preventDefault());
    pileEl.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!solitaire.dragSource) return;
      solitaire.selected = solitaire.dragSource;
      moveToTableau(pileIndex);
      solitaire.dragSource = null;
    });

    const pile = solitaire.tableau[pileIndex];

    if (!pile.length) {
      const empty = document.createElement("button");
      empty.type = "button";
      empty.className = "empty-card";
      empty.textContent = "—";
      empty.addEventListener("click", () => moveToTableau(pileIndex));
      pileEl.appendChild(empty);
    } else {
      pile.forEach((card, cardIndex) => {
        const cardEl = document.createElement("button");
        cardEl.type = "button";
        cardEl.className = "card";
        cardEl.textContent = `${rankLabel(card.rank)}${card.suit}`;

        if (cardIndex === pile.length - 1) {
          cardEl.classList.add("top");
          if (solitaire.selected?.kind === "tableau" && solitaire.selected.index === pileIndex) {
            cardEl.classList.add("selected");
          }
          cardEl.draggable = true;
          cardEl.addEventListener("click", () => selectTableau(pileIndex));
          cardEl.addEventListener("dragstart", () => {
            solitaire.dragSource = { kind: "tableau", index: pileIndex };
          });
        }

        pileEl.appendChild(cardEl);
      });
    }

    tableauEl.appendChild(pileEl);
  }

  checkSolitaireWin();
}

document.getElementById("solitaire-reset").addEventListener("click", initSolitaire);

/* ============================================================
   Game tabs
   ============================================================ */

function showGame(name) {
  const minesPanel = document.getElementById("minesweeper");
  const solitairePanel = document.getElementById("solitaire");
  const minesTab = document.getElementById("tab-mines");
  const solitaireTab = document.getElementById("tab-solitaire");

  const showingMines = name === "mines";

  minesPanel.classList.toggle("hidden", !showingMines);
  solitairePanel.classList.toggle("hidden", showingMines);
  minesTab.classList.toggle("active", showingMines);
  solitaireTab.classList.toggle("active", !showingMines);
}

document.getElementById("tab-mines").addEventListener("click", () => showGame("mines"));
document.getElementById("tab-solitaire").addEventListener("click", () => showGame("solitaire"));

initMinesweeper();
initSolitaire();
showGame("mines");

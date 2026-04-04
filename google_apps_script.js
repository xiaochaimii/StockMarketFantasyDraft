// ============================================================
// Google Apps Script — Reactions + Challenge Votes
// ============================================================
// Deploy: Extensions > Apps Script > Deploy > Web app
//   Execute as: Me
//   Who has access: Anyone
//
// This script uses TWO sheets in the same spreadsheet:
//   1) "Reactions"  – existing emoji reaction counts
//   2) "Votes"      – challenge votes (MVP, HOH, Earnings)
//
// After pasting this, click Deploy > Manage deployments >
//   Edit (pencil icon) > Version: New version > Deploy
// ============================================================

// ---------- helpers ----------

function getOrCreateSheet(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
  }
  return sheet;
}

// ---------- Reactions (existing) ----------

function getReactions() {
  var sheet = getOrCreateSheet("Reactions");
  var data = sheet.getDataRange().getValues();
  var result = {};
  for (var i = 0; i < data.length; i++) {
    var key = data[i][0];   // e.g. "roast_0"
    var emoji = data[i][1]; // e.g. "😂"
    var count = data[i][2]; // e.g. 5
    if (!result[key]) result[key] = {};
    result[key][emoji] = count;
  }
  return result;
}

function updateReaction(roast, emoji, delta) {
  var sheet = getOrCreateSheet("Reactions");
  var data = sheet.getDataRange().getValues();
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] === roast && data[i][1] === emoji) {
      var newCount = Math.max(0, (data[i][2] || 0) + delta);
      sheet.getRange(i + 1, 3).setValue(newCount);
      return;
    }
  }
  // Not found — create new row
  if (delta > 0) {
    sheet.appendRow([roast, emoji, delta]);
  }
}

// ---------- Challenge Votes ----------

// Votes sheet columns: A=type, B=voter, C=pick, D=timestamp
// type = "mvp" | "hoh" | "earn"

function saveVote(type, voter, pick) {
  var sheet = getOrCreateSheet("Votes");
  var data = sheet.getDataRange().getValues();

  // Check if this voter already voted for this type
  // For earnings, voter includes the stock, so each stock is separate
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] === type && data[i][1] === voter) {
      // Update existing vote
      sheet.getRange(i + 1, 3).setValue(pick);
      sheet.getRange(i + 1, 4).setValue(new Date().toISOString());
      return;
    }
  }
  // New vote
  sheet.appendRow([type, voter, pick, new Date().toISOString()]);
}

function deleteVote(type, voter) {
  var sheet = getOrCreateSheet("Votes");
  var data = sheet.getDataRange().getValues();
  for (var i = data.length - 1; i >= 0; i--) {
    if (data[i][0] === type && data[i][1] === voter) {
      sheet.deleteRow(i + 1);
      return;
    }
  }
}

function getVotes(type) {
  var sheet = getOrCreateSheet("Votes");
  var data = sheet.getDataRange().getValues();
  var counts = {};
  var total = 0;
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] === type) {
      var pick = data[i][2];
      counts[pick] = (counts[pick] || 0) + 1;
      total++;
    }
  }
  return { votes: counts, total: total };
}

function getEarningsVotes() {
  var sheet = getOrCreateSheet("Votes");
  var data = sheet.getDataRange().getValues();
  // Returns: { "AAPL": { up: 3, down: 1 }, "SVNDY": { up: 0, down: 2 } }
  var result = {};
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] === "earn") {
      var pick = data[i][2]; // e.g. "AAPL_up"
      var parts = pick.split("_");
      var dir = parts.pop();         // "up" or "down"
      var stock = parts.join("_");   // handles tickers with underscores
      if (!result[stock]) result[stock] = { up: 0, down: 0 };
      if (dir === "up" || dir === "down") {
        result[stock][dir]++;
      }
    }
  }
  return result;
}

// ---------- Main handler ----------

function doGet(e) {
  var p = e.parameter;

  // --- Existing emoji reactions ---
  if (p.roast && p.emoji && p.delta) {
    updateReaction(p.roast, p.emoji, parseInt(p.delta));
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Challenge votes ---
  if (p.action === "mvp_vote") {
    saveVote("mvp", p.voter, p.pick);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "mvp_remove") {
    deleteVote("mvp", p.voter);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "get_mvp_votes") {
    var mvp = getVotes("mvp");
    return ContentService.createTextOutput(JSON.stringify(mvp))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "hoh_vote") {
    saveVote("hoh", p.voter, p.pick);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "hoh_remove") {
    deleteVote("hoh", p.voter);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "get_hoh_votes") {
    var hoh = getVotes("hoh");
    return ContentService.createTextOutput(JSON.stringify(hoh))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "earn_vote") {
    // voter = earn_{voterId}_{stock}, pick = STOCK_up or STOCK_down
    saveVote("earn", p.voter, p.pick);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "earn_remove") {
    deleteVote("earn", p.voter);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "get_earn_votes") {
    var earn = getEarningsVotes();
    return ContentService.createTextOutput(JSON.stringify(earn))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Legacy: old vote action (backwards compat) ---
  if (p.action === "vote") {
    // Old format — treat as MVP vote for backwards compat
    saveVote("mvp", p.voter, p.pick);
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "get_votes") {
    var all = getVotes("mvp");
    return ContentService.createTextOutput(JSON.stringify(all))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // --- Default: return all reactions ---
  var reactions = getReactions();
  return ContentService.createTextOutput(JSON.stringify(reactions))
    .setMimeType(ContentService.MimeType.JSON);
}

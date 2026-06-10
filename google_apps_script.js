// ============================================================
// Google Apps Script — Reactions + Challenge Votes + Owners
// ============================================================
// Deploy: Extensions > Apps Script > Deploy > Web app
//   Execute as: Me
//   Who has access: Anyone
//
// This script uses THREE sheets in the same spreadsheet:
//   1) "Roast"      – emoji reaction counts (public, unauthenticated)
//   2) "Votes"      – challenge votes (public, unauthenticated)
//   3) "Owners"     – PII: ticker -> owner name/email. TOKEN-GATED.
//
// SECURITY SETUP (required for Owners):
//   File > Project properties > Script properties >
//     add ADMIN_TOKEN = <a long random string>
//   Put the same value in the Streamlit app's secrets as ADMIN_TOKEN.
//   Reaction/vote actions stay open on purpose: guests use them without
//   logging in, the data is low-stakes, and any token shipped to the
//   public page would be visible anyway. Owner data is PII, admin-only,
//   and every owner action checks the token.
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
  var sheet = getOrCreateSheet("Roast");
  var data = sheet.getDataRange().getValues();
  // Row 0 is header: [roast_key, 😂, 💀, 🔥]
  if (data.length < 2) return {};
  var emojis = data[0].slice(1); // ["😂", "💀", "🔥"]
  var result = {};
  for (var i = 1; i < data.length; i++) {
    var key = data[i][0];
    if (!key) continue;
    result[key] = {};
    for (var j = 0; j < emojis.length; j++) {
      result[key][emojis[j]] = data[i][j + 1] || 0;
    }
  }
  return result;
}

function updateReaction(roast, emoji, delta) {
  var sheet = getOrCreateSheet("Roast");
  var data = sheet.getDataRange().getValues();
  // Row 0 is header: [roast_key, 😂, 💀, 🔥]
  var emojis = data[0].slice(1);
  var colIndex = emojis.indexOf(emoji);
  if (colIndex === -1) return; // emoji not in header

  for (var i = 1; i < data.length; i++) {
    if (data[i][0] === roast) {
      var newCount = Math.max(0, (data[i][colIndex + 1] || 0) + delta);
      sheet.getRange(i + 1, colIndex + 2).setValue(newCount);
      return;
    }
  }
  // Not found — create new row
  if (delta > 0) {
    var newRow = [roast];
    for (var k = 0; k < emojis.length; k++) {
      newRow.push(emojis[k] === emoji ? delta : 0);
    }
    sheet.appendRow(newRow);
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

function getVoterPicks(voter) {
  var sheet = getOrCreateSheet("Votes");
  var data = sheet.getDataRange().getValues();
  var picks = {};
  var earnPicks = {};
  for (var i = 0; i < data.length; i++) {
    var type = data[i][0];
    var voterCol = data[i][1];
    var pick = data[i][2];
    if (voterCol === voter) {
      picks[type] = pick;
    }
    // Earnings votes use "earn_{voterId}_{stock}" as voter
    if (type === "earn" && voterCol.indexOf("earn_" + voter + "_") === 0) {
      var stock = voterCol.replace("earn_" + voter + "_", "");
      earnPicks[stock] = pick;
    }
  }
  picks.earn = earnPicks;
  return picks;
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

// ---------- Owners (PII — token-gated) ----------

// Owners sheet columns: A=ticker, B=owner_name, C=owner_email, D=updated_at

function checkToken(token) {
  var expected = PropertiesService.getScriptProperties().getProperty("ADMIN_TOKEN");
  return expected && token && token === expected;
}

function getOwners() {
  var sheet = getOrCreateSheet("Owners");
  var data = sheet.getDataRange().getValues();
  var result = {};
  for (var i = 0; i < data.length; i++) {
    var ticker = data[i][0];
    if (!ticker || ticker === "ticker") continue; // skip blanks + header
    result[ticker] = {
      owner_name: data[i][1] || "",
      owner_email: data[i][2] || "",
      updated_at: data[i][3] || "",
    };
  }
  return result;
}

function setOwner(ticker, name, email) {
  var sheet = getOrCreateSheet("Owners");
  var data = sheet.getDataRange().getValues();
  var now = new Date().toISOString();
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] === ticker) {
      if (!name && !email) {
        sheet.deleteRow(i + 1); // cleared in the app -> remove the row
      } else {
        sheet.getRange(i + 1, 2).setValue(name);
        sheet.getRange(i + 1, 3).setValue(email);
        sheet.getRange(i + 1, 4).setValue(now);
      }
      return;
    }
  }
  if (name || email) {
    sheet.appendRow([ticker, name, email, now]);
  }
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

  if (p.action === "get_my_votes") {
    var myVotes = getVoterPicks(p.voter);
    return ContentService.createTextOutput(JSON.stringify(myVotes))
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

  // --- Owners (PII — every action checks the token) ---
  if (p.action === "get_owners") {
    if (!checkToken(p.token)) {
      return ContentService.createTextOutput(JSON.stringify({ error: "unauthorized" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(JSON.stringify(getOwners()))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (p.action === "set_owner") {
    if (!checkToken(p.token)) {
      return ContentService.createTextOutput(JSON.stringify({ error: "unauthorized" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    setOwner(p.ticker || "", p.name || "", p.email || "");
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
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

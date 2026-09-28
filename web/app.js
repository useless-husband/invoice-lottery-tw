(function () {
  "use strict";
  var L = window.Lottery;
  var $ = function (id) { return document.getElementById(id); };
  var data = null, current = null;
  var quick = { count: 0, wins: 0, total: 0, unsure: 0, pending: null };

  function today() {
    var d = new Date();
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }

  // ---------- 載入與期別 ----------
  fetch("data.json", { cache: "no-cache" }).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(init).catch(function (e) {
    $("meta").textContent = "讀不到 data.json（" + e.message + "）。請用網頁伺服器開啟，例如在專案根目錄執行 python3 -m http.server。";
  });

  function init(d) {
    data = d;
    $("meta").textContent = "資料更新於 " + d.generated_at.slice(0, 10) + "，來源：" + d.source;
    var sel = $("period");
    d.periods.forEach(function (p, i) {
      var o = el("option", p.label + (i === 0 ? "（最新）" : ""));
      o.value = p.period;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { selectPeriod(sel.value); resetQuick(); });
    selectPeriod(d.periods[0].period);
    resetQuick();
    $("last3").focus();
  }

  function selectPeriod(key) {
    current = data.periods.filter(function (p) { return p.period === key; })[0];
    $("periodInfo").textContent = "開獎日 " + current.draw_date + "　領獎期間 " + current.claim_start + " 至 " + current.claim_end;
    var st = L.periodStatus(current, today()), w = $("periodWarn");
    w.hidden = st === "claimable";
    if (st === "pending") w.textContent = "這一期要到 " + current.draw_date + " 才開獎。";
    if (st === "expired") w.textContent = "這一期的領獎期限（" + current.claim_end + "）已經過了。";
    renderNumbers();
  }

  function renderNumbers() {
    var t = $("numbersTable");
    t.textContent = "";
    function row(a, b, c) {
      var tr = el("tr");
      tr.appendChild(el("th", a)); tr.appendChild(el("td", b)); tr.appendChild(el("td", c));
      t.appendChild(tr);
    }
    row("特別獎", "1,000 萬", current.special);
    row("特獎", "200 萬", current.grand);
    row("頭獎", "20 萬", current.first.join("　"));
    L.LOWER.forEach(function (x) {
      row(x[0], L.formatAmount(x[1]) + " 元", "末 " + x[2] + " 碼：" + current.first.map(function (f) { return f.slice(-x[2]); }).join("　"));
    });
    if (current.extra_sixth && current.extra_sixth.length) row("增開六獎", "200 元", "末 3 碼：" + current.extra_sixth.join("　"));
  }

  // ---------- 分頁 ----------
  function showTab(name) {
    var q = name === "quick";
    $("tabQuick").setAttribute("aria-selected", q);
    $("tabPaste").setAttribute("aria-selected", !q);
    $("paneQuick").hidden = !q;
    $("panePaste").hidden = q;
    (q ? $("last3") : $("pasteInput")).focus();
  }
  $("tabQuick").addEventListener("click", function () { showTab("quick"); });
  $("tabPaste").addEventListener("click", function () { showTab("paste"); });

  // ---------- 貼上模式 ----------
  $("pasteGo").addEventListener("click", function () {
    if (!current) return;
    var r = L.extractNumbers($("pasteInput").value);
    var ul = $("pasteResults"); ul.textContent = "";
    var wins = 0, total = 0;
    r.numbers.forEach(function (n) {
      var w = L.evaluate(n, current), li = el("li");
      if (w) {
        wins++; total += w.amount;
        li.appendChild(el("span", n + "　"));
        li.appendChild(el("span", w.prize + " " + L.formatAmount(w.amount) + " 元", "win"));
      } else {
        li.appendChild(el("span", n + "　沒中", "lose"));
      }
      ul.appendChild(li);
    });
    r.bad.forEach(function (b) { ul.appendChild(el("li", "看不懂：" + b + "（需要 8 位數字）", "lose")); });
    var s = $("pasteStats");
    s.hidden = false;
    s.textContent = r.numbers.length ? "共 " + r.numbers.length + " 張，中獎 " + wins + " 張，總獎金 " + L.formatAmount(total) + " 元。" : "沒有找到可以對獎的號碼。";
  });

  // ---------- 快速模式 ----------
  function renderQuickStats() {
    var s = "已對 " + quick.count + " 張，中獎 " + quick.wins + " 張，總獎金 " + L.formatAmount(quick.total) + " 元。";
    if (quick.unsure) s += "　另有 " + quick.unsure + " 張末三碼相符但沒確認完整號碼。";
    $("quickStats").textContent = s;
  }
  function say(text, cls) { var r = $("lastResult"); r.textContent = text; r.className = "last " + (cls || ""); }
  function resetQuick() {
    quick = { count: 0, wins: 0, total: 0, unsure: 0, pending: null };
    $("fullBox").hidden = true; $("last3").disabled = false; $("last3").value = ""; $("full").value = "";
    say(""); renderQuickStats();
  }
  $("resetQuick").addEventListener("click", function () { resetQuick(); $("last3").focus(); });

  function finishWin(n) {
    var w = L.evaluate(n, current);
    if (w) { quick.wins++; quick.total += w.amount; say(n + "　中獎！" + w.prize + " " + L.formatAmount(w.amount) + " 元", "win"); }
    else say(n + "　沒中（末三碼像，但整組不同）", "lose");
  }
  function backToLast3() {
    $("fullBox").hidden = true; $("full").value = "";
    $("last3").disabled = false; $("last3").value = ""; $("last3").focus();
    quick.pending = null; renderQuickStats();
  }

  $("last3").addEventListener("input", function () {
    if (!current) return;
    var v = this.value.replace(/[\s-]/g, "");
    var full = L.normalizeNumber(v);
    if (full) { quick.count++; finishWin(full); this.value = ""; renderQuickStats(); return; }
    if (!/^\d{3}$/.test(v)) return;
    quick.count++;
    if (!L.couldWin(v, current)) {
      say(v + "　沒中", "lose"); this.value = ""; renderQuickStats(); return;
    }
    quick.pending = v;
    say(v + "　可能中獎！", "win");
    this.disabled = true;
    $("fullBox").hidden = false; $("full").value = ""; $("full").focus();
    renderQuickStats();
  });

  function confirmFull() {
    var t = $("full").value.replace(/[\s-]/g, "");
    if (t === "") return skipFull();
    if (/^\d{5}$/.test(t)) t += quick.pending;
    var n = L.normalizeNumber(t);
    if (!n) { say("請輸入 8 碼或前 5 碼", "lose"); return; }
    if (n.slice(-3) !== quick.pending) { say("末三碼跟剛才的 " + quick.pending + " 不一樣，請重輸", "lose"); return; }
    finishWin(n); backToLast3();
  }
  function skipFull() { quick.unsure++; say(quick.pending + "　略過（未確認）", "lose"); backToLast3(); }
  $("fullOk").addEventListener("click", confirmFull);
  $("fullSkip").addEventListener("click", skipFull);
  $("full").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); confirmFull(); } });
})();

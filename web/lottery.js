// 對獎邏輯（純函式，無 DOM）。規則與 Python 版 invoice_lottery/prizes.py 相同。
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Lottery = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var LOWER = [
    ["二獎", 40000, 7],
    ["三獎", 10000, 6],
    ["四獎", 4000, 5],
    ["五獎", 1000, 4],
    ["六獎", 200, 3],
  ];

  function normalizeNumber(text) {
    var s = String(text).replace(/[\s-]/g, "");
    var m = /^(?:[A-Za-z]{2})?(\d{8})$/.exec(s);
    return m ? m[1] : null;
  }

  // 中多個獎項只回傳金額最高的一個；沒中回傳 null
  function evaluate(number, data) {
    var n = normalizeNumber(number);
    if (!n) throw new Error("發票號碼必須是 8 位數字");
    var best = null;
    function offer(prize, amount, matched) {
      if (!best || amount > best.amount) best = { prize: prize, amount: amount, matched: matched };
    }
    if (n === data.special) offer("特別獎", 10000000, data.special);
    if (n === data.grand) offer("特獎", 2000000, data.grand);
    data.first.forEach(function (f) {
      if (n === f) return offer("頭獎", 200000, f);
      for (var i = 0; i < LOWER.length; i++) {
        var d = LOWER[i][2];
        if (n.slice(-d) === f.slice(-d)) return offer(LOWER[i][0], LOWER[i][1], f.slice(-d));
      }
    });
    (data.extra_sixth || []).forEach(function (e) {
      if (n.slice(-3) === e) offer("增開六獎", 200, e);
    });
    return best;
  }

  function couldWin(last3, data) {
    if (!/^\d{3}$/.test(last3)) return false;
    if (data.special.slice(-3) === last3 || data.grand.slice(-3) === last3) return true;
    if ((data.extra_sixth || []).indexOf(last3) >= 0) return true;
    return data.first.some(function (f) { return f.slice(-3) === last3; });
  }

  // 從一段文字抽出所有發票號碼；回傳 {numbers:[], bad:[]}
  function extractNumbers(text) {
    var numbers = [], bad = [];
    String(text).split(/[\s,，、;；]+/).forEach(function (tok) {
      if (!tok) return;
      var n = normalizeNumber(tok);
      if (n) numbers.push(n); else bad.push(tok);
    });
    return { numbers: numbers, bad: bad };
  }

  function parseDate(s) {
    var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    return p ? new Date(Date.UTC(+p[1], +p[2] - 1, +p[3])) : null;
  }

  // 'pending' | 'claimable' | 'expired'；today 為 YYYY-MM-DD 字串
  function periodStatus(p, today) {
    if (today < p.draw_date) return "pending";
    if (today > p.claim_end) return "expired";
    return "claimable";
  }

  function formatAmount(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }

  return {
    normalizeNumber: normalizeNumber, evaluate: evaluate, couldWin: couldWin,
    extractNumbers: extractNumbers, periodStatus: periodStatus, formatAmount: formatAmount,
    parseDate: parseDate, LOWER: LOWER,
  };
});

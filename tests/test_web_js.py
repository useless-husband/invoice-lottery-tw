"""用 node 執行 web/lottery.js，確認網頁版的比對結果跟 Python 版完全一致。沒有 node 就略過。"""
import json
import random
import shutil
import subprocess
import unittest

from invoice_lottery import prizes, store

from .helpers import ROOT

NODE = shutil.which("node")

SCRIPT = """
const L = require(process.argv[1]);
let input = '';
process.stdin.on('data', c => input += c);
process.stdin.on('end', () => {
  const {data, numbers} = JSON.parse(input);
  const out = numbers.map(n => {
    const w = L.evaluate(n, data);
    return [w ? w.prize : null, w ? w.amount : 0, L.couldWin(n.slice(-3), data)];
  });
  console.log(JSON.stringify(out));
});
"""


@unittest.skipUnless(NODE, "需要 node")
class WebParityTests(unittest.TestCase):
    def test_same_results_as_python(self):
        doc = json.loads((ROOT / "web" / "data.json").read_text(encoding="utf-8"))
        rng = random.Random(1)
        for pd_obj, pdata in zip(doc["periods"], store.load_dict(doc)):
            numbers = [pd_obj["special"], pd_obj["grand"], *pd_obj["first"]]
            for f in pd_obj["first"]:  # 每個獎項邊界：末 3~8 碼相同、再往前一碼不同
                for k in range(3, 9):
                    flip = str((int(f[-k - 1]) + 1) % 10) if k < 8 else ""
                    numbers.append((f"{rng.randrange(10**8):08d}"[: 8 - k - (1 if k < 8 else 0)] + flip + f[-k:])[-8:])
            numbers += [f"{rng.randrange(10**8):08d}" for _ in range(1500)]
            r = subprocess.run([NODE, "-e", SCRIPT, str(ROOT / "web" / "lottery.js")],
                               input=json.dumps({"data": pd_obj, "numbers": numbers}),
                               capture_output=True, text=True, check=True)
            got = json.loads(r.stdout)
            for n, (prize, amount, could) in zip(numbers, got):
                w = prizes.evaluate(n, pdata)
                self.assertEqual((prize, amount), (w.prize, w.amount) if w else (None, 0), n)
                self.assertEqual(could, prizes.could_win(n[-3:], pdata), n)


if __name__ == "__main__":
    unittest.main()

"""
城市探索打卡系统
- 主页面：展示站点列表，点击弹出二维码
- 签到页：手机扫码后打开，确认签到
- 进度实时查询
"""

import hmac
import hashlib
import time
import os
from datetime import datetime

from flask import Flask, send_from_directory
from flask import Flask, request, jsonify, render_template
import qrcode
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__,static_folder='/tmp')

# ============================================================
# 配置 —— 改成你的实际地址，手机需在同一网络能访问
# ============================================================
SECRET_KEY = "city_explore_2024_secret"
BASE_URL = "https://dwca.vercel.app"  # ← 改成你的局域网IP
QRCODE_DIR = os.path.join(app.static_folder, "qrcodes")

STATIONS = [
    {"id": 1, "name": "启程广场", "desc": "在起点留下足迹，开启城市探索之旅", "icon": "fa-flag"},
    {"id": 2, "name": "星光市集", "desc": "品味地道风味，感受人间烟火气",     "icon": "fa-utensils"},
    {"id": 3, "name": "云端画廊", "desc": "沉浸艺术光影，发现美的瞬间",       "icon": "fa-palette"},
    {"id": 4, "name": "潮流工坊", "desc": "亲手创作专属手作，留下独特记忆",   "icon": "fa-hammer"},
    {"id": 5, "name": "秘密花园", "desc": "抵达终点，领取你的探索者礼物",     "icon": "fa-gift"},
]

# 存储（生产环境用 Redis/MySQL）
checkin_db = {}   # { uid: { "1": "2024-06-15T10:30:00", ... } }
gift_db = {}      # { uid: "2024-06-15T12:00:00" }


# ============================================================
# 签名工具
# ============================================================

def sign(station_id: int, timestamp: int) -> str:
    """HMAC-SHA256 签名，取前12位"""
    message = f"{station_id}:{timestamp}"
    return hmac.new(
        SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).hexdigest()[:12]


def verify_token(station_id: int, timestamp: int, signature: str) -> bool:
    """验证签名 + 有效期（24小时）"""
    expected = sign(station_id, timestamp)
    if not hmac.compare_digest(signature, expected):
        return False
    if abs(time.time() - timestamp) > 86400:
        return False
    return True


# ============================================================
# 页面路由
# ============================================================

@app.route("/")
def index():
    """主页面：站点列表 + 弹出二维码"""
    return render_template("index.html")


@app.route("/checkin/<int:station_id>")
def checkin_page(station_id):
    """签到确认页：手机扫码后打开"""
    timestamp = int(request.args.get("t", "0"))
    signature = request.args.get("sig", "")
    valid = verify_token(station_id, timestamp, signature)
    station = next((s for s in STATIONS if s["id"] == station_id), None)

    return render_template("checkin.html",
                           station=station,
                           station_id=station_id,
                           valid=valid,
                           timestamp=timestamp,
                           signature=signature)


# ============================================================
# API
# ============================================================

@app.route("/api/stations")
def api_stations():
    """查询站点 + 用户进度"""
    uid = request.args.get("uid", "")
    user_checkins = checkin_db.get(uid, {})

    result = []
    for s in STATIONS:
        sid = str(s["id"])
        result.append({
            "id": s["id"],
            "name": s["name"],
            "desc": s["desc"],
            "icon": s["icon"],
            "checked_in": sid in user_checkins,
            "checkin_time": user_checkins.get(sid),
        })

    done = len(user_checkins)
    total = len(STATIONS)

    return jsonify({
        "stations": result,
        "progress": {
            "done": done,
            "total": total,
            "percent": round(done / total * 100, 1),
            "all_done": done == total,
        },
        "gift_claimed": uid in gift_db,
    })


@app.route("/api/qrcode/<int:station_id>")
def api_qrcode(station_id):
    """
    生成站点二维码图片
    二维码内容 = 签到URL（手机扫码后跳转到确认页）
    """
    timestamp = int(time.time())
    signature = sign(station_id, timestamp)

    # 二维码内容是签到URL
    checkin_url = f"{BASE_URL}/checkin/{station_id}?t={timestamp}&sig={signature}"

    # 生成二维码
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(checkin_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # 加底部文字
    station_name = next(s["name"] for s in STATIONS if s["id"] == station_id)
    img = _add_label(img, f"第{station_id}站 · {station_name}")

    # 保存
    os.makedirs(QRCODE_DIR, exist_ok=True)
    filename = f"qr_s{station_id}_{timestamp}.png"
    filepath = os.path.join(QRCODE_DIR, filename)
    img.save(filepath)

    return jsonify({
        "ok": True,
        "image_url": f"/qrcodes/{filename}",
        "checkin_url": checkin_url,
    })


# ✅ This route serves files from /tmp
@app.route('/qrcodes/<filename>')
def serve_qrcode(filename):
    return send_from_directory(app.static_folder, filename)

def _add_label(img, text):
    """二维码底部加文字标注"""
    qr_w, qr_h = img.size
    label_h = 48
    canvas = Image.new("RGB", (qr_w, qr_h + label_h), "white")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)

    font = _load_font(22)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((qr_w - text_w) / 2, qr_h + 10), text, fill="black", font=font)
    return canvas


def _load_font(size):
    paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


@app.route("/api/do_checkin", methods=["POST"])
def api_do_checkin():
    """执行签到（签到确认页调用）"""
    data = request.get_json()
    uid = data.get("uid", "").strip()
    station_id = data.get("station_id")
    timestamp = data.get("timestamp")
    signature = data.get("signature", "")

    if not uid:
        return jsonify({"ok": False, "msg": "请输入手机号"})

    # 验证签名
    if not verify_token(int(station_id), int(timestamp), signature):
        return jsonify({"ok": False, "msg": "二维码无效或已过期，请刷新重试"})

    sid = str(station_id)
    user_checkins = checkin_db.get(uid, {})

    # 重复签到
    if sid in user_checkins:
        return jsonify({"ok": False, "msg": "该站点已签到，无需重复打卡"})

    # 顺序校验
    sid_int = int(station_id)
    if sid_int > 1 and str(sid_int - 1) not in user_checkins:
        return jsonify({
            "ok": False,
            "msg": f"请先完成第{sid_int - 1}站的打卡",
        })

    # 签到
    now = datetime.now().isoformat()
    if uid not in checkin_db:
        checkin_db[uid] = {}
    checkin_db[uid][sid] = now

    done = len(checkin_db[uid])
    total = len(STATIONS)

    return jsonify({
        "ok": True,
        "msg": "签到成功",
        "station_name": next(s["name"] for s in STATIONS if s["id"] == sid_int),
        "progress": {"done": done, "total": total, "all_done": done == total},
    })


@app.route("/api/claim_gift", methods=["POST"])
def api_claim_gift():
    data = request.get_json()
    uid = data.get("uid", "").strip()
    if uid not in checkin_db or len(checkin_db[uid]) < len(STATIONS):
        return jsonify({"ok": False, "msg": "尚未完成全部打卡"})
    if uid in gift_db:
        return jsonify({"ok": False, "msg": "礼物已领取"})
    gift_db[uid] = datetime.now().isoformat()
    return jsonify({"ok": True, "msg": "礼物领取成功", "prize": "限量版探索者徽章套装"})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    data = request.get_json()
    uid = data.get("uid", "").strip()
    checkin_db.pop(uid, None)
    gift_db.pop(uid, None)
    return jsonify({"ok": True})


# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  城市探索打卡系统")
    print(f"  主页面:   {BASE_URL}")
    print(f"  签到示例: {BASE_URL}/checkin/1?t=0&sig=test")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000)

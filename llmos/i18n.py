"""Fixed interface strings. Everything else the user reads comes from the
model, which is told which language to use for each section."""
import json
import os

from . import config

S = {
    "en": {
        "prompt": "›", "working": "working", "loading_model": "Loading the model…",
        "model_ready": "Ready.", "allow": "Allow %s?", "yes_no_always": "y = yes, n = no, a = always",
        "denied": "Not allowed.", "stopped": "Stopped.", "unlock": "Passphrase to unlock your data",
        "unlock_bad": "Wrong passphrase.", "unlocked": "Unlocked.",
        "net_needed": "This needs the internet, which is off. Turn it on?",
        "net_choices": "direct|through Tor|cancel", "tasks_done": "%d scheduled task(s) finished. Type: tasks",
        "welcome": "LLMOS", "onboard_intro": "Setup. Answer with a number or type your answer.",
        "ob_lang": "Language", "ob_profile": "How much should the computer do on its own?",
        "ob_profile_auto": "Autonomous: never ask me anything",
        "ob_profile_bal": "Balanced: ask before deleting things or sending my data out",
        "ob_profile_care": "Careful: ask before any change",
        "ob_net": "Internet access", "ob_net_off": "Off (fully offline)",
        "ob_net_direct": "On", "ob_net_tor": "On, only through Tor",
        "ob_disk": "Where should your data be stored? It will be encrypted.",
        "ob_disk_ram": "Nowhere: forget everything when switched off",
        "ob_erase": "Everything on %s will be erased. Type ERASE to continue",
        "ob_pass": "Choose a passphrase", "ob_pass2": "Type it again",
        "ob_pass_warn": "There is no recovery. If you forget this passphrase your data is gone for good.",
        "ob_pass_mismatch": "They do not match.", "ob_name": "What should I call you? (optional)",
        "ob_tz": "Time zone (for example Europe/Berlin, America/New_York)",
        "ob_model": "Which model? (the bundled one works offline)",
        "ob_done": "Done. Tell me what you want to do.", "ob_formatting": "Encrypting the disk…",
        "err": "Error", "steps_exhausted": "Stopped after too many steps.",
        "help": "Type what you want in plain words. Examples: \"brightness 40\", \"make everything purple\", \"play the latest Veritasium video\", \"search for flights to Lisbon\". Ctrl-C stops the current task.",
    },
    "zh": {
        "prompt": "›", "working": "处理中", "loading_model": "正在加载模型…", "model_ready": "就绪。",
        "allow": "允许 %s？", "yes_no_always": "y = 是，n = 否，a = 总是", "denied": "未允许。",
        "stopped": "已停止。", "unlock": "输入密码以解锁数据", "unlock_bad": "密码错误。", "unlocked": "已解锁。",
        "net_needed": "此操作需要联网，但网络已关闭。要打开吗？", "net_choices": "直接连接|通过 Tor|取消",
        "tasks_done": "%d 个计划任务已完成。输入：tasks", "welcome": "LLMOS",
        "onboard_intro": "设置。请输入数字或直接回答。", "ob_lang": "语言",
        "ob_profile": "电脑可以自主做多少事？", "ob_profile_auto": "完全自主：从不询问我",
        "ob_profile_bal": "平衡：删除内容或发送我的数据前询问", "ob_profile_care": "谨慎：任何更改前都询问",
        "ob_net": "网络访问", "ob_net_off": "关闭（完全离线）", "ob_net_direct": "打开", "ob_net_tor": "打开，仅通过 Tor",
        "ob_disk": "数据存放在哪里？将被加密。", "ob_disk_ram": "不存储：关机后全部忘记",
        "ob_erase": "%s 上的所有内容将被清除。输入 ERASE 继续", "ob_pass": "设置密码", "ob_pass2": "再输入一次",
        "ob_pass_warn": "没有任何恢复方式。忘记密码数据将永久丢失。", "ob_pass_mismatch": "两次输入不一致。",
        "ob_name": "我该怎么称呼你？（可选）", "ob_tz": "时区（例如 Asia/Shanghai）",
        "ob_model": "使用哪个模型？（内置模型可离线使用）", "ob_done": "完成。告诉我你想做什么。",
        "ob_formatting": "正在加密磁盘…", "err": "错误", "steps_exhausted": "步骤过多，已停止。",
        "help": "用普通的话说出你想做的事。例如：“亮度 40”、“全部改成紫色”、“播放最新的 Veritasium 视频”。Ctrl-C 停止当前任务。",
    },
    "es": {
        "prompt": "›", "working": "trabajando", "loading_model": "Cargando el modelo…", "model_ready": "Listo.",
        "allow": "¿Permitir %s?", "yes_no_always": "s = sí, n = no, a = siempre", "denied": "No permitido.",
        "stopped": "Detenido.", "unlock": "Frase de acceso para desbloquear tus datos",
        "unlock_bad": "Frase incorrecta.", "unlocked": "Desbloqueado.",
        "net_needed": "Esto necesita internet, que está apagado. ¿Activarlo?",
        "net_choices": "directo|por Tor|cancelar", "tasks_done": "%d tarea(s) programada(s) terminada(s). Escribe: tasks",
        "ob_done": "Listo. Dime qué quieres hacer.", "err": "Error",
    },
    "fr": {
        "prompt": "›", "working": "en cours", "loading_model": "Chargement du modèle…", "model_ready": "Prêt.",
        "allow": "Autoriser %s ?", "yes_no_always": "o = oui, n = non, a = toujours", "denied": "Refusé par vous.",
        "stopped": "Arrêté.", "unlock": "Phrase secrète pour déverrouiller vos données",
        "unlock_bad": "Phrase incorrecte.", "unlocked": "Déverrouillé.",
        "net_needed": "Il faut internet, qui est coupé. L'activer ?", "net_choices": "direct|via Tor|annuler",
        "ob_done": "Terminé. Dites-moi ce que vous voulez faire.", "err": "Erreur",
    },
    "de": {
        "prompt": "›", "working": "arbeitet", "loading_model": "Modell wird geladen…", "model_ready": "Bereit.",
        "allow": "%s erlauben?", "yes_no_always": "j = ja, n = nein, a = immer", "denied": "Nicht erlaubt.",
        "stopped": "Gestoppt.", "unlock": "Passphrase zum Entsperren deiner Daten",
        "unlock_bad": "Falsche Passphrase.", "unlocked": "Entsperrt.",
        "net_needed": "Dafür braucht es Internet, das ist aus. Einschalten?", "net_choices": "direkt|über Tor|abbrechen",
        "ob_done": "Fertig. Sag mir, was du tun willst.", "err": "Fehler",
    },
    "ja": {
        "prompt": "›", "working": "処理中", "loading_model": "モデルを読み込み中…", "model_ready": "準備完了。",
        "allow": "%s を許可しますか？", "yes_no_always": "y = はい、n = いいえ、a = 常に", "denied": "許可されていません。",
        "stopped": "停止しました。", "unlock": "データのロックを解除するパスフレーズ",
        "unlock_bad": "パスフレーズが違います。", "unlocked": "解除しました。",
        "net_needed": "インターネットが必要ですがオフです。オンにしますか？", "net_choices": "直接|Tor 経由|キャンセル",
        "ob_done": "完了。やりたいことを伝えてください。", "err": "エラー",
    },
}

LANG_NAMES = {
    "en": "English", "zh": "中文", "es": "Español", "fr": "Français", "de": "Deutsch", "ja": "日本語",
    "ko": "한국어", "pt": "Português", "it": "Italiano", "ru": "Русский", "ar": "العربية", "hi": "हिन्दी",
    "nl": "Nederlands", "pl": "Polski", "tr": "Türkçe", "uk": "Українська", "vi": "Tiếng Việt",
}

ALIASES = {
    "english": "en", "chinese": "zh", "mandarin": "zh", "中文": "zh", "spanish": "es", "español": "es",
    "french": "fr", "français": "fr", "german": "de", "deutsch": "de", "japanese": "ja", "日本語": "ja",
    "korean": "ko", "portuguese": "pt", "italian": "it", "russian": "ru", "arabic": "ar", "hindi": "hi",
    "dutch": "nl", "polish": "pl", "turkish": "tr", "ukrainian": "uk", "vietnamese": "vi",
    "zh-cn": "zh", "zh_cn": "zh", "zh-hans": "zh", "simplified chinese": "zh",
}


def code(lang):
    l = str(lang).strip().lower()
    return ALIASES.get(l, l.split("-")[0].split("_")[0] if len(l) > 3 and ("-" in l or "_" in l) else l)


def _cache():
    try:
        with open(config.dpath("i18n-cache.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def add_translation(lang, table):
    c = _cache()
    c[lang] = table
    os.makedirs(config.DATA, exist_ok=True)
    with open(config.dpath("i18n-cache.json"), "w") as f:
        json.dump(c, f, ensure_ascii=False)


def has(lang):
    return lang in S or lang in _cache()


def t(lang, key, *args):
    table = S.get(lang) or _cache().get(lang) or {}
    s = table.get(key) or S["en"].get(key, key)
    return s % args if args else s


def name(lang):
    return LANG_NAMES.get(lang, lang)

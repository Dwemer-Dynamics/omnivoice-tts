from __future__ import annotations

# Multilingual TTS language catalog v0.6.3
#
# This catalog has two layers:
# 1) WHISPER_LANGUAGES: the OpenAI Whisper tokenizer language list used for ASR
#    verification during auto-calibration.
# 2) RECOMMENDED_LANGUAGE_PRESETS: languages from the Whisper list that also have
#    a known OmniVoice language/ID mapping. This is the useful intersection for
#    this tool because calibration needs both TTS generation and ASR verification.
#
# OmniVoice itself supports 646 languages. The GUI deliberately focuses on the
# Whisper-compatible subset for guided automatic calibration; advanced users can
# still type/edit any custom JSON profile manually.

WHISPER_LANGUAGES: dict[str, str] = {
    "en": "english", "zh": "chinese", "de": "german", "es": "spanish", "ru": "russian",
    "ko": "korean", "fr": "french", "ja": "japanese", "pt": "portuguese", "pt-br": "portuguese", "tr": "turkish",
    "pl": "polish", "ca": "catalan", "nl": "dutch", "ar": "arabic", "sv": "swedish",
    "it": "italian", "id": "indonesian", "hi": "hindi", "fi": "finnish", "vi": "vietnamese",
    "he": "hebrew", "uk": "ukrainian", "el": "greek", "ms": "malay", "cs": "czech",
    "ro": "romanian", "da": "danish", "hu": "hungarian", "ta": "tamil", "no": "norwegian",
    "th": "thai", "ur": "urdu", "hr": "croatian", "bg": "bulgarian", "lt": "lithuanian",
    "la": "latin", "mi": "maori", "ml": "malayalam", "cy": "welsh", "sk": "slovak",
    "te": "telugu", "fa": "persian", "lv": "latvian", "bn": "bengali", "sr": "serbian",
    "az": "azerbaijani", "sl": "slovenian", "kn": "kannada", "et": "estonian", "mk": "macedonian",
    "br": "breton", "eu": "basque", "is": "icelandic", "hy": "armenian", "ne": "nepali",
    "mn": "mongolian", "bs": "bosnian", "kk": "kazakh", "sq": "albanian", "sw": "swahili",
    "gl": "galician", "mr": "marathi", "pa": "punjabi", "si": "sinhala", "km": "khmer",
    "sn": "shona", "yo": "yoruba", "so": "somali", "af": "afrikaans", "oc": "occitan",
    "ka": "georgian", "be": "belarusian", "tg": "tajik", "sd": "sindhi", "gu": "gujarati",
    "am": "amharic", "yi": "yiddish", "lo": "lao", "uz": "uzbek", "fo": "faroese",
    "ht": "haitian creole", "ps": "pashto", "tk": "turkmen", "nn": "nynorsk", "mt": "maltese",
    "sa": "sanskrit", "lb": "luxembourgish", "my": "myanmar", "bo": "tibetan", "tl": "tagalog",
    "mg": "malagasy", "as": "assamese", "tt": "tatar", "haw": "hawaiian", "ln": "lingala",
    "ha": "hausa", "ba": "bashkir", "jw": "javanese", "su": "sundanese", "yue": "cantonese",
}

SAMPLE_TEXTS: dict[str, tuple[str, str]] = {
    "en": (
        "Hello. Today is a beautiful and peaceful day. The wind moves across the mountains, the grass rustles by the river, and we can talk quietly beside the fire.",
        "In the morning, George walks beside the river toward the old castle. The wind presses against the gate, and dry wood crackles in the fireplace.",
    ),
    "sk": (
        "Ahoj. Dnes je krásny pokojný deň. Vietor fúka ponad hory, pri rieke šumí tráva a pri ohni sa môžeme pokojne porozprávať.",
        "Ráno pri rieke kráča Juraj k starému hradu. Vietor sa opiera do brány a v krbe praská suché drevo.",
    ),
    "cs": (
        "Ahoj. Dnes je krásný klidný den. Vítr fouká přes hory, u řeky šumí tráva a u ohně si můžeme v klidu popovídat.",
        "Ráno u řeky kráčí Jiří ke starému hradu. Vítr se opírá do brány a v krbu praská suché dřevo.",
    ),
    "es": (
        "Hola. Hoy hace un día claro y tranquilo. El viento cruza las montañas, las hojas se mueven junto al río y podemos conversar despacio frente al fuego.",
        "Al amanecer, Javier camina por el viejo camino hacia el castillo. Una brisa fresca golpea la puerta, mientras la leña seca cruje suavemente en la chimenea.",
    ),
    "pt": (
        "Ola. Hoje e um dia calmo junto ao rio, o vento passa pelas montanhas e podemos conversar devagar perto do fogo.",
        "De manha, Jorge caminha pela estrada antiga em direcao ao castelo, enquanto a lenha seca crepita suavemente na lareira.",
    ),
    "pt-br": (
        "Ola. Hoje esta um dia tranquilo perto do rio, o vento passa pelas montanhas e a gente pode conversar devagar junto ao fogo.",
        "De manha, Jorge caminha pela estrada velha ate o castelo, enquanto a lenha seca estala baixinho na lareira.",
    ),
    "de": (
        "Hallo. Heute ist ein ruhiger Tag am Fluss, der Wind weht durch die Berge und wir können am Feuer leise sprechen.",
        "Am Morgen geht Georg den alten Weg entlang zur Burg, während trockenes Holz im Kamin knistert.",
    ),
    "pl": (
        "Cześć. Dzisiaj jest spokojny dzień nad rzeką, wiatr porusza trawą przy brzegu i możemy cicho porozmawiać przy ogniu.",
        "Rano Jerzy idzie starą drogą w stronę zamku, a suche drewno cicho trzaska w kominku.",
    ),
    "fr": (
        "Bonjour. Aujourd'hui est une journée calme au bord de la rivière, le vent passe sur les montagnes et nous pouvons parler doucement près du feu.",
        "Le matin, Georges marche sur le vieux chemin vers le château, tandis que le bois sec crépite dans la cheminée.",
    ),
    "it": (
        "Ciao. Oggi è una giornata tranquilla vicino al fiume, il vento passa tra le montagne e possiamo parlare piano accanto al fuoco.",
        "Al mattino Giorgio cammina lungo la vecchia strada verso il castello, mentre la legna secca scoppietta nel camino.",
    ),
    "hu": (
        "Szia. Ma nyugodt nap van a folyó mellett, a szél átfúj a hegyeken, és csendesen beszélgethetünk a tűz mellett.",
        "Reggel György a régi úton halad a vár felé, miközben a száraz fa halkan ropog a kandallóban.",
    ),
    "ro": (
        "Bună. Astăzi este o zi liniștită lângă râu, vântul trece peste munți și putem vorbi încet lângă foc.",
        "Dimineața, George merge pe drumul vechi spre castel, în timp ce lemnul uscat trosnește în șemineu.",
    ),
    "uk": (
        "Привіт. Сьогодні спокійний день біля річки, вітер проходить через гори, і ми можемо тихо поговорити біля вогню.",
        "Вранці Юрій іде старою дорогою до замку, а сухі дрова тихо потріскують у каміні.",
    ),
    "ru": (
        "Здравствуйте. Сегодня спокойный день у реки, ветер проходит над горами, и мы можем тихо поговорить у огня.",
        "Утром Георгий идет по старой дороге к замку, а сухие дрова тихо потрескивают в камине.",
    ),
    "ja": (
        "こんにちは。今日は川のそばで静かな一日です。風が山を越えて吹き、私たちは火の近くで落ち着いて話すことができます。",
        "朝、健二は古い道を通って城へ向かいます。門に風が当たり、暖炉では乾いた木が静かに音を立てています。",
    ),
    "ko": (
        "안녕하세요. 오늘은 강가의 조용한 날입니다. 바람이 산을 지나가고 우리는 불 옆에서 차분하게 이야기할 수 있습니다.",
        "아침에 민수는 오래된 길을 따라 성으로 걸어갑니다. 문에는 바람이 부딪히고 벽난로에서는 마른 장작이 조용히 타오릅니다.",
    ),
    "zh": (
        "你好。今天是河边安静的一天，风从群山之间吹过，我们可以在火旁慢慢说话。",
        "清晨，李明沿着旧路走向城堡，风吹着大门，干柴在壁炉里轻轻作响。",
    ),
    "yue": (
        "你好。今日河邊好安靜，風吹過山邊，我哋可以喺火旁邊慢慢傾偈。",
        "朝早，阿明沿住舊路行去城堡，風吹住大門，乾柴喺壁爐入面輕輕作響。",
    ),
}

# code, display_name, omnivoice_language_value, omnivoice_language_id, aliases
# OmniVoice IDs follow the official docs where they differ from the Whisper code.
_COMMON_ROWS: list[tuple[str, str, str, str, tuple[str, ...]]] = [
    ("en", "English", "English", "en", ("eng",)),
    ("sk", "Slovak", "Slovak", "sk", ("slk", "slovensky", "slovenčina", "slovencina")),
    ("cs", "Czech", "Czech", "cs", ("cz", "cze", "ces", "cesky", "čeština", "cestina")),
    ("es", "Spanish", "Spanish", "es", ("spa", "espanol", "español")),
    ("de", "German", "German", "de", ("deutsch",)),
    ("pl", "Polish", "Polish", "pl", ("polski", "polska")),
    ("fr", "French", "French", "fr", ("francais", "français")),
    ("it", "Italian", "Italian", "it", ("italiano",)),
    ("hu", "Hungarian", "Hungarian", "hu", ("magyar",)),
    ("ro", "Romanian", "Romanian", "ro", ("română", "romana")),
    ("uk", "Ukrainian", "Ukrainian", "uk", ("ukr", "українська")),
    ("ru", "Russian", "Russian", "ru", ("русский",)),
    ("zh", "Chinese", "Chinese", "zh", ("mandarin", "cmn")),
    ("yue", "Cantonese", "Cantonese", "yue", ("cantonese chinese",)),
    ("ko", "Korean", "Korean", "ko", ()),
    ("ja", "Japanese", "Japanese", "ja", ()),
    ("pt", "Portuguese", "Portuguese", "pt", ("português", "portugues")),
    ("pt-br", "Brazilian Portuguese", "Portuguese", "pt", ("brasileiro", "portugues brasileiro", "brazilian portuguese")),
    ("tr", "Turkish", "Turkish", "tr", ("turkce", "türkçe")),
    ("ca", "Catalan", "Catalan", "ca", ()),
    ("nl", "Dutch", "Dutch", "nl", ()),
    ("ar", "Standard Arabic", "Standard Arabic", "arb", ("arabic", "العربية")),
    ("sv", "Swedish", "Swedish", "sv", ()),
    ("id", "Indonesian", "Indonesian", "id", ()),
    ("hi", "Hindi", "Hindi", "hi", ()),
    ("fi", "Finnish", "Finnish", "fi", ()),
    ("vi", "Vietnamese", "Vietnamese", "vi", ()),
    ("he", "Hebrew", "Hebrew", "he", ()),
    ("el", "Greek", "Greek", "el", ()),
    ("ms", "Malay", "Malay", "ms", ()),
    ("da", "Danish", "Danish", "da", ()),
    ("ta", "Tamil", "Tamil", "ta", ()),
    ("no", "Norwegian", "Norwegian", "no", ()),
    ("th", "Thai", "Thai", "th", ()),
    ("ur", "Urdu", "Urdu", "ur", ()),
    ("hr", "Croatian", "Croatian", "hr", ()),
    ("bg", "Bulgarian", "Bulgarian", "bg", ()),
    ("lt", "Lithuanian", "Lithuanian", "lt", ()),
    ("mi", "Maori", "Maori", "mi", ()),
    ("ml", "Malayalam", "Malayalam", "ml", ()),
    ("cy", "Welsh", "Welsh", "cy", ()),
    ("te", "Telugu", "Telugu", "te", ()),
    ("fa", "Persian", "Persian", "fa", ("farsi",)),
    ("lv", "Latvian", "Latvian", "lv", ()),
    ("bn", "Bengali", "Bengali", "bn", ()),
    ("sr", "Serbian", "Serbian", "sr", ()),
    ("az", "Azerbaijani", "Azerbaijani", "az", ()),
    ("sl", "Slovenian", "Slovenian", "sl", ()),
    ("kn", "Kannada", "Kannada", "kn", ()),
    ("et", "Estonian", "Estonian", "et", ()),
    ("mk", "Macedonian", "Macedonian", "mk", ()),
    ("br", "Breton", "Breton", "br", ()),
    ("eu", "Basque", "Basque", "eu", ()),
    ("is", "Icelandic", "Icelandic", "is", ()),
    ("hy", "Armenian", "Armenian", "hy", ()),
    ("ne", "Nepali", "Nepali", "npi", ()),
    ("mn", "Mongolian", "Mongolian", "mn", ()),
    ("bs", "Bosnian", "Bosnian", "bs", ()),
    ("kk", "Kazakh", "Kazakh", "kk", ()),
    ("sq", "Albanian", "Albanian", "sq", ()),
    ("sw", "Swahili", "Swahili", "sw", ()),
    ("gl", "Galician", "Galician", "gl", ()),
    ("mr", "Marathi", "Marathi", "mr", ()),
    ("pa", "Panjabi", "Panjabi", "pa", ("punjabi",)),
    ("si", "Sinhala", "Sinhala", "si", ()),
    ("km", "Khmer", "Khmer", "km", ()),
    ("sn", "Shona", "Shona", "sn", ()),
    ("yo", "Yoruba", "Yoruba", "yo", ()),
    ("so", "Somali", "Somali", "so", ()),
    ("af", "Afrikaans", "Afrikaans", "af", ()),
    ("oc", "Occitan", "Occitan", "oc", ()),
    ("ka", "Georgian", "Georgian", "ka", ()),
    ("be", "Belarusian", "Belarusian", "be", ()),
    ("tg", "Tajik", "Tajik", "tg", ()),
    ("sd", "Sindhi", "Sindhi", "sd", ()),
    ("gu", "Gujarati", "Gujarati", "gu", ()),
    ("am", "Amharic", "Amharic", "am", ()),
    ("yi", "Yiddish", "Yiddish", "yi", ()),
    ("lo", "Lao", "Lao", "lo", ()),
    ("uz", "Uzbek", "Uzbek", "uz", ()),
    ("ht", "Haitian", "Haitian", "ht", ("haitian creole",)),
    ("ps", "Pushto", "Pushto", "ps", ("pashto",)),
    ("tk", "Turkmen", "Turkmen", "tk", ()),
    ("nn", "Norwegian Nynorsk", "Norwegian Nynorsk", "nn", ("nynorsk",)),
    ("mt", "Maltese", "Maltese", "mt", ()),
    ("sa", "Sanskrit", "Sanskrit", "sa", ()),
    ("lb", "Luxembourgish", "Luxembourgish", "lb", ()),
    ("my", "Burmese", "Burmese", "my", ("myanmar",)),
    ("bo", "Tibetan", "Tibetan", "bo", ()),
    ("tl", "Filipino", "Filipino", "fil", ("tagalog",)),
    ("as", "Assamese", "Assamese", "as", ()),
    ("tt", "Tatar", "Tatar", "tt", ()),
    ("haw", "Hawaiian", "Hawaiian", "haw", ()),
    ("ln", "Lingala", "Lingala", "ln", ()),
    ("ha", "Hausa", "Hausa", "ha", ()),
    ("ba", "Bashkir", "Bashkir", "ba", ()),
    ("jw", "Javanese", "Javanese", "jv", ("jv",)),
]


def _fallback_samples(code: str, display: str) -> tuple[str, str]:
    return (
        f"REPLACE THIS with a clear natural calibration sentence in {display}. Keep it neutral, calm, and at least one full sentence long.",
        f"REPLACE THIS with a second clear natural calibration sentence in {display}. It should sound different from the first one.",
    )


def recommended_language_presets() -> list[dict[str, object]]:
    presets: list[dict[str, object]] = []
    for code, display, omni_value, omni_id, aliases in _COMMON_ROWS:
        whisper = WHISPER_LANGUAGES.get(code, display.casefold())
        bootstrap, master = SAMPLE_TEXTS.get(code, _fallback_samples(code, display))
        presets.append({
            "id": code,
            "display_name": display,
            "omnivoice_language": omni_value,
            "omnivoice_language_id": omni_id,
            "whisper_language": whisper,
            "aliases": list(aliases),
            "bootstrap_text": bootstrap,
            "master_text": master,
            "has_native_samples": code in SAMPLE_TEXTS,
        })
    return presets


RECOMMENDED_LANGUAGE_PRESETS = recommended_language_presets()


def preset_label(preset: dict[str, object]) -> str:
    native = "native samples" if preset.get("has_native_samples") else "edit samples"
    return (
        f"{preset['id']} — {preset['display_name']} "
        f"[OmniVoice: {preset['omnivoice_language_id']} / Whisper: {preset['whisper_language']}; {native}]"
    )


def find_preset(value: str) -> dict[str, object] | None:
    needle = value.strip().casefold()
    if not needle:
        return None
    for preset in RECOMMENDED_LANGUAGE_PRESETS:
        candidates = {
            str(preset.get("id", "")).casefold(),
            str(preset.get("display_name", "")).casefold(),
            str(preset.get("omnivoice_language", "")).casefold(),
            str(preset.get("omnivoice_language_id", "")).casefold(),
            str(preset.get("whisper_language", "")).casefold(),
        }
        candidates.update(str(item).casefold() for item in preset.get("aliases", []) if str(item).strip())
        if needle in candidates:
            return preset
    return None


def searchable_catalog_text() -> str:
    lines = [
        "Multilingual TTS language catalog",
        "",
        f"Whisper tokenizer languages bundled here: {len(WHISPER_LANGUAGES)}",
        f"Recommended OmniVoice+Whisper profile presets: {len(RECOMMENDED_LANGUAGE_PRESETS)}",
        "",
        "The recommended list is the practical intersection used by this tool:",
        "OmniVoice must generate speech and Whisper must verify the calibration text.",
        "OmniVoice officially supports 646 languages; advanced users can still type/edit a custom JSON profile manually.",
        "",
        "Recommended presets:",
    ]
    for preset in RECOMMENDED_LANGUAGE_PRESETS:
        lines.append("  " + preset_label(preset))
    lines.append("")
    lines.append("Whisper language names:")
    for code, name in sorted(WHISPER_LANGUAGES.items()):
        lines.append(f"  {code:>4}  {name}")
    return "\n".join(lines) + "\n"

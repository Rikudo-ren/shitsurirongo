#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
アップロード前チェックスクリプト
================================

この譜面セットがサーバー側 (MySQL latin1_swedish_ci) への変換で
エラーを出さない構成になっているかを検証します。

ルール（アップロード仕様）:
  [日本語(全角) OK]  : Title, Artist の通常欄 (=TitleUnicode/ArtistUnicode),
                       Source, Tags(半角スペース区切り)
  [半角のみ・絶対NG]  : Romanised Title / Romanised Artist (=Title/Artist),
                       Version(難易度名) … 半角英数字のみ
                       .mp3 / .png / .jpg / .osu 等の全ファイル名・フォルダ名
  [ID 固定]          : BeatmapSetID / BeatmapID は指定の固定値であること

使い方:  python3 validate_upload.py
         問題がなければ "ALL OK" を出力して終了コード 0。
"""

import os
import re
import sys

# ---------------------------------------------------------------- 設定（固定値）
SET_DIR = "2637792 Sakurayuu - Shitsurirongo"
FIXED_SET_ID = 2637792
FIXED_MAP_IDS = {          # Version -> BeatmapID（絶対に変えないこと）
    "Easy":    5943367,
    "Easyx2":  5943410,
    "Normal":  5943370,
    "Normalx2": 5943412,
    "Hard":    5943369,
    "Hardx2":  5943411,
}

# 日本語(全角)を入れてよいフィールド
JP_OK_FIELDS = {"TitleUnicode", "ArtistUnicode", "Source", "Tags"}

AUDIO_EXT = (".mp3", ".ogg", ".wav")
IMAGE_EXT = (".jpg", ".jpeg", ".png")


def is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def parse_osu(path: str):
    """(section, key, value) の行リストと raw 行リストを返す"""
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")  # BOM は想定外
    section = ""
    rows = []
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            rows.append((section, key.strip(), value.strip()))
    return rows, text.splitlines()


def main() -> int:
    errors = []

    def err(msg):
        errors.append(msg)

    # ---------------------------------------------------------- フォルダ名
    if not is_ascii(os.path.basename(SET_DIR)):
        err(f"フォルダ名に半角以外の文字が含まれています: {SET_DIR}")
    if not os.path.isdir(SET_DIR):
        print(f"NG: フォルダが見つかりません: {SET_DIR}")
        return 1

    # ---------------------------------------------------------- 内部の全ファイル名
    for name in sorted(os.listdir(SET_DIR)):
        if not is_ascii(name):
            err(f"ファイル名に半角以外の文字が含まれています: {name}")

    # ---------------------------------------------------------- 各 .osu
    osu_files = sorted(f for f in os.listdir(SET_DIR) if f.endswith(".osu"))
    if not osu_files:
        err(".osu ファイルが 1 件もありません")

    seen_versions = set()
    for fname in osu_files:
        path = os.path.join(SET_DIR, fname)
        rows, lines = parse_osu(path)
        meta = {(s, k): v for s, k, v in rows}
        tag = f"[{fname}]"

        def m(k, section="Metadata"):
            return meta.get((section, k), "")

        # --- Romanised Title / Artist : 半角のみ（日本語NG）
        for k in ("Title", "Artist"):
            v = m(k)
            if not is_ascii(v):
                err(f"{tag} {k}(Romanised) に半角以外が入っています: {v!r}")

        # --- Version(難易度名) : 半角英数字のみ
        version = m("Version")
        if not re.fullmatch(r"[A-Za-z0-9]+", version):
            err(f"{tag} Version は半角英数字のみにしてください: {version!r}")
        if version in seen_versions:
            err(f"{tag} Version が重複しています: {version!r}")
        seen_versions.add(version)

        # --- Tags : 半角スペース区切り（全角スペースNG）
        tags = m("Tags")
        if "　" in tags or "\t" in tags:
            err(f"{tag} Tags は半角スペースで区切ってください: {tags!r}")

        # --- ID 固定チェック
        try:
            set_id = int(m("BeatmapSetID"))
        except ValueError:
            set_id = None
        if set_id != FIXED_SET_ID:
            err(f"{tag} BeatmapSetID が固定値 {FIXED_SET_ID} ではありません: {m('BeatmapSetID')!r}")
        expected = FIXED_MAP_IDS.get(version)
        try:
            map_id = int(m("BeatmapID"))
        except ValueError:
            map_id = None
        if expected is not None and map_id != expected:
            err(f"{tag} BeatmapID が固定値 {expected} ではありません: {m('BeatmapID')!r}")

        # --- 参照ファイル (AudioFilename / 背景・動画) : 半角のみ & 実在
        audio = meta.get(("General", "AudioFilename"), "")
        if not is_ascii(audio):
            err(f"{tag} AudioFilename に半角以外が含まれています: {audio!r}")
        elif audio and not os.path.isfile(os.path.join(SET_DIR, audio)):
            err(f"{tag} AudioFilename のファイルが存在しません: {audio!r}")

        for sec, key, value in rows:
            if sec == "Events":
                parts = value.split(",")
                if parts and parts[0].strip() in ("0", "1") and '"' in value:
                    ref = value.split('"')[1] if value.count('"') >= 2 else ""
                    if ref:
                        if not is_ascii(ref):
                            err(f"{tag} 参照ファイル名に半角以外が含まれています: {ref!r}")
                        elif not os.path.isfile(os.path.join(SET_DIR, ref)):
                            err(f"{tag} 参照ファイルが存在しません: {ref!r}")

        # --- 全行総ざらい: 半角以外は日本語OKフィールドのみ許可
        for line in lines:
            if not any(ord(c) > 127 for c in line):
                continue
            key = line.partition(":")[0].strip() if ":" in line else ""
            if key in JP_OK_FIELDS:
                continue
            err(f"{tag} 半角以外の文字が許可されていない箇所にあります: {line[:70]!r}")

    # ---------------------------------------------------------- 結果
    if errors:
        print("UPLOAD CHECK: NG")
        for e in errors:
            print("  -", e)
        return 1
    print(f"UPLOAD CHECK: ALL OK ({len(osu_files)} diffs, set id {FIXED_SET_ID} fixed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import hashlib

import streamlit as st

from common.ui import apply_app_style
from common import atehagi as A
from common import proceed_atehagi as PR
from common import advalue as AV
from common import shiwake as SH

apply_app_style()
st.title("資料作成・変換表")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VERSION_JP = {A.KEIHAN_KITA: "京阪北版", A.KEIHAN_MINAMI: "京阪南版"}

tab_atehagi, tab_shiwake, tab_proceed, tab_advalue, tab_other = st.tabs(
    ["ぱど あて紙", "仕分け表", "リビングプロシード あて紙", "アドバリュー 報告書",
     "その他（準備中）"])

with tab_atehagi:
    st.caption("関西ぱどの配送管理表（CSV / Excel）をアップロードすると、"
               "担当地区ごとのあて紙をまとめたExcelを作成します。")
    # 🔴 segmented_control は選択を解除でき、そのとき None を返す。
    # `A.KEIHAN_KITA if label == "京阪北版" else A.KEIHAN_MINAMI` のような書き方だと
    # None が黙って南版に落ち、全枚数のあて紙で地区名が誤る。
    # 既定へ戻したうえで、対応表で引く。
    # 並びは 南 → 北（2026-08-07 オーナー指示で左右を入れ替えた）。
    # 既定は「京阪北版」のまま変えていない（位置の入れ替えだけの指示だったため）。
    _VERSIONS = {"京阪南版": A.KEIHAN_MINAMI, "京阪北版": A.KEIHAN_KITA}
    version_label = st.segmented_control("版", list(_VERSIONS), default="京阪北版",
                                         key="keihan_version") or "京阪北版"
    version = _VERSIONS[version_label]
    # 版の取り違えは全枚数に影響するため、テストで固定できるよう解決結果を残す
    st.session_state["_resolved_version"] = version

    up = st.file_uploader("配送管理表をアップロード", type=["csv", "xlsx", "xlsm"],
                          key="keihan_upload")
    if up is not None:
        rows = groups = None
        try:
            table = A.read_uploaded(up.name, up.getvalue())
            rows = A.rows_from_table(table)
            groups = A.group_by_chiku(rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"読み取りに失敗しました: {e}")

        # 版やファイルを変えたら前回の生成物は捨てる（古いファイルを配らないため）。
        # ファイル名とサイズだけでは「同じ名前・同じ桁数で中身だけ直したCSV」を見逃すので
        # 中身のハッシュで比べる。
        if up is not None:
            stamp = (f"{version}|{up.name}|"
                     f"{hashlib.sha1(up.getvalue()).hexdigest()}")
            if st.session_state.get("keihan_stamp") != stamp:
                st.session_state["keihan_stamp"] = stamp
                st.session_state.pop("keihan_out", None)
                st.session_state.pop("keihan_single_out", None)

        detected = A.detect_version(groups) if groups else None
        if groups and detected and detected != version:
            # 版を取り違えたまま出すと、全枚数の地区名が誤った紙が黙って出来上がる
            st.error(
                f"担当地区コードから見て、このデータは **{VERSION_JP[detected]}** です。"
                f"いま選ばれているのは {VERSION_JP[version]} です。"
                "版を切り替えてから生成してください"
                "（このまま出すと、すべての枚数で見出しの地区名が誤ります）。")
        elif not groups:
            if rows is not None:
                st.warning("データ行が0件でした。配送管理表の中身をご確認ください。")
        else:
            gou = next((r["gou"] for r in rows if r.get("gou")), "—")
            hb_raw = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
            hb = str(hb_raw).split(" ")[0] if hb_raw else "—"   # 時刻を落として日付だけ表示
            st.success(f"読み込みOK：号数 {gou} / 配布日 {hb} / "
                       f"データ {len(rows)}行 / 地区 {len(groups)}件")

            over = A.overflow_areas(groups)
            if over:
                detail = "、".join(f"{c}（{n}件）" for c, n in over[:5])
                more = f" ほか{len(over) - 5}地区" if len(over) > 5 else ""
                st.warning(
                    f"⚠️ 明細が13件を超える担当地区が {len(over)}件あります：{detail}{more}。"
                    "あて紙の明細枠は13行しかないため、14件目以降は印字されません。"
                    "先に関西ぱどへご確認ください。")

            c1, c2, c3 = st.columns(3)
            if c1.button("あて紙を生成", type="primary", key="keihan_atehagi"):
                st.session_state["keihan_out"] = (
                    f"あて紙（{len(groups)}地区）",
                    A.build_atehagi_workbook(groups, version),
                    A.atehagi_filename(version, rows))
            if c2.button("挟み込み実績表を生成", key="keihan_jisseki"):
                courses = A.jisseki_courses(groups, version)
                gou = next((r["gou"] for r in rows if r.get("gou")), None)
                haifubi = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
                # 外注先/リーダーごとに別タブになる(2026-08-27 大橋様ご指摘)。
                # 何枚のタブになるかを先に伝えて、印刷前に把握できるようにする。
                _n_tabs = len({c.get("leader") for c in courses})
                st.session_state["keihan_out"] = (
                    f"挟み込み実績表（{len(courses)}コース／"
                    f"外注先・リーダー別に{_n_tabs}タブ）",
                    A.build_jisseki_daishi_workbook(courses, version, gou, haifubi),
                    A.jisseki_filename(version, rows))
            if c3.button("集計表を生成", key="keihan_shukei"):
                sdata = A.shukei_data(groups, version)
                gou = next((r["gou"] for r in rows if r.get("gou")), None)
                haifubi = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
                of = A.shukei_overflow_types(sdata)
                if of:
                    detail = "、".join(f"{t}種（{ku}地区・{bu:,}部）" for t, ku, bu in of)
                    st.warning(
                        f"⚠️ 集計表の下部集計は チラシ種類数 0〜{A.SHUKEI_TYPE_MAX}種 の枠しかありません。"
                        f"枠を超える地区があります：{detail}。"
                        "この分は表に載らないため、表を足し上げた数と総計が合いません。"
                        "先に関西ぱどへご確認ください。")
                st.session_state["keihan_out"] = (
                    f"集計表（総地区数 {sdata['total_chiku']} / "
                    f"総配布部数 {sdata['total_busuu']:,} / チラシ総数 {sdata['chirashi_sou']:,}）",
                    A.build_shukei_daishi_workbook(sdata, version, gou, haifubi),
                    A.shukei_filename(version, rows))

            # ダウンロードは生成ボタンの外に出す（押した瞬間に消えないように）
            out = st.session_state.get("keihan_out")
            if out:
                label, data, fname = out
                st.caption(f"作成しました：{label}")
                st.download_button(f"{fname} をダウンロード", data=data, file_name=fname,
                                   mime=XLSX_MIME, key="keihan_dl")

            st.divider()
            st.markdown("**担当地区コードを指定して、その分だけ出す**（刷り直し用）")
            st.text_input("担当地区コード（カンマ区切りで複数可・先頭の0は有無どちらでも可）",
                          key="keihan_area_codes", placeholder="例: 010101, 46501")
            if st.button("指定した地区だけ出す", key="keihan_single"):
                # 押した時点でいったん捨てる（失敗したときに前回の別地区が残らないように）
                st.session_state.pop("keihan_single_out", None)
                raw = st.session_state.get("keihan_area_codes", "")
                codes = A.parse_area_codes(raw)
                if not raw.strip():
                    st.error("担当地区コードを入力してください。")
                elif not codes:
                    st.error("担当地区コードは6桁までです。"
                             "複数指定する場合はカンマで区切ってください（例: 010101, 046501）。")
                else:
                    sel = A.select_groups(groups, codes)
                    found = {A.area_code6(k) for k in sel}
                    missing = [c for c in codes if c not in found]
                    if not sel:
                        st.error("指定された担当地区が見つかりませんでした："
                                 + "、".join(codes))
                    else:
                        if missing:
                            st.warning("見つからなかった担当地区："
                                       + "、".join(missing))
                        st.session_state["keihan_single_out"] = (
                            A.build_atehagi_workbook(sel, version),
                            A.atehagi_filename(version, rows, chiku=list(sel.keys())),
                            len(sel))
            single = st.session_state.get("keihan_single_out")
            if single:
                sdata_bytes, sname, n_sel = single
                st.caption(f"{n_sel}地区分のあて紙を作成しました")
                st.download_button(f"{sname} をダウンロード", data=sdata_bytes,
                                   file_name=sname, mime=XLSX_MIME,
                                   key="keihan_single_dl")

with tab_shiwake:
    st.caption("配送管理表（CSV / Excel）をアップロードすると、配布員ごとの仕分け表を作ります。"
               "倉庫でチラシを配布員ごとの山に分けるためのチェック表で、"
               "印刷すると1人1枚になります。京阪南版・北版のどちらでも使えます。")
    up_s = st.file_uploader("配送管理表をアップロード", type=["csv", "xlsx", "xlsm"],
                            key="shiwake_upload")
    if up_s is not None:
        try:
            s_table = A.read_uploaded(up_s.name, up_s.getvalue())
            s_rows = SH.rows_from_haiso_table(s_table)
            s_groups, s_warn = SH.shiwake_groups(s_rows)
        except Exception as e:  # noqa: BLE001 - 読み取り失敗は画面に出して止める
            st.error(f"読み取れませんでした: {e}")
        else:
            s_gou = next((r["gou"] for r in s_rows if r["gou"]), None)
            s_haifubi = next((r["haifubi"] for r in s_rows if r["haifubi"]), None)

            # 🔴 「その他配送管理表」を入れた疑い。そちらは配布員ではなく会社名
            # (ケイピーエス/フィールドサービス)でまとまっているため、そのまま出すと
            # 「配布員2名・15万部」という無意味な表になる。気づけるようにする。
            if s_warn["looks_like_wrong_file"]:
                st.error(
                    "**このファイルは仕分け表の元データではない可能性があります。**"
                    "配送順位がどの行にも入っていません。\n\n"
                    "仕分け表に使うのは、配布員ひとりずつが行になっている "
                    "**「配送管理表」**（例：`【京阪南】20260821配送管理表.xlsx`）です。"
                    "**「その他配送管理表」**（あて紙・集計表に使うもの）は、"
                    "配布員ではなく会社名でまとまっているため、"
                    "そのまま出すと人数も部数も実態と合いません。\n\n"
                    "下の内容を見て、意図したものでなければファイルを差し替えてください。")

            # 🔴 何人を外したかを必ず出す。黙って人数が減ると倉庫で山が足りなくなる。
            msg = f"{len(s_groups)}名分の仕分け表を作成しました"
            if s_warn["excluded"]:
                msg += f"（異動「休」の{len(s_warn['excluded'])}名を除外： " \
                       f"{'、'.join(s_warn['excluded'])}）"
            st.success(msg)

            if s_warn["unknown_ido"]:
                # 見慣れない異動値の人は落とさず残したうえで知らせる。
                st.warning(
                    "異動欄に「休」以外の値がある方がいます。**除外していません**ので、"
                    "外すべき方がいたら教えてください： "
                    + "、".join(f"{n}（{v}）" for n, v in s_warn["unknown_ido"]))

            if s_groups:
                s_data = SH.build_shiwake_workbook(s_groups, gou=s_gou,
                                                   haifubi=s_haifubi)
                s_name = SH.shiwake_filename(gou=s_gou, haifubi=s_haifubi)
                st.download_button(f"{s_name} をダウンロード", data=s_data,
                                   file_name=s_name, mime=XLSX_MIME,
                                   key="shiwake_dl")
                with st.expander("中身を確認する（先頭5名）"):
                    for g in s_groups[:5]:
                        st.markdown(f"**{g['name']}**　配送順位 {g['junni']}　"
                                    f"合計 {g['total']:,}部")
                        st.table([{"チラシ名": i["chirashi"],
                                   "部数": f"{i['busuu']:,}",
                                   "サイズ": i["size"]} for i in g["items"]])


with tab_proceed:
    st.caption("リビングプロシードの配布依頼書（エリア×広告主）をアップロードすると、"
               "担当地区ごとのあて紙をまとめたExcelを作成します。")
    up_p = st.file_uploader("配布依頼書をアップロード", type=["xlsx", "xls", "csv"],
                            key="proceed_upload")
    if up_p is not None:
        try:
            parsed = PR.read_and_parse(up_p.name, up_p.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"読み取りに失敗しました: {e}")
            st.stop()

        if not parsed["areas"]:
            st.warning("エリア（担当地区）が読み取れませんでした。配布依頼書の様式をご確認ください。")
        else:
            st.success(
                f"読み込みOK：{parsed['group'] or '—'} / 号 {parsed['gou'] or '—'} / "
                f"広告主 {len(parsed['advertisers'])}社 / エリア {len(parsed['areas'])}件")
            if st.button("あて紙を生成", type="primary", key="proceed_build"):
                data = PR.build_proceed_atehagi_workbook(parsed)
                st.download_button(
                    "あて紙をダウンロード",
                    data=data,
                    file_name=PR.proceed_atehagi_filename(parsed),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="proceed_dl",
                )

with tab_advalue:
    st.caption("アドバリューの依頼表と、京阪南版の配送管理表をアップロードすると、"
               "各町丁目が京阪南版と被る担当地区を割り出した報告書を作成します。")
    adv_case = st.text_input(
        "案件名（任意・例：8-1）",
        help="アドバリューは週ごとに依頼が来るため『8-1』『8-2』『8-3』のように分けて"
             "管理されています。入力すると報告書とファイル名にそのまま入り、週ごとに"
             "生成しても上書きされず分けて保存できます。")
    col1, col2 = st.columns(2)
    with col1:
        up_irai = st.file_uploader("① アドバリュー依頼表", type=["xlsx", "xls", "csv"],
                                   key="adv_irai")
    with col2:
        up_minami = st.file_uploader("② 京阪南版 配送管理表", type=["xlsx", "xls", "csv", "xlsm"],
                                     key="adv_minami")
    if up_irai is not None and up_minami is not None:
        try:
            irai = AV.read_irai(up_irai.name, up_irai.getvalue())
            index = AV.read_minami_index(up_minami.name, up_minami.getvalue())
            report_rows = AV.build_report_rows(irai, index)
        except Exception as e:  # noqa: BLE001
            st.error(f"読み取りに失敗しました: {e}")
            st.stop()

        summ = AV.overlap_summary(report_rows)
        st.success(f"読み込みOK：依頼表 {summ['total']}エリア／"
                   f"京阪南と被り {summ['overlap']}件・被らない {summ['non_overlap']}件")
        st.dataframe(report_rows, use_container_width=True, hide_index=True)
        if st.button("報告書を生成", type="primary", key="adv_build"):
            data = AV.build_advalue_report_workbook(report_rows, case_label=adv_case.strip() or None)
            st.download_button(
                "報告書をダウンロード",
                data=data,
                file_name=AV.advalue_filename(adv_case.strip() or None),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="adv_dl",
            )
    elif up_irai is not None or up_minami is not None:
        st.info("依頼表と京阪南版 配送管理表の**両方**をアップロードしてください。")

with tab_other:
    st.info("京阪の報告書・集計表・実績表は順次追加予定です。")

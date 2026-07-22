import streamlit as st

from common.ui import apply_app_style
from common import atehagi as A
from common import proceed_atehagi as PR
from common import advalue as AV

apply_app_style()
st.title("資料作成・変換表")

tab_atehagi, tab_proceed, tab_advalue, tab_other = st.tabs(
    ["京阪 あて紙", "リビングプロシード あて紙", "アドバリュー 報告書", "その他（準備中）"])

with tab_atehagi:
    st.caption("関西ぱどの配送管理表（CSV / Excel）をアップロードすると、"
               "担当地区ごとのあて紙をまとめたExcelを作成します。")
    version_label = st.radio("版", ["京阪北版", "京阪南版"], horizontal=True)
    version = A.KEIHAN_KITA if version_label == "京阪北版" else A.KEIHAN_MINAMI

    up = st.file_uploader("配送管理表をアップロード", type=["csv", "xlsx", "xlsm"])
    if up is not None:
        try:
            table = A.read_uploaded(up.name, up.getvalue())
            rows = A.rows_from_table(table)
            groups = A.group_by_chiku(rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"読み取りに失敗しました: {e}")
            st.stop()

        gou = next((r["gou"] for r in rows if r.get("gou")), "—")
        hb_raw = next((r["haifubi"] for r in rows if r.get("haifubi")), "")
        hb = str(hb_raw).split(" ")[0] if hb_raw else "—"   # 時刻(00:00:00)を落として日付だけ表示
        st.success(f"読み込みOK：号数 {gou} / 配布日 {hb} / "
                   f"データ {len(rows)}行 / 地区 {len(groups)}件")

        if version == A.KEIHAN_MINAMI:
            st.warning("京阪南版の地区名ルールが未設定です。"
                       "管理者に地区名ルールの登録を依頼してください。")
        else:
            c1, c2 = st.columns(2)
            if c1.button("あて紙を生成", type="primary", key="keihan_atehagi"):
                data = A.build_atehagi_workbook(groups, version)
                st.download_button(
                    "あて紙をダウンロード",
                    data=data,
                    file_name=A.atehagi_filename(version, rows),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="keihan_atehagi_dl",
                )
            if c2.button("挟み込み実績表を生成", key="keihan_jisseki"):
                jrows = A.jisseki_rows(groups, version)
                jdata = A.build_jisseki_workbook(jrows)
                st.caption(f"挟み込みチラシがある地区 {len(jrows)}件（ぱどのみ地区は除外）")
                st.download_button(
                    "実績表をダウンロード",
                    data=jdata,
                    file_name=A.jisseki_filename(version, rows),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="keihan_jisseki_dl",
                )
            if st.button("集計表を生成", key="keihan_shukei"):
                sdata = A.shukei_data(groups, version)
                swb = A.build_shukei_workbook(sdata, version)
                st.caption(f"総地区数 {sdata['total_chiku']} / 総配布部数 {sdata['total_busuu']:,} / "
                           f"チラシ総数 {sdata['chirashi_sou']:,}")
                st.download_button(
                    "集計表をダウンロード",
                    data=swb,
                    file_name=A.shukei_filename(version, rows),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="keihan_shukei_dl",
                )

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
            data = AV.build_advalue_report_workbook(report_rows)
            st.download_button(
                "報告書をダウンロード",
                data=data,
                file_name="アドバリュー_エリア被り報告書.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="adv_dl",
            )
    elif up_irai is not None or up_minami is not None:
        st.info("依頼表と京阪南版 配送管理表の**両方**をアップロードしてください。")

with tab_other:
    st.info("京阪の報告書・集計表・実績表は順次追加予定です。")

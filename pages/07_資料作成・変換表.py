import streamlit as st

from common.ui import apply_app_style
from common import atehagi as A

apply_app_style()
st.title("資料作成・変換表")

tab_atehagi, tab_other = st.tabs(["京阪 あて紙", "その他（準備中）"])

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
        elif st.button("あて紙を生成", type="primary"):
            data = A.build_atehagi_workbook(groups, version)
            st.download_button(
                "あて紙をダウンロード",
                data=data,
                file_name=A.atehagi_filename(version, rows),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

with tab_other:
    st.info("リビングプロシード（配布依頼書→あて紙）、京阪の報告書・集計表・実績表、"
            "アドバリュー（依頼表→報告書＋エリア被り判定）は順次追加予定です。")

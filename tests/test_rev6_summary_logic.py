from common import posting_logic as L


def test_company_summary_totals():
    r = L.company_summary_totals(
        receivables=[{"amount": 1000}, {"amount": 500}],
        payables=[{"amount": 300}], petty=[{"amount": 200}],
        contract_lines=[{"amount": 400}], manual=[{"amount": 100}])
    assert r["sales"] == 1500
    assert r["cost"] == 1000          # 300+200+400+100
    assert r["profit"] == 500


def test_company_summary_rows_classifies_and_resolves_names():
    rows = L.company_summary_rows(
        receivables=[{"month": "2026-07", "client_id": 1, "project_id": 9, "amount": 1000}],
        payables=[{"date": "2026-07-03", "vendor_name": "大家", "project_id": 9, "amount": 300}],
        petty=[{"date": "2026-07-04", "category_id": 2, "project_id": 9, "amount": 200, "memo": "茶"}],
        contract_lines=[{"issue_date": "2026-07-05", "distributor_id": 3, "project_id": 9, "amount": 400}],
        manual=[{"work_date": "2026-07-06", "content": "配布", "project_id": 9, "amount": 100}],
        id2proj={9: "A号"}, id2vendor={}, id2cat={2: "飲料"}, id2client={1: "クライアントX"},
        id2dist={3: "山田"})
    kinds = {row["区分"] for row in rows}
    assert kinds == {"売上", "買掛", "小口", "業務委託", "直接入力"}
    sales = [r for r in rows if r["区分"] == "売上"][0]
    assert sales["項目"] == "クライアントX" and sales["案件"] == "A号" and sales["金額"] == 1000
    pay = [r for r in rows if r["区分"] == "買掛"][0]
    assert pay["項目"] == "大家" and pay["日付"] == "2026-07-03"
    dist = [r for r in rows if r["区分"] == "業務委託"][0]
    assert dist["項目"] == "山田" and dist["日付"] == "2026-07-05"

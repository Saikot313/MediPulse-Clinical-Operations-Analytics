"""Synthetic, fully reproducible clinic data (no real patient data).

Built-in signals so the analytics have something real to find:
weekday/seasonal/growth demand, department-specific no-show rates, higher no-show for
self-pay and new patients, peak-hour waits, repeat-visit patients, afternoon lab backlog.
Currency is BDT.
"""
import numpy as np
import pandas as pd

# name: (doctors, base fee, mean consult min, base no-show rate, lab-order probability)
DEPTS = {
    "General Medicine": (8, 800, 15, 0.10, 0.35),
    "Cardiology": (5, 1800, 25, 0.08, 0.60),
    "Orthopedics": (5, 1500, 22, 0.11, 0.30),
    "Pediatrics": (6, 700, 15, 0.13, 0.30),
    "Gynecology": (5, 1200, 20, 0.12, 0.45),
    "Dermatology": (4, 900, 12, 0.14, 0.10),
    "Neurology": (3, 2000, 28, 0.07, 0.55),
    "ENT": (3, 1000, 14, 0.12, 0.15),
}
TESTS = [
    ("CBC", "Hematology", 120), ("Lipid Profile", "Biochemistry", 240),
    ("Blood Glucose", "Biochemistry", 90), ("HbA1c", "Biochemistry", 300),
    ("Urine R/E", "Pathology", 120), ("ECG", "Cardiology", 45),
    ("X-Ray", "Radiology", 90), ("Ultrasound", "Radiology", 180),
    ("Thyroid Panel", "Biochemistry", 360), ("Liver Function", "Biochemistry", 300),
    ("Culture & Sensitivity", "Microbiology", 1440), ("CRP", "Biochemistry", 150),
]
CITIES = ["Dhaka", "Gazipur", "Narayanganj", "Chattogram", "Savar", "Cumilla", "Mymensingh"]
CITY_P = [0.50, 0.12, 0.10, 0.10, 0.08, 0.05, 0.05]
INSURANCE = ["Self-pay", "Corporate", "Private Insurance", "Government Scheme"]
INS_P = [0.50, 0.20, 0.20, 0.10]
INS_DISCOUNT = np.array([0.0, 0.15, 0.10, 0.30])
INS_NOSHOW = np.array([0.04, -0.03, 0.0, 0.01])
AGE_BANDS = ["0-17", "18-34", "35-49", "50-64", "65+"]
AGE_P = [0.20, 0.25, 0.25, 0.18, 0.12]
HOUR_P = np.array([8, 12, 14, 12, 8, 9, 11, 13, 9, 4], dtype=float)  # 08:00 .. 17:00
FIRST = ["Ayesha", "Rahim", "Nusrat", "Imran", "Farhana", "Tanvir", "Sabrina", "Kamal", "Mehnaz", "Arif", "Lamia", "Shafiq"]
LAST = ["Rahman", "Hossain", "Akter", "Chowdhury", "Islam", "Karim", "Sultana", "Ahmed", "Khan", "Begum", "Mia", "Das", "Sarker"]


def _dim_date(start: str, days: int) -> pd.DataFrame:
    d = pd.date_range(start, periods=days)
    return pd.DataFrame({
        "date_key": np.asarray(d.strftime("%Y%m%d")).astype(int),
        "full_date": np.asarray(d.date),
        "year": np.asarray(d.year), "quarter": np.asarray(d.quarter), "month": np.asarray(d.month),
        "month_name": np.asarray(d.strftime("%b %Y")),
        "month_start": np.asarray(d.to_period("M").to_timestamp().date),
        "iso_week": np.asarray(d.isocalendar().week).astype(int),
        "dow": np.asarray(d.dayofweek), "dow_name": np.asarray(d.strftime("%a")),
        "is_weekend": np.asarray(d.dayofweek.isin([4, 5])),  # Fri/Sat weekend (Bangladesh)
    })


def generate(n_visits: int = 20000, seed: int = 42, start: str = "2025-10-01", days: int = 365) -> dict:
    rng = np.random.default_rng(seed)
    n = n_visits
    dd = _dim_date(start, days)
    dow = dd["dow"].to_numpy()

    # ---- demand over the year
    w = np.where(np.isin(dow, [4, 5]), 0.08, 1.0) * np.where(np.isin(dow, [0, 6]), 1.15, 1.0)
    w = w * (1 + 0.15 * np.sin(2 * np.pi * (dd["month"].to_numpy() - 3) / 12)) * (1 + 0.3 * np.arange(days) / days)
    day_idx = np.sort(rng.choice(days, n, p=w / w.sum()))
    hour = rng.choice(np.arange(8, 18), n, p=HOUR_P / HOUR_P.sum())
    v_dow = dow[day_idx]

    # ---- doctors
    docs, k = [], 1
    for dept, (nd, *_rest) in DEPTS.items():
        for _ in range(nd):
            docs.append((k, f"D{k:03d}", f"Dr. {FIRST[(k * 3) % len(FIRST)]} {LAST[(k * 5) % len(LAST)]}", dept))
            k += 1
    dim_doctor = pd.DataFrame(docs, columns=["doctor_key", "doctor_id", "full_name", "department"])
    nd_total = len(dim_doctor)
    dept_names = list(DEPTS)
    d_idx = dim_doctor["department"].map({d: i for i, d in enumerate(dept_names)}).to_numpy()
    base_fee = np.array([DEPTS[d][1] for d in dept_names])[d_idx]
    cons_mean = np.array([DEPTS[d][2] for d in dept_names])[d_idx]
    ns_base = np.array([DEPTS[d][3] for d in dept_names])[d_idx]
    lab_p = np.array([DEPTS[d][4] for d in dept_names])[d_idx]
    pop = rng.gamma(4, 1, nd_total)
    doc = rng.choice(nd_total, n, p=pop / pop.sum())  # 0-based

    # ---- patients (gamma propensity => repeat visitors)
    n_pat = max(200, n // 3)
    ins_i = rng.choice(4, n_pat, p=INS_P)
    age = rng.choice(AGE_BANDS, n_pat, p=AGE_P)
    dim_patient = pd.DataFrame({
        "patient_key": np.arange(1, n_pat + 1),
        "patient_token": [f"PT{i:06d}" for i in range(1, n_pat + 1)],
        "age_band": age,
        "gender": rng.choice(["F", "M"], n_pat, p=[0.54, 0.46]),
        "city": rng.choice(CITIES, n_pat, p=CITY_P),
        "insurance_type": np.array(INSURANCE)[ins_i],
    })
    prop = rng.gamma(0.8, 1, n_pat)
    pat = rng.choice(n_pat, n, p=prop / prop.sum())

    # ---- visit outcome
    vt = rng.choice(["New", "Follow-up", "Emergency"], n, p=[0.35, 0.55, 0.10])
    p_ns = ns_base[doc] + INS_NOSHOW[ins_i[pat]] + (age[pat] == "18-34") * 0.03 + (vt == "New") * 0.02
    p_ns = np.where(vt == "Emergency", 0.0, p_ns)
    u = rng.random(n)
    status = np.where(u < p_ns, "No-Show", np.where(u < p_ns + 0.06, "Cancelled", "Completed"))
    status = np.where(vt == "Emergency", "Completed", status)
    comp = status == "Completed"

    wait = 8 + rng.lognormal(2.4, 0.6, n)
    wait = wait * np.where(np.isin(hour, [10, 11]), 1.3, 1.0) * np.where(np.isin(v_dow, [0, 6]), 1.15, 1.0)
    wait = np.where(vt == "Emergency", rng.integers(2, 10, n), wait)
    consult = np.clip(rng.normal(cons_mean[doc], 0.25 * cons_mean[doc]), 5, None).round()
    mult = np.select([vt == "New", vt == "Follow-up"], [1.0, 0.6], 1.5)
    fee = (base_fee[doc] * mult * (1 + rng.normal(0, 0.08, n))).round(-1)
    disc = (fee * INS_DISCOUNT[ins_i[pat]]).round(0)

    # ---- capacity: slots/day sized from realised load so utilisation is meaningful
    wk_days = int((~dd["is_weekend"]).sum())
    booked = np.bincount(doc[status != "Cancelled"], minlength=nd_total)
    dim_doctor["slots_per_day"] = np.maximum(2, np.ceil(booked / wk_days / rng.uniform(0.55, 0.85, nd_total))).astype(int)

    fact_visits = pd.DataFrame({
        "visit_key": np.arange(1, n + 1),
        "visit_id": [f"V{i:07d}" for i in range(1, n + 1)],
        "date_key": dd["date_key"].to_numpy()[day_idx],
        "patient_key": pat + 1, "doctor_key": doc + 1, "visit_hour": hour,
        "visit_type": vt, "status": status,
        "wait_minutes": pd.Series(np.where(comp, wait.round(), np.nan)).astype("Int64"),
        "consult_minutes": pd.Series(np.where(comp, consult, np.nan)).astype("Int64"),
        "consultation_fee": fee, "discount": disc, "net_amount": fee - disc,
    })

    # ---- lab orders for completed visits
    lab_vis = np.flatnonzero(comp & (rng.random(n) < lab_p[doc]))
    reps = rng.choice([1, 2, 3], len(lab_vis), p=[0.6, 0.3, 0.1])
    vis = np.repeat(lab_vis, reps)
    m = len(vis)
    tidx = rng.integers(0, len(TESTS), m)
    day0 = pd.to_datetime(dd["full_date"]).to_numpy()[day_idx].astype("datetime64[m]")
    ordered = day0[vis] + (hour[vis] * 60 + consult[vis] + rng.integers(0, 30, m)).astype("timedelta64[m]")
    o_hour = (ordered.astype("datetime64[h]") - ordered.astype("datetime64[D]")).astype(int)
    target = np.array([t[2] for t in TESTS])[tidx]
    tat = (target * rng.lognormal(-0.35, 0.40, m) * np.where(o_hour >= 15, 1.25, 1.0)).round().astype(int)
    pending = rng.random(m) < 0.015
    flag = rng.choice(["Normal", "High", "Low"], m, p=[0.72, 0.16, 0.12])
    flag = np.where(pending, "Pending", flag)
    resulted = pd.Series(ordered + tat.astype("timedelta64[m]"))
    resulted[pending] = pd.NaT
    fact_lab = pd.DataFrame({
        "lab_key": np.arange(1, m + 1),
        "lab_order_id": [f"L{i:07d}" for i in range(1, m + 1)],
        "visit_key": vis + 1, "test_key": tidx + 1,
        "ordered_at": pd.Series(ordered), "resulted_at": resulted,
        "turnaround_minutes": pd.Series(np.where(pending, np.nan, tat)).astype("Int64"),
        "result_flag": flag,
    })
    dim_test = pd.DataFrame(
        [(i + 1, *t) for i, t in enumerate(TESTS)], columns=["test_key", "test_name", "category", "target_tat_minutes"]
    )
    return {"dim_date": dd, "dim_doctor": dim_doctor, "dim_patient": dim_patient, "dim_test": dim_test,
            "fact_visits": fact_visits, "fact_lab_tests": fact_lab}

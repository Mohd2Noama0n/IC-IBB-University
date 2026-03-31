import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
import io
from geopy.distance import geodesic
from streamlit_js_eval import get_geolocation 

# --- 1. إعدادات الصفحة ---
st.set_page_config(page_title="FMA Compaction Pro - Dynamic Passes", layout="wide")

# --- 2. دالة الحسابات الهندسية (Hyperbolic Saturation Model) ---
def calculate_dynamic_compaction(n_actual, w_actual, w_opt, n_ref, c_ref_after, c_initial, efficiency):
    """
    حساب معامل الدمك بناءً على عدد دورات متغير لكل نقطة.
    """
    eff_coeff = efficiency / 100.0
    
    # تأثير الرطوبة (Moisture Factor)
    moisture_deviation = abs(w_actual - w_opt)
    moisture_factor = np.exp(-0.06 * moisture_deviation) 
    
    # حساب الطاقة (Energy = Passes * Efficiency)
    # نستخدم الثابت 0.6 لتمثيل منحنى التشبع الهيبيربولي (Hyperbolic)
    energy_ref = n_ref * eff_coeff
    energy_actual = n_actual * eff_coeff
    
    if energy_ref <= 0 or energy_actual <= 0: return c_initial
    
    # نسبة الاستجابة للطاقة (Energy Response Ratio)
    # هذه الصيغة تضمن أن الزيادة في الدمك تتناقص مع زيادة عدد الدورات (Diminishing Returns)
    response_ratio = (energy_actual / (energy_actual + 0.6)) / (energy_ref / (energy_ref + 0.6))
    
    total_improvement_ref = c_ref_after - c_initial
    compaction_result = c_initial + (total_improvement_ref * response_ratio * moisture_factor)
    
    return min(round(compaction_result, 2), 115.0)

# --- 3. إدارة الجلسة ---
if 'recorded_points' not in st.session_state:
    st.session_state.recorded_points = []
if 'ref_coords' not in st.session_state:
    st.session_state.ref_coords = None

# --- 4. الواجهة الجانبية ---
with st.sidebar:
    st.header("🏗️ إعدادات المعايرة")
    proj_code = st.text_input("رمز المشروع", "FMA-IBB-PRO")
    efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)
    omc = st.number_input("الرطوبة المثالية OMC (%)", value=12.0)
    
    st.divider()
    st.subheader("🧪 بيانات النقطة المرجعية (Point 0)")
    c_initial = st.number_input("الدمك الابتدائي (%)", value=80.0)
    n_ref = st.number_input("عدد دورات المرجعية الفعلية", value=8, min_value=1)
    c_ref_after = st.number_input("دمك المرجعية النهائي (%)", value=98.5)
    w_ref_actual = st.number_input("الرطوبة الفعلية (%)", value=11.5)

# --- 5. الرصد الميداني الحقيقي ---
st.title("📊 نظام الرصد الديناميكي لعمليات الدمك")
loc = get_geolocation()

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 التحكم بالموقع (GPS)")
    if loc:
        curr_lat, curr_lon = loc['coords']['latitude'], loc['coords']['longitude']
        st.success(f"إحداثياتك: {curr_lat:.6f}, {curr_lon:.6f}")
        if st.button("🚩 تسجيل النقطة المرجعية"):
            st.session_state.ref_coords = (curr_lat, curr_lon)
            st.toast("تم تحديد الصفر الميداني.")
    else:
        st.error("📡 يرجى السماح بالوصول للموقع.")

with col2:
    st.subheader("🚜 إدخال بيانات النقطة الحالية")
    # هنا يستطيع المهندس تعديل عدد الدورات لكل نقطة على حدة قبل التسجيل
    current_n = st.number_input("عدد دورات المعدة لهذه النقطة", value=int(n_ref), min_value=1)
    current_w = st.number_input("الرطوبة المقدرة لهذه النقطة (%)", value=float(w_ref_actual))

st.divider()

# --- 6. تسجيل النقاط ---
if st.session_state.ref_coords and loc:
    dist = geodesic(st.session_state.ref_coords, (curr_lat, curr_lon)).meters
    st.info(f"المسافة الحالية عن المرجعية: {dist:.2f} متر")

    if st.button("➕ تسجيل النقطة (رصد فعلي)"):
        comp_val = calculate_dynamic_compaction(current_n, current_w, omc, n_ref, c_ref_after, c_initial, efficiency)
        
        st.session_state.recorded_points.append({
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Latitude": curr_lat,
            "Longitude": curr_lon,
            "Dist(m)": round(dist, 2),
            "Passes(n)": current_n,
            "Moisture(%)": current_w,
            "Compaction(%)": comp_val
        })
        st.toast(f"تم تسجيل النقطة بنسبة دمك {comp_val}%")

# --- 7. عرض النتائج والتقارير ---
if st.session_state.recorded_points:
    df = pd.DataFrame(st.session_state.recorded_points)
    st.dataframe(df, use_container_width=True)

    # الخريطة الحرارية
    fig = px.density_mapbox(df, lat='Latitude', lon='Longitude', z='Compaction(%)',
                            radius=40, zoom=18, mapbox_style="open-street-map",
                            color_continuous_scale="Viridis")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

    # تصدير Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    st.download_button("📥 تحميل التقرير (Excel)", buffer.getvalue(), f"FMA_Report_{proj_code}.xlsx")

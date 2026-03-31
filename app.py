import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from geopy.distance import geodesic
import io
from streamlit_js_eval import get_geolocation # مكتبة ضرورية للحصول على GPS الهاتف

# --- إعدادات الصفحة ---
st.set_page_config(page_title="FMA Compaction Monitoring", layout="wide")

# --- دالة الحساب الهندسي (المعايرة) ---
def calculate_field_compaction(n_passes, w_actual, w_opt, n_ref, c_ref_after, c_initial, efficiency):
    eff_coeff = efficiency / 100.0
    moisture_deviation = abs(w_actual - w_opt)
    moisture_factor = np.exp(-0.06 * moisture_deviation)
    
    energy_target = n_passes * eff_coeff
    energy_ref = n_ref * eff_coeff
    
    if energy_ref <= 0 or energy_target <= 0: return c_initial
    
    total_improvement_ref = c_ref_after - c_initial
    improvement_ratio = (np.log1p(energy_target) / np.log1p(energy_ref))
    
    result = c_initial + (total_improvement_ref * improvement_ratio * moisture_factor)
    return min(round(result, 2), 115.0)

# --- إدارة تخزين النقاط (Session State) ---
if 'recorded_points' not in st.session_state:
    st.session_state.recorded_points = []

# --- الواجهة الجانبية ---
with st.sidebar:
    st.header("🏗️ إعدادات المعايرة والمعدة")
    proj_code = st.text_input("رمز المشروع", "FMA-IBB-2026")
    spacing = st.number_input("مسافة التباعد المطلوبة (متر)", value=5.0)
    efficiency = st.slider("كفاءة المعدة (%)", 50, 120, 100)
    omc = st.number_input("الرطوبة المثالية OMC (%)", value=12.0)
    
    st.divider()
    st.subheader("🧪 بيانات النقطة المرجعية")
    c_initial = st.number_input("الدمك الابتدائي (%)", value=80.0)
    n_ref = st.number_input("دورات المرجعية (n_ref)", value=8)
    c_ref_after = st.number_input("دمك المرجعية النهائي (%)", value=98.5)
    w_ref_actual = st.number_input("الرطوبة الفعلية (%)", value=11.5)

# --- الجزء الرئيسي: نظام الرصد الميداني ---
st.title("📊 نظام الرصد والتدقيق الميداني (Live GPS)")

# ميزة جلب الموقع آلياً من الهاتف
st.subheader("🛰️ وحدة الرصد المكاني")
loc = get_geolocation()

if loc:
    curr_lat = loc['coords']['latitude']
    curr_lon = loc['coords']['longitude']
    st.success(f"تم تحديد موقعك الحالي: {curr_lat:.6f}, {curr_lon:.6f}")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📍 تسجيل موقع النقطة المرجعية (Point 0)"):
            st.session_state.ref_coords = (curr_lat, curr_lon)
            st.info("تم تثبيت النقطة المرجعية.")

    with col_btn2:
        if st.button("➕ تسجيل النقطة الحالية (مرور المعدة)"):
            if 'ref_coords' in st.session_state:
                # حساب البعد عن المرجعية للتأكد من الحركة
                dist = geodesic(st.session_state.ref_coords, (curr_lat, curr_lon)).meters
                
                # إدخال عدد الدورات لهذه النقطة (يمكن أتمتتها لاحقاً)
                p_n = st.number_input(f"عدد دورات المعدة عند المسافة {dist:.1f}م", value=n_ref, key=f"n_{len(st.session_state.recorded_points)}")
                
                comp_val = calculate_field_compaction(p_n, w_ref_actual, omc, n_ref, c_ref_after, c_initial, efficiency)
                
                st.session_state.recorded_points.append({
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Latitude": curr_lat,
                    "Longitude": curr_lon,
                    "Distance from Ref (m)": round(dist, 2),
                    "Passes": p_n,
                    "Compaction (%)": comp_val
                })
            else:
                st.error("يرجى تسجيل النقطة المرجعية أولاً!")
else:
    st.warning("يرجى تفعيل الـ GPS في المتصفح والسماح للتطبيق بالوصول للموقع.")

# --- عرض النتائج الحية ---
if st.session_state.recorded_points:
    df = pd.DataFrame(st.session_state.recorded_points)
    st.divider()
    st.subheader("📋 جدول الرصد الميداني الفعلي")
    st.dataframe(df, use_container_width=True)

    # الخريطة الحرارية للنقاط المسجلة فقط
    fig = px.density_mapbox(df, lat='Latitude', lon='Longitude', z='Compaction (%)',
                            radius=30, zoom=18, mapbox_style="open-street-map")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

    if st.button("🗑️ مسح السجل والبدء من جديد"):
        st.session_state.recorded_points = []
        st.rerun()

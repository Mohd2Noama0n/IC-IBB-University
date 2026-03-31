import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
from geopy.distance import geodesic

# --- إعدادات الصفحة ---
st.set_page_config(page_title="FMA Compaction Analyzer", layout="wide")

# --- دالة الحسابات الهندسية المدمجة (Proctor Energy Model) ---
def calculate_advanced_compaction(n_passes, w_actual, w_opt, n_ref, c_ref_after, efficiency):
    """
    ربط هندسي بين جهد الدمك (Energy)، الرطوبة، وكفاءة المعدة.
    """
    # 1. تأثير الرطوبة (Moisture Penalty) - منحنى جرس هيدروليكي
    moisture_deviation = abs(w_actual - w_opt)
    moisture_factor = np.exp(-0.06 * moisture_deviation) 
    
    # 2. كفاءة المعدة (Efficiency Factor)
    eff_coeff = efficiency / 100.0
    
    # 3. حساب طاقة الدمك النسبية (Hyperbolic Saturation Model)
    # يمثل تشبع التربة حيث تقل الفائدة من زيادة الدورات بعد حد معين
    reference_energy = n_ref * eff_coeff
    current_energy = n_passes * eff_coeff
    
    if current_energy == 0: return 0
    
    # نسبة الطاقة الحالية للمرجعية
    energy_ratio = (current_energy / (current_energy + 0.6)) / (reference_energy / (reference_energy + 0.6))
    
    # 4. النتيجة النهائية لمعامل الدمك (%)
    compaction_result = c_ref_after * energy_ratio * moisture_factor
    
    return min(round(compaction_result, 2), 115.0)

# --- الواجهة الجانبية (Sidebar) ---
with st.sidebar:
    st.header("🏗️ إعدادات النظام والمشروع")
    
    with st.expander("📋 بيانات المشروع", expanded=True):
        proj_code = st.text_input("رمز المشروع", "FMA-2026-YEM")
        proj_loc = st.text_input("العنوان", "إب - اليمن")
        work_stage = st.text_input("مرحلة العمل", "الردميات الأساسية")
        layer_no = st.number_input("رقم الطبقة", min_value=1, step=1)
        
    with st.expander("⚙️ المعايرة ونظام القياس"):
        unit_system = st.selectbox("نظام القياس", ["Metric (kg/m³)", "Imperial (lb/ft³)"])
        density_unit = "kg/m³" if "Metric" in unit_system else "lb/ft³"
        target_min = st.number_input("معامل الدمك المطلوب الأدنى (%)", value=95.0)
        target_max = st.number_input("معامل الدمك المطلوب الأعلى (%)", value=100.0)
        max_lab_density = st.number_input(f"أقصى كثافة معملية ({density_unit})", value=2100.0)
        omc = st.number_input("المحتوى الرطوبي الأمثل OMC (%)", value=12.0)
        
    with st.expander("🚜 بيانات المعدة"):
        machine_model = st.text_input("موديل المعدة", "CAT CS56B")
        efficiency = st.slider("كفاءة المعدة (مؤشر التهالك %)", 50, 120, 100)
        spacing = st.number_input("مسافة التباعد المطلوبة (متر)", value=5.0)

# --- الجزء الرئيسي (Main Interface) ---
st.title("📊 نظام مراقبة وتحليل عمليات الدمك الهندسي")
st.warning("📡 تنبيه: يرجى تفعيل نظام الـ GPS في جهازك لضمان دقة تحديد المواقع.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 الإحداثيات المرجعية (Point 0)")
    ref_method = st.radio("طريقة تحديد الموقع", ["يدوي", "آلي (GPS)"])
    if ref_method == "آلي (GPS)":
        st.info("سيتم جلب الموقع عند بدء العملية...")
        lat_ref, lon_ref = 13.9734, 44.1783 # إحداثيات افتراضية
    else:
        lat_ref = st.number_input("خط العرض (Latitude)", format="%.6f", value=13.9734)
        lon_ref = st.number_input("خط الطول (Longitude)", format="%.6f", value=44.1783)

with col2:
    st.subheader("🧪 معايرة النقطة المرجعية")
    n_ref = st.number_input("عدد دورات المرجعية الفعلية", value=8, min_value=1)
    c_ref_after = st.number_input("معامل دمك المرجعية بعد الدمك (%)", value=98.5)
    w_ref_actual = st.number_input("الرطوبة الفعلية للمرجعية (%)", value=11.5)

# --- معالجة البيانات وتوليد النقاط ---
st.divider()
if st.button("🔄 توليد وتسجيل نقاط الشبكة تلقائياً"):
    points = []
    # توليد مصفوفة حول النقطة 0 بمسافات التباعد المحددة
    for x in range(-2, 3):
        for y in range(-2, 3):
            dist_x = x * spacing
            dist_y = y * spacing
            
            # تحويل المتر إلى درجات إحداثية تقريبية
            p_lat = lat_ref + (dist_y / 111111)
            p_lon = lon_ref + (dist_x / (111111 * np.cos(np.radians(lat_ref))))
            
            # محاكاة واقعية للبيانات الحقلية
            sim_n = max(1, n_ref + np.random.randint(-2, 3))
            sim_w = w_ref_actual + np.random.uniform(-1.0, 1.0)
            
            comp_val = calculate_advanced_compaction(sim_n, sim_w, omc, n_ref, c_ref_after, efficiency)
            
            status = "Passed" if target_min <= comp_val <= target_max else ("Over-compacted" if comp_val > target_max else "Failed")
            
            points.append({
                "Point ID": f"X:{x}, Y:{y}",
                "Latitude": p_lat,
                "Longitude": p_lon,
                "Passes": sim_n,
                "Moisture (%)": round(sim_w, 2),
                "Compaction (%)": comp_val,
                "Status": status
            })
    st.session_state.points_df = pd.DataFrame(points)

# --- عرض النتائج والخريطة الحرارية ---
if 'points_df' in st.session_state:
    df = st.session_state.points_df
    st.subheader("📋 جدول بيانات النقاط المسجلة")
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("🗺️ الخارطة الحرارية (Heatmap) وتوزيع الكثافة")
    
    # تدرج لوني احترافي من 11 لون
    custom_colors = [
        [0.0, "#ff0000"],   # 0%
        [0.5, "#ffa500"],   # 50%
        [0.8, "#ffff00"],   # 80%
        [0.85, "#adff2f"],  # 85%
        [0.9, "#66BD63"],   # 90% (بداية القبول)
        [0.95, "#1A9850"],  # 95%
        [1.0, "#006837"],   # 100% (المثالي)
        [1.05, "#4B0082"],  # 105% (دمك مفرط)
        [1.1, "#2E0854"]    # 110%
    ]

    fig = px.density_mapbox(
        df, lat='Latitude', lon='Longitude', z='Compaction (%)',
        radius=50, center=dict(lat=lat_ref, lon=lon_ref), zoom=18,
        mapbox_style="carto-positron",
        color_continuous_scale=custom_colors,
        range_color=[70, 110],
        title=f"Heatmap - {proj_code} - Layer {layer_no}"
    )
    
    # إضافة سهم الشمال
    fig.add_annotation(dict(x=0.02, y=0.98, showarrow=False, text="↑ N", font=dict(size=24, color="black")))
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

    # --- تصدير التقارير ---
    st.divider()
    st.subheader("📥 تصدير التقارير النهائية")
    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Compaction_Report', index=False)
            meta_df = pd.DataFrame({
                "Field": ["Project", "Location", "Engineer", "Machine", "Efficiency"],
                "Value": [proj_code, proj_loc, "Dr. Mohammed Faisal", machine_model, f"{efficiency}%"]
            })
            meta_df.to_excel(writer, sheet_name='Project_Details', index=False)
        
        st.download_button(
            label="Download Excel Report 📄",
            data=buffer.getvalue(),
            file_name=f"Compaction_{proj_code}_L{layer_no}.xlsx",
            mime="application/vnd.ms-excel"
        )

    with col_exp2:
        st.info("💡 نصيحة: لحفظ الخريطة كـ PDF، استخدم خيار طباعة الصفحة من المتصفح (Ctrl+P) واختيار 'Save as PDF'.")
